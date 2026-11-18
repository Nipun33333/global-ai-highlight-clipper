from pathlib import Path
import pytest
from scripts import upload_local_mp4 as local


def test_local_file_validation_accepts_video(tmp_path):
    p = tmp_path / "My GTA VI gameplay.mp4"
    p.write_bytes(b"test")
    assert local.validate_file(str(p)) == p.resolve()


@pytest.mark.parametrize("name", ["missing.mp4", "clip.exe", "../no.mov"])
def test_rejects_missing_or_unsafe_input(tmp_path, name):
    with pytest.raises(ValueError):
        local.validate_file(str(tmp_path / name))


def test_local_upload_private_only(monkeypatch, tmp_path):
    p = tmp_path / "legit.mp4"
    p.write_bytes(b"test")
    events = []
    monkeypatch.setattr(local.shutil, "which", lambda prog: "/usr/bin/ffmpeg")
    monkeypatch.setattr(local, "get_oauth_token", lambda *args: '{"refresh_token":"fake"}')
    def clipped(src, video_id, start, seconds, output_dir, fmt):
        events.append(("clip", video_id, start, seconds, fmt))
        assert src == str(p.resolve())
        target = tmp_path / "out.mp4"
        target.write_bytes(b"mock video")
        return target
    def uploaded(path, oauth_json, title, description, privacy):
        events.append(("upload", privacy, title))
        return "abc12345678"
    monkeypatch.setattr(local, "clip_media", clipped)
    monkeypatch.setattr(local, "upload", uploaded)
    result = local.run(str(p), "Real GTA VI gameplay", 15, "client_secret.json",
                       ".youtube_oauth_token.json", confirmed=True)
    assert result == "https://www.youtube.com/watch?v=abc12345678"
    assert events[0] == ("clip", "localGTA6v1", 15, 30, "vertical")
    assert events[1] == ("upload", "private", "Real GTA VI gameplay")


def test_local_upload_requires_explicit_confirmation(monkeypatch, tmp_path):
    p = tmp_path / "game.mp4"
    p.write_bytes(b"test")
    monkeypatch.setattr(local.shutil, "which", lambda prog: "/usr/bin/ffmpeg")
    monkeypatch.setattr("builtins.input", lambda prompt: "NO")
    monkeypatch.setattr(local, "get_oauth_token", lambda *args: pytest.fail("should not login"))
    with pytest.raises(RuntimeError, match="cancelled"):
        local.run(str(p), "Gameplay", 0, "client_secret.json", ".youtube_oauth_token.json")


def test_local_upload_requires_ffmpeg(monkeypatch, tmp_path):
    p = tmp_path / "game.mp4"
    p.write_bytes(b"test")
    monkeypatch.setattr(local.shutil, "which", lambda prog: None)
    with pytest.raises(RuntimeError, match="FFmpeg"):
        local.run(str(p), "Gameplay", 0, "client_secret.json", ".youtube_oauth_token.json",
                  confirmed=True)
