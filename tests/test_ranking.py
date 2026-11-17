from app.ranking import extract_timecodes, build_candidates, non_overlapping
from app.youtube import duration_seconds


def test_10h_duration_and_hour_timecodes():
    assert duration_seconds("PT12H3M20S") == 43400
    assert extract_timecodes("Great 10:12:33 and 2:13", max_seconds=40000) == [36753, 133]
    assert extract_timecodes("Invalid 9:99 plus 99:99") == []


def test_timestamp_only_vod_and_positive_votes():
    msgs = [{"id":"a", "text":"1:22:10 epic 🔥"}, {"id":"b", "text":"1:22:19 crazy wow!"},
            {"id":"c", "text":"1:22:11 boring and terrible"}, {"id":"d", "text":"epic but no timecode"}]
    c = build_candidates(msgs, is_live=False, duration=39000, min_support=2)
    assert len(c) == 1 and c[0]["support"] == 2
    assert c[0]["timestamp"] == 4935
    selected = non_overlapping(c, 3, 20, 10, .3)
    assert selected[0]["start"] == 4915


def test_chat_uses_stream_relative_seconds_not_comment_post_time():
    msgs = [{"id":"1", "text":"WOW 🔥", "seconds":150.}, {"id":"2", "text":"insane!", "seconds":160.}]
    results = build_candidates(msgs, is_live=True, duration=0, min_support=2)
    assert len(results) == 1
    assert results[0]["timestamp"] == 165


def test_30s_window():
    c = [{"timestamp":60, "heuristic_score":.75, "support":3, "sample_comments":[]}]
    result = non_overlapping(c, 9, 20, 10, .35, duration=120)
    assert len(result) == 1
    assert result[0]["start"] == 40 and result[0]["end"] == 70


def test_gta6_only_title_filter():
    from app.gta6 import is_gta6_video
    assert is_gta6_video("GTA 6 FIRST GAMEPLAY LIVE")
    assert is_gta6_video("Grand Theft Auto VI stream")
    assert not is_gta6_video("GTA 5 Online live")
    assert not is_gta6_video("Random gaming highlights")
