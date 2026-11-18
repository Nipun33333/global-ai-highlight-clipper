import json
import pytest

from app.gta6 import is_gta6_gameplay_video
from app.media import MediaAccessError, clip_media
from scripts import upload_approved_mp4 as approved


@pytest.mark.parametrize("title,description,tags", [
    ("This Game Changed My Life, The Final GTA Online Stream Before GTA 6, What A Long Road", "GTA 6 gameplay", []),
    ("GTA 6 LIVE, NOV 19, 12AM (BRAZIL TIME) #gta6 #gameplay", "Playing GTA 6 gameplay", ["gameplay"]),
    ("GTA VI gameplay trailer", "GTA 6 gameplay", []),
    ("GTA VI in FiveM gameplay", "GTA 6 game", []),
    ("GTA 6 LIVE before release", "GTA 6 gameplay", []),
    ("GTA VI release livestream gameplay", "", []),
    ("GTA 6 GTA Online full gameplay", "", []),
    ("GTA VI GTA RP gameplay", "gameplay", []),
])
def test_recent_false_positives_rejected(title, description, tags):
    assert not is_gta6_gameplay_video(title, description, tags)


@pytest.mark.parametrize("title,description", [
    ("GTA VI gameplay playthrough #1", ""),
    ("Grand Theft Auto VI gameplay episode 1", "Playing the game"),
    ("GTA 6 LIVE", "Playing GTA VI gameplay with friends"),
])
def test_clear_gameplay_candidates_still_pass(title, description):
    assert is_gta6_gameplay_video(title, description)


@pytest.mark.parametrize("url,expected", [
    ("https://cdn.example.com/owned.mp4", True),
    ("https://cdn.example.com/owned.mp4?token=private", True),
    ("https://www.youtube.com/watch?v=ABCDEFGHIJK", False),
    ("https://drive.google.com/file/d/example/view", False),
    ("http://cdn.example.com/owned.mp4", False),
    ("https://user:pass@cdn.example.com/owned.mp4", False),
    ("https://cdn.example.com/playlist.m3u8", False),
])
def test_approved_url_validation(url, expected):
    assert approved.direct_https_media_url(url) is expected


def test_private_upload_reserves_hour_and_does_not_leak_signed_url(monkeypatch, tmp_path):
    monkeypatch.setenv("STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setenv("APPROVED_GTA6_MP4_URL", "https://cdn.example.com/owned.mp4?secret=private")
    monkeypatch.setenv("YOUTUBE_OAUTH_TOKEN", "fake-token")
    monkeypatch.setenv("APPROVED_UPLOAD_TITLE", "GTA VI gameplay")
    monkeypatch.setenv("APPROVED_UPLOAD_START", "0")
    calls = []
    def render(url, *args):
        calls.append(("clip", url))
        path = tmp_path / "clip.mp4"
        path.write_bytes(b"mock")
        return path
    def publish(path, token, title, description, privacy):
        calls.append(("upload", privacy))
        return "abcDEFGHIJK"
    monkeypatch.setattr(approved, "clip_media", render)
    monkeypatch.setattr(approved, "upload", publish)
    first = approved.run()
    assert first["status"] == "published_private"
    assert first["youtube_url"] == "https://www.youtube.com/watch?v=abcDEFGHIJK"
    assert calls[-1] == ("upload", "private")
    assert approved.run()["status"] == "youtube_hourly_limit_already_used"
    assert len([x for x in calls if x[0] == "upload"]) == 1
    assert "secret=private" not in json.dumps(first)


def test_missing_source_does_not_try_upload(monkeypatch, tmp_path):
    monkeypatch.setenv("STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.delenv("APPROVED_GTA6_MP4_URL", raising=False)
    monkeypatch.setenv("YOUTUBE_OAUTH_TOKEN", "fake-token")
    monkeypatch.setattr(approved, "upload", lambda *a, **kw: pytest.fail("should not upload"))
    assert approved.run()["status"] == "missing_or_invalid_direct_mp4_url"


def test_ffmpeg_error_does_not_leak_signed_url(monkeypatch, tmp_path):
    import subprocess
    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, args[0],
            stderr="https://cdn.example.com/owned.mp4?secret=private not available")
    monkeypatch.setattr("app.media.subprocess.run", fail)
    with pytest.raises(MediaAccessError) as exc:
        clip_media("https://cdn.example.com/owned.mp4?secret=private",
                   "ABCDEFGHIJK", 0, 30, tmp_path)
    assert "secret=private" not in str(exc.value)
