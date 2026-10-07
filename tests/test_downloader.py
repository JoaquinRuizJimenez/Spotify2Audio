import pytest

from spotify2audio.core.cancellation import CancellationToken
from spotify2audio.core.errors import CancelledError, DownloadError
from spotify2audio.models.candidate import Candidate
from spotify2audio.models.track import Track
from spotify2audio.services.downloader import Downloader, _short_error, verify_duration

T = Track(spotify_id="s1", title="Song", artists=("A",), album="Al", duration_ms=200_000)


class FakeSearcher:
    def find_candidates(self, track):
        return [Candidate(f"vid{i:08d}", "Song", "A", 200, score=0.9 - i / 10) for i in range(4)]


class ScriptedDownloader(Downloader):
    def __init__(self, outcomes, **kw):
        super().__init__(searcher=FakeSearcher(), **kw)
        self.outcomes, self.tried = outcomes, []

    def _download_one(self, cand, track, work_dir, on_progress, cancel):
        self.tried.append(cand.video_id)
        out = self.outcomes[len(self.tried) - 1]
        if isinstance(out, Exception):
            raise out
        return out


def test_falls_back_to_next_candidate(tmp_path):
    d = ScriptedDownloader([DownloadError("privado"), "OK"])
    assert d.download_track(T, tmp_path) == "OK"
    assert d.tried == ["vid00000000", "vid00000001"]


def test_all_fail_reports_every_reason(tmp_path):
    d = ScriptedDownloader([DownloadError("a"), DownloadError("b"), DownloadError("c")], max_candidates=3)
    with pytest.raises(DownloadError) as e:
        d.download_track(T, tmp_path)
    assert len(d.tried) == 3 and "a" in str(e.value) and "c" in str(e.value)


def test_cancel_stops_immediately(tmp_path):
    token = CancellationToken()
    token.cancel()
    d = ScriptedDownloader(["OK"])
    with pytest.raises(CancelledError):
        d.download_track(T, tmp_path, cancel=token)
    assert d.tried == []


def test_cancelled_during_download_propagates(tmp_path):
    d = ScriptedDownloader([CancelledError("x"), "OK"])
    with pytest.raises(CancelledError):
        d.download_track(T, tmp_path)
    assert len(d.tried) == 1


def test_verify_duration():
    verify_duration(T, 205)
    verify_duration(T, None)
    with pytest.raises(DownloadError):
        verify_duration(T, 400)


def test_error_hints():
    assert "Deno" in _short_error(Exception("ERROR: n challenge solving failed"))
    assert "yt-dlp" in _short_error(Exception("Sign in to confirm you're not a bot"))
    assert "\x1b" not in _short_error(Exception("\x1b[0;31mERROR:\x1b[0m boom"))
