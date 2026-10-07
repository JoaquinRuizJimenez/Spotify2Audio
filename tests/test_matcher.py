import pytest
from yt_dlp.utils import DownloadError as YtDlpError

from spotify2audio.core.errors import DownloadError, MatchNotFoundError
from spotify2audio.models.candidate import Candidate
from spotify2audio.models.track import Track
from spotify2audio.services.matcher import (YouTubeSearcher, clean_title, normalize,
                                            rank_candidates, score_candidate)


def trk(title="Bohemian Rhapsody", artists=("Queen",), dur=354, album="A Night at the Opera"):
    return Track(spotify_id="s1", title=title, artists=artists, album=album, duration_ms=dur * 1000)


def cand(i, title, channel="", dur=None):
    return Candidate(video_id=f"vid{i:08d}", title=title, channel=channel, duration_s=dur)


def test_normalize_and_clean():
    assert normalize("Beyoncé – Halo!") == "beyonce halo"
    assert clean_title("Song (feat. Guest)") == "Song"
    assert clean_title("Song - feat. Guest") == "Song"
    assert clean_title("Song - 2011 Remaster") == "Song"
    assert clean_title("Song - Remastered 2011") == "Song"
    assert clean_title("Song (Remastered 2011)") == "Song"
    assert clean_title("Song - Radio Edit") == "Song - Radio Edit"   # las versiones sí importan


def test_ranking_prefers_topic_channel_and_rejects_wrong_ones():
    t = trk()
    cs = [
        cand(1, "Queen - Bohemian Rhapsody (Live at Wembley)", "Queen Official", 340),
        cand(2, "Bohemian Rhapsody", "Queen - Topic", 355),
        cand(3, "Bohemian Rhapsody - Cover by Someone", "Someone", 354),
        cand(4, "Queen Greatest Hits Full Album", "Queen", 4000),
        cand(5, "Queen - Don't Stop Me Now", "Queen - Topic", 211),
    ]
    ranked = rank_candidates(t, cs)
    assert [c.video_id for c in ranked][0] == "vid00000002"
    ids = {c.video_id for c in ranked}
    assert "vid00000004" not in ids and "vid00000005" not in ids and "vid00000003" not in ids


def test_dedupes_same_video():
    t = trk()
    c = cand(2, "Bohemian Rhapsody", "Queen - Topic", 355)
    assert len(rank_candidates(t, [c, c])) == 1


def test_feat_and_remaster_in_spotify_title_still_match():
    t = trk(title="Halo (feat. Guest) - Remastered 2011", artists=("Beyoncé",), dur=261)
    c = cand(1, "Beyonce - Halo", "BeyoncéVEVO", 262)
    assert score_candidate(t, c) > 0.85


def test_live_allowed_when_spotify_title_is_live():
    t = trk(title="Song - Live", artists=("Band",), dur=200, album="Greatest")
    c = cand(1, "Band - Song (Live)", "Band", 201)
    assert score_candidate(t, c) > 0.8


def test_unknown_duration_ranks_below_confirmed_duration():
    t = trk()
    known = cand(1, "Queen - Bohemian Rhapsody", "Queen", 354)
    unknown = cand(2, "Queen - Bohemian Rhapsody", "Queen", None)
    ranked = rank_candidates(t, [unknown, known])
    assert ranked[0].video_id == known.video_id and len(ranked) == 2


def test_non_latin_titles():
    t = trk(title="夜に駆ける", artists=("YOASOBI",), dur=261)
    assert score_candidate(t, cand(1, "YOASOBI「夜に駆ける」 Official Audio", "YOASOBI", 261)) > 0.9


def test_other_song_same_artist_rejected():
    t = trk()
    assert score_candidate(t, cand(1, "Queen - Another One Bites the Dust", "Queen", 354)) is None


# ---- searcher con red simulada ------------------------------------------------
def entry(i, title, channel, dur):
    return {"id": f"vid{i:08d}", "title": title, "channel": channel, "duration": dur}


class FakeSearcher(YouTubeSearcher):
    def __init__(self, responses):
        super().__init__()
        self.responses, self.calls = responses, []

    def _extract(self, query):
        self.calls.append(query)
        r = self.responses[min(len(self.calls) - 1, len(self.responses) - 1)]
        if isinstance(r, Exception):
            raise r
        return r


def test_search_stops_early_when_good_enough():
    s = FakeSearcher([[entry(1, "Bohemian Rhapsody", "Queen - Topic", 354)]])
    assert s.find_candidates(trk())[0].score >= 0.85 and len(s.calls) == 1


def test_search_continues_and_filters_non_videos():
    bad = [{"id": "UCchannelid", "title": "Queen"}, {"id": "short", "title": "x"}]
    s = FakeSearcher([bad, [entry(1, "Queen - Bohemian Rhapsody", "Queen", 354)]])
    res = s.find_candidates(trk())
    assert len(s.calls) >= 2 and res[0].video_id == "vid00000001"


def test_no_match_vs_network_failure():
    with pytest.raises(MatchNotFoundError):
        FakeSearcher([[]]).find_candidates(trk())
    with pytest.raises(DownloadError, match="falló"):
        FakeSearcher([YtDlpError("sin red")]).find_candidates(trk())
