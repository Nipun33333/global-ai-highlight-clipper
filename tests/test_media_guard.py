from app.media import find_media_source, section_command
import pytest


def test_media_source_map_no_channel_allowlist(monkeypatch, tmp_path):
    vid = "ABC12345678"
    assert find_media_source(vid, tmp_path) is None
    monkeypatch.setenv("MEDIA_SOURCE_MAP_JSON", '{"ABC12345678":"https://cdn.example/media.mp4"}')
    assert find_media_source(vid, tmp_path) == "https://cdn.example/media.mp4"
    assert find_media_source("../passwords", tmp_path) is None
    (tmp_path / f"{vid}.mp4").write_bytes(b"mp4 placeholder")
    assert find_media_source(vid, tmp_path) == str((tmp_path / f"{vid}.mp4").resolve())


def test_section_command_fetches_only_window(tmp_path):
    cmd = section_command("ABC12345678", 36005, 30, tmp_path / "segment.%(ext)s")
    assert "--download-sections" in cmd
    assert "*36005.000-36035.000" in cmd
    assert "--force-keyframes-at-cuts" in cmd
    assert "https://www.youtube.com/watch?v=ABC12345678" in cmd
    with pytest.raises(ValueError):
        section_command("../../bad", 0, 30, tmp_path / "x")
