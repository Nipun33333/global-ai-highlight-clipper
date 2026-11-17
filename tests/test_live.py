from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.config import Settings
from app.live import buffer_window
from app.youtube import discover


def test_buffer_window_selects_only_30s_inside_live_capture():
    broadcast = datetime(2026, 11, 17, 10, 0, tzinfo=timezone.utc)
    record = broadcast + timedelta(hours=1)
    w = buffer_window(3620, 3650, broadcast, record, recorded_seconds=150)
    assert w and w.start == 20 and w.duration == 30
    assert buffer_window(3599, 3629, broadcast, record, recorded_seconds=150) is None
    assert buffer_window(3725, 3760, broadcast, record, recorded_seconds=150) is None
    shifted = buffer_window(3620, 3650, broadcast, record, 150, clock_shift_seconds=5)
    assert shifted and shifted.start == 25


def test_hourly_discovery_always_searches_currently_live_first():
    class FakeYouTube:
        def __init__(self):
            self.queries = []
        def search(self, query, mode, region):
            self.queries.append((query, mode, region))
            return [{"id": {"videoId": "ABC12345678"}}] if mode == "live" else []
        def video_details(self, ids):
            return [{"id": "ABC12345678", "snippet": {
                "title": "GTA 6 LIVE GAMEPLAY", "channelId": "channel-a",
                "channelTitle": "Creator", "liveBroadcastContent": "live"},
                "contentDetails": {"duration": "PT0S"},
                "liveStreamingDetails": {
                    "activeLiveChatId": "chat-a", "actualStartTime": "2026-11-17T08:00:00Z"
                }}]
        def channel_subs(self, ids):
            return {"channel-a": 1_200_000}
    yt = FakeYouTube()
    matches = discover(yt, ("GTA 6 long", "GTA VI short"), ("US", "IN"), 1_000_000, 36000,
                       max_calls=3, live_search_term="GTA 6 gameplay live")
    assert yt.queries[0][0:2] == ("GTA 6 gameplay live", "live")
    assert len(yt.queries) == 3
    assert matches[0]["is_live"] is True
    assert matches[0]["chat_id"] == "chat-a"


def test_workflow_analyzes_and_renders_from_current_live_buffer(monkeypatch, tmp_path):
    import app.main as main
    now = datetime.now(timezone.utc)
    broadcast_start = now - timedelta(seconds=200)
    buffered_from = now - timedelta(seconds=120)  # capture covers 80..230s from start
    video = {
        "id": "ABC12345678", "title": "GTA VI GAMEPLAY LIVE",
        "channel_id": "ch", "channel_title": "Big Creator", "subscribers": 1_500_000,
        "duration": 0, "is_live": True, "is_short": False, "chat_id": "chat",
        "actual_start": broadcast_start.isoformat(),
    }
    monkeypatch.setattr(main, "discover", lambda *args: [video])
    class MockYouTube:
        def __init__(self, api_key):
            pass
        def live_chat(self, chat_id, start, **kwargs):
            assert chat_id == "chat"
            return [{"id": "x", "text": "OMG epic 🔥", "seconds": 150},
                    {"id": "y", "text": "insane wow", "seconds": 155}]
    monkeypatch.setattr(main, "YouTubeData", MockYouTube)
    record = tmp_path / "captured_live.mkv"
    record.write_bytes(b"mock")
    class FakeLiveBuffer:
        def __init__(self, video_id, seconds):
            self.started_at = buffered_from
            self.recorded_seconds = 150
        def __enter__(self):
            return self
        def wait(self):
            return record
        def __exit__(self, *args):
            pass
    monkeypatch.setattr(main, "LiveBuffer", FakeLiveBuffer)
    captured = []
    def fake_clip(source, video_id, start, duration, output_dir, fmt):
        captured.append((source, start, duration))
        output_dir.mkdir(exist_ok=True)
        result = output_dir / "mock.mp4"
        result.write_bytes(b"mock mp4")
        return result
    monkeypatch.setattr(main, "clip_media", fake_clip)
    monkeypatch.setattr(main, "clip_youtube_section", lambda *args: pytest.fail("Must use buffered source"))
    settings = replace(Settings(), youtube_api_key="dummy", gemini_api_key="", live_clock_shift=0,
                       state_path=tmp_path / "state.json", report_path=tmp_path / "report.json",
                       output_dir=tmp_path / "clips", auto_upload=False)
    result = main.run_once(settings)
    assert result["stats"]["live_found"] == 1
    assert result["stats"]["live_analyzed"] == 1
    assert result["stats"]["live_buffered"] == 1
    assert result["stats"]["clipped"] == 1
    assert captured[0][0] == str(record)
    assert captured[0][2] == 30


def test_failed_live_capture_still_analyzes_chat(monkeypatch, tmp_path):
    import app.main as main
    monkeypatch.setattr(main, "discover", lambda *args: [{
        "id":"ABC12345678", "title":"GTA 6 gameplay live", "channel_id":"ch", "channel_title":"Creator",
        "subscribers":1000000, "duration":0, "is_live": True, "is_short": False,
        "chat_id":"chat", "actual_start": "2026-11-17T00:00:00Z"
    }])
    class DummyYT:
        def __init__(self, key):
            pass
        def live_chat(self, *a, **kw):
            return []
    class ErrorBuffer:
        def __init__(self, *args):
            pass
        def __enter__(self):
            raise RuntimeError("capture unavailable")
        def __exit__(self, *args):
            pass
    monkeypatch.setattr(main, "YouTubeData", DummyYT)
    monkeypatch.setattr(main, "LiveBuffer", ErrorBuffer)
    settings = replace(Settings(), youtube_api_key="dummy", gemini_api_key="",
                       state_path=tmp_path / "state.json", report_path=tmp_path / "report.json",
                       output_dir=tmp_path / "clips")
    result = main.run_once(settings)
    assert result["stats"]["live_analyzed"] == 1
    assert "capture_note" in result["videos"][0]
