"""Búsqueda de la pista en YouTube/YouTube Music y puntuación de candidatos.

La puntuación (0..1) combina duración (40%), título (35%) y artista (25%), con penalizaciones
por versiones no deseadas (live, cover, remix...) y bonus por canales "- Topic" (audio oficial).
Las funciones de puntuación son puras y se prueban sin red.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from urllib.parse import quote_plus

import yt_dlp
from yt_dlp.utils import DownloadError as YtDlpError

from ..core.errors import DownloadError, MatchNotFoundError
from ..models.candidate import Candidate
from ..models.track import Track

log = logging.getLogger(__name__)

DURATION_FULL_S = 3        # diferencia aceptada sin penalización
DURATION_MAX_S = 15        # por encima, el candidato se descarta
MIN_TITLE_SCORE = 0.5      # el título debe coincidir al menos a medias
MIN_SCORE = 0.60
GOOD_ENOUGH = 0.85         # si el mejor candidato lo supera, no se hacen más búsquedas

_UNWANTED = (
    "live", "en vivo", "cover", "remix", "karaoke", "instrumental", "sped up", "slowed",
    "reverb", "nightcore", "8d", "bass boosted", "mashup", "reaction", "tutorial", "acoustic",
)
_VIDEO_WORDS = ("official video", "music video", "video oficial", "videoclip", "official music video")

_FEAT_BRACKET = re.compile(r"[\(\[]\s*(?:feat|ft|featuring|with|prod)\b[^\)\]]*[\)\]]", re.I)
_FEAT_DASH = re.compile(r"\s[-–]\s*(?:feat|ft|featuring)\b.*$", re.I)
_REMASTER_BRACKET = re.compile(r"[\(\[][^\)\]]*remaster[^\)\]]*[\)\]]", re.I)
_REMASTER_DASH = re.compile(r"\s[-–]\s*(?:\d{4}\s+)?(?:digital\s+)?remaster(?:ed)?[^-–]*$", re.I)


# --------------------------------------------------------------------------- texto
def normalize(text: str) -> str:
    """Minúsculas, sin acentos ni signos; tokens separados por un espacio."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(re.findall(r"\w+", text.casefold()))


def clean_title(title: str) -> str:
    """Quita '(feat. X)' y '- Remastered 2011': no ayudan a encontrar ni a comparar."""
    for rx in (_FEAT_BRACKET, _FEAT_DASH, _REMASTER_BRACKET, _REMASTER_DASH):
        title = rx.sub("", title)
    return re.sub(r"\s+", " ", title).strip()


def _has(text_norm: str, phrase: str) -> bool:
    return f" {phrase} " in f" {text_norm} "


# --------------------------------------------------------------------------- puntuación
def _title_score(track: Track, cand: Candidate) -> float:
    wanted = set(normalize(clean_title(track.title)).split())
    if not wanted:
        return 0.5
    found = set(normalize(cand.title).split())
    return len(wanted & found) / len(wanted)


def _artist_score(track: Track, cand: Candidate) -> float:
    hay = normalize(f"{cand.title} {cand.channel}")
    for i, artist in enumerate(track.artists):
        na = normalize(artist)
        if na and _has(hay, na):
            return 1.0 if i == 0 else 0.8
    tokens = set(normalize(track.primary_artist).split())
    if tokens:
        return 0.8 * len(tokens & set(hay.split())) / len(tokens)
    return 0.0


def score_candidate(track: Track, cand: Candidate) -> float | None:
    """Rellena cand.score/cand.notes. Devuelve None si el candidato queda descartado."""
    cand.notes = []
    if cand.duration_s and track.duration_ms:
        diff = abs(cand.duration_s - track.duration_s)
        if diff > DURATION_MAX_S:
            cand.notes.append(f"descartado: duración difiere {diff:.0f}s")
            return None
        dur = 1.0 if diff <= DURATION_FULL_S else 1 - (diff - DURATION_FULL_S) / (DURATION_MAX_S - DURATION_FULL_S)
        cand.notes.append(f"duración Δ{diff:.0f}s")
    else:
        dur = 0.4
        cand.notes.append("duración desconocida")

    title = _title_score(track, cand)
    if title < MIN_TITLE_SCORE:
        cand.notes.append(f"descartado: título no coincide ({title:.2f})")
        return None
    artist = _artist_score(track, cand)
    score = 0.40 * dur + 0.35 * title + 0.25 * artist
    cand.notes.append(f"dur {dur:.2f} / título {title:.2f} / artista {artist:.2f}")

    reference = normalize(f"{track.title} {track.album}")
    cand_title = normalize(cand.title)
    penalty = 0.0
    for kw in _UNWANTED:
        if _has(cand_title, kw) and not _has(reference, kw):
            penalty += 0.30
            cand.notes.append(f"-0.30 contiene '{kw}'")
    score -= min(penalty, 0.60)

    if normalize(cand.channel).endswith(" topic"):
        score += 0.08
        cand.notes.append("+0.08 canal Topic")
    if _has(cand_title, "official audio"):
        score += 0.04
    if any(_has(cand_title, w) for w in _VIDEO_WORDS):
        score -= 0.05

    cand.score = max(0.0, min(1.0, score))
    return cand.score


def rank_candidates(track: Track, candidates: list[Candidate], min_score: float = MIN_SCORE) -> list[Candidate]:
    seen: set[str] = set()
    ranked: list[Candidate] = []
    for cand in candidates:
        if cand.video_id in seen:
            continue
        seen.add(cand.video_id)
        score = score_candidate(track, cand)
        if score is not None and score >= min_score:
            ranked.append(cand)
    ranked.sort(key=lambda c: (-c.score, abs((c.duration_s or 0) - track.duration_s)))
    return ranked


# --------------------------------------------------------------------------- búsqueda
class YouTubeSearcher:
    def __init__(self, use_ytmusic: bool = True, results_per_query: int = 6, socket_timeout: int = 15) -> None:
        self.use_ytmusic = use_ytmusic
        self.results = results_per_query
        self.socket_timeout = socket_timeout

    def _queries(self, track: Track) -> list[tuple[str, str]]:
        artist, title = track.primary_artist, clean_title(track.title)
        queries: list[tuple[str, str]] = []
        if self.use_ytmusic:
            q = quote_plus(f"{artist} {title}")
            queries.append(("ytmusic", f"https://music.youtube.com/search?q={q}#songs"))
        queries.append(("youtube", f"ytsearch{self.results}:{artist} - {title}"))
        queries.append(("youtube", f"ytsearch{self.results}:{artist} {title} official audio"))
        return queries

    def _extract(self, query: str) -> list[dict]:
        """Única función que toca la red; se sustituye en los tests."""
        opts = {"quiet": True, "no_warnings": True, "extract_flat": True,
                "skip_download": True, "socket_timeout": self.socket_timeout,
                "playlistend": self.results}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(query, download=False)
        return list((info or {}).get("entries") or [])

    @staticmethod
    def _to_candidates(entries: list[dict], source: str) -> list[Candidate]:
        out = []
        for e in entries:
            vid = e.get("id") or ""
            if not e or len(vid) != 11 or not e.get("title"):    # descarta canales/playlists
                continue
            out.append(Candidate(
                video_id=vid, title=e["title"],
                channel=e.get("channel") or e.get("uploader") or "",
                duration_s=e.get("duration"), source=source))
        return out

    def find_candidates(self, track: Track) -> list[Candidate]:
        pool: list[Candidate] = []
        ranked: list[Candidate] = []
        errors: list[str] = []
        ok_queries = 0
        for source, query in self._queries(track):
            try:
                entries = self._extract(query)
            except (YtDlpError, OSError) as exc:
                errors.append(str(exc)[:150])
                log.debug("Búsqueda fallida (%s): %s", source, exc)
                continue
            ok_queries += 1
            pool.extend(self._to_candidates(entries, source))
            ranked = rank_candidates(track, pool)
            if ranked and ranked[0].score >= GOOD_ENOUGH:
                break
        if ranked:
            return ranked
        if ok_queries == 0:
            raise DownloadError(f"La búsqueda en YouTube falló: {errors[0] if errors else 'sin detalle'}")
        raise MatchNotFoundError(f"Sin coincidencias fiables en YouTube para: {track}")
