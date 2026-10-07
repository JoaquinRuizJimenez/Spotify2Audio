import pytest

from spotify2audio.utils.sanitize import sanitize_component, track_filename


@pytest.mark.parametrize("raw,expected", [
    ('AC/DC', "AC_DC"),
    ('What?', "What_"),
    ('Song: "Live"', "Song_ _Live_"),
    ("Trailing dot...", "Trailing dot"),
    ("   spaced   out  ", "spaced out"),
    ("CON", "_CON"),
    ("nul.txt", "_nul.txt"),
    ("", "Unknown"),
    ("...", "Unknown"),
])
def test_sanitize(raw, expected):
    assert sanitize_component(raw) == expected


def test_max_len():
    assert len(sanitize_component("a" * 300, max_len=50)) == 50


def test_track_filename():
    assert track_filename(1, "Intro", "mp3") == "01 - Intro.mp3"
    assert track_filename(3, "A/B", ".m4a", disc_number=2, multi_disc=True) == "2-03 - A_B.m4a"
