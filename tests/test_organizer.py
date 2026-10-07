from pathlib import Path

from spotify2audio.models.options import JobOptions, OutputFormat
from spotify2audio.models.track import Track
from spotify2audio.services.organizer import MAX_PATH_LEN, Organizer


def trk(id="1", title="Title", artist="AC/DC", album="Back: In Black?", n=1, disc=1, **kw):
    return Track(spotify_id=id, title=title, artists=(artist,), album=album, track_number=n,
                 disc_number=disc, **kw)


def org(tmp_path, **kw):
    return Organizer(JobOptions(output_dir=tmp_path, **kw))


def test_standard_layout_sanitized(tmp_path):
    p = org(tmp_path).target_path(trk())
    assert p == tmp_path / "AC_DC" / "Back_ In Black_" / "01 - Title.mp3"


def test_uses_album_artist_for_folder(tmp_path):
    p = org(tmp_path).target_path(trk(album_artist="Various Artists"))
    assert p.parts[-3] == "Various Artists"


def test_format_extension(tmp_path):
    assert org(tmp_path, output_format=OutputFormat.M4A).target_path(trk()).suffix == ".m4a"


def test_flat_mode(tmp_path):
    p = org(tmp_path, create_folders=False).target_path(trk(title="Song"))
    assert p == tmp_path / "AC_DC - Song.mp3"


def test_multi_disc_numbering_is_consistent(tmp_path):
    tracks = [trk("a", "One", n=1, disc=1, album="Double"), trk("b", "Two", n=1, disc=2, album="Double")]
    o = Organizer.for_playlist(JobOptions(output_dir=tmp_path), tracks)
    assert [o.target_path(t).name for t in tracks] == ["1-01 - One.mp3", "2-01 - Two.mp3"]


def test_collision_between_different_tracks(tmp_path):
    o = org(tmp_path)
    a, b = trk("a", "Same"), trk("b", "Same")
    pa, pb = o.target_path(a), o.target_path(b)
    assert pa != pb and pb.name == "01 - Same (2).mp3"
    assert o.target_path(a) == pa                       # estable al repetir la consulta


def test_duplicate_entry_same_track_same_path(tmp_path):
    o = org(tmp_path)
    assert o.target_path(trk("a")) == o.target_path(trk("a"))


def test_long_names_fit_windows_limit(tmp_path):
    long = "x" * 300
    p = org(tmp_path).target_path(trk(title=long, artist=long, album=long))
    assert len(str(p)) <= MAX_PATH_LEN


def test_exists(tmp_path):
    o = org(tmp_path)
    t = trk()
    assert not o.exists(t)
    p = o.target_path(t)
    p.parent.mkdir(parents=True)
    p.write_bytes(b"")
    assert not o.exists(t)                              # vacío = no cuenta
    p.write_bytes(b"data")
    assert o.exists(t)
