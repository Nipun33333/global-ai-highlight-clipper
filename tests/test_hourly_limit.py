"""Quota tests: hourly and manual workflow runs share a persisted limit."""
from dataclasses import replace

from app.config import Settings
from app.state import hour_has_attempt, load, reserve_hour, save


def test_hour_reservation_survives_state_reload(tmp_path):
    path = tmp_path / 'state.json'
    state = {'clips': {}}
    assert reserve_hour(state, 'youtube', '2026-11-18T08', 'a:30')
    assert not reserve_hour(state, 'youtube', '2026-11-18T08', 'b:60')
    assert reserve_hour(state, 'instagram', '2026-11-18T08', 'a:30')
    save(path, state)
    reloaded = load(path)
    assert hour_has_attempt(reloaded, 'youtube', '2026-11-18T08')
    assert hour_has_attempt(reloaded, 'instagram', '2026-11-18T08')
    assert not reserve_hour(reloaded, 'instagram', '2026-11-18T08', 'b:60')
    assert reserve_hour(reloaded, 'youtube', '2026-11-18T09', 'b:60')


def test_same_clip_once_on_each_platform_per_hour(monkeypatch, tmp_path):
    from app import main
    video = {'id': 'ABC12345678', 'title': 'GTA 6 gameplay', 'channel_id': 'channel',
             'channel_title': 'Creator', 'subscribers': 1_500_000,
             'duration': 36000, 'is_live': False, 'is_short': False,
             'chat_id': None, 'actual_start': None}
    monkeypatch.setattr(main, 'discover', lambda *a: [video])
    monkeypatch.setattr(main, 'YouTubeData', lambda _: type('YT', (), {'comments': lambda *a, **kw: []})())
    monkeypatch.setattr(main, 'build_candidates', lambda *a, **kw: [])
    monkeypatch.setattr(main, 'non_overlapping', lambda *a, **kw: [
        {'timestamp': point, 'score': .9, 'support': 5, 'model_used': 'mock',
         'label': 'funny highlight', 'start': point - 20, 'end': point + 10}
        for point in (120, 180, 240)
    ])
    monkeypatch.setattr(main, 'find_media_source', lambda *a: '/not-a-real.mp4')
    rendered = []
    def fake_clip(_, video_id, start, duration, *args):
        rendered.append((video_id, start, duration))
        out = tmp_path / 'clip.mp4'
        out.write_bytes(b'fake mp4')
        return out
    monkeypatch.setattr(main, 'clip_media', fake_clip)
    posts = {'youtube': [], 'instagram': []}
    def yt(*a, **kw):
        posts['youtube'].append(a[0])
        return 'yt-'+str(len(posts['youtube']))
    def ig(*a, **kw):
        posts['instagram'].append(a[0])
        return 'ig-'+str(len(posts['instagram']))
    monkeypatch.setattr(main, 'upload', yt)
    monkeypatch.setattr(main, 'publish_reel', ig)
    clock = {'slot': '2026-11-18T08'}
    monkeypatch.setattr(main, 'current_utc_hour', lambda: clock['slot'])
    config = replace(Settings(), youtube_api_key='mock', oauth_token='mock',
                     auto_upload=True, instagram_auto_upload=True,
                     instagram_page_token='mock', instagram_user_id='123',
                     state_path=tmp_path/'state.json', report_path=tmp_path/'report.json',
                     output_dir=tmp_path)
    first = main.run_once(config)
    assert first['stats']['uploaded'] == first['stats']['instagram_uploaded'] == 1
    assert len(rendered) == 1
    assert posts['youtube'][0] == posts['instagram'][0]
    main.run_once(config)  # manually triggered again during same hour
    assert len(posts['youtube']) == len(posts['instagram']) == 1
    clock['slot'] = '2026-11-18T09'
    third = main.run_once(config)
    assert third['stats']['uploaded'] == third['stats']['instagram_uploaded'] == 1
    assert len(posts['youtube']) == len(posts['instagram']) == 2
    assert len(rendered) == 2
