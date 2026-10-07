import pytest

from spotify2audio.core.errors import InvalidSpotifyUrlError, SpotifyError
from spotify2audio.services.spotify_client import SpotifyClient, parse_playlist_id, parse_track

PID = "37i9dQZF1DXcBWIGoYBM5M"


@pytest.mark.parametrize("text", [
    f"https://open.spotify.com/playlist/{PID}",
    f"https://open.spotify.com/playlist/{PID}?si=abc123def",
    f"https://open.spotify.com/intl-es/playlist/{PID}?si=x",
    f"https://open.spotify.com/embed/playlist/{PID}",
    f"spotify:playlist:{PID}",
    f"  {PID}  ",
])
def test_parse_ok(text):
    assert parse_playlist_id(text) == PID


@pytest.mark.parametrize("text", [
    "", "hola", "https://open.spotify.com/album/" + PID,
    "https://open.spotify.com/track/" + PID, "https://spotify.link/abc",
])
def test_parse_invalid(text):
    with pytest.raises(InvalidSpotifyUrlError):
        parse_playlist_id(text)


def raw_track(i, **kw):
    t = {"id": f"id{i:020d}", "name": f"Song {i}", "type": "track", "duration_ms": 200000,
         "track_number": i, "disc_number": 1, "explicit": False,
         "artists": [{"name": "Artist"}, {"name": "Guest"}],
         "external_ids": {"isrc": "ES1234567890"},
         "album": {"name": "Album", "release_date": "2019-05-03", "total_tracks": 12,
                   "artists": [{"name": "Artist"}],
                   "images": [{"url": "small", "width": 64}, {"url": "big", "width": 640}]}}
    t.update(kw)
    return t


def test_parse_track_both_key_names():
    for key in ("item", "track"):
        t = parse_track({key: raw_track(3)}, position=7)
        assert t.title == "Song 3" and t.year == 2019 and t.cover_url == "big"
        assert t.artists == ("Artist", "Guest") and t.playlist_position == 7 and t.isrc == "ES1234567890"


def test_parse_track_skips_unusable():
    assert parse_track({"item": None}, 1) is None
    assert parse_track({"item": raw_track(1, is_local=True)}, 1) is None
    assert parse_track({"item": raw_track(1, type="episode")}, 1) is None
    assert parse_track({"item": raw_track(1, id=None)}, 1) is None


class FakeSP:
    def __init__(self, total=250, fail_items=None):
        self.total, self.fail_items, self.calls = total, fail_items, []

    def _get(self, path, **params):
        self.calls.append((path, params))
        if path.endswith("/items"):
            if self.fail_items:
                raise self.fail_items
            off, lim = params["offset"], params["limit"]
            items = []
            for i in range(off, min(off + lim, self.total)):
                items.append({"item": None} if i == 5 else {"item": raw_track(i + 1)})
            return {"items": items, "total": self.total, "next": "x" if off + lim < self.total else None}
        return {"name": "Mi lista", "owner": {"display_name": "Yo", "id": "yo"},
                "images": [{"url": "cov", "width": 300}], "external_urls": {"spotify": "u"}}


def test_pagination_and_skips():
    sp = FakeSP(250)
    seen = []
    pl = SpotifyClient(sp).get_playlist(PID, progress=lambda d, t: seen.append((d, t)))
    assert len(pl) == 249 and len(pl.skipped) == 1
    assert pl.name == "Mi lista" and pl.owner == "Yo"
    assert seen[-1] == (250, 250) and len([c for c in sp.calls if c[0].endswith("/items")]) == 3


def test_403_message():
    from spotipy.exceptions import SpotifyException
    sp = FakeSP(fail_items=SpotifyException(403, -1, "Forbidden"))
    with pytest.raises(SpotifyError, match="403"):
        SpotifyClient(sp).get_playlist(PID)
