from dataclasses import replace
from pathlib import Path

import pytest

from app.config import Settings
from app.instagram import InstagramPublishError, publish_reel
from app.state import load, mark, platform_uploaded


class Response:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload


class FakeMeta:
    def __init__(self, fail_stage=None, hostile_uri=False):
        self.calls = []
        self.fail_stage = fail_stage
        self.hostile_uri = hostile_uri

    def post(self, url, headers=None, data=None, **kwargs):
        assert kwargs['allow_redirects'] is False
        if url.endswith('/media'):
            self.calls.append('create')
            assert data['media_type'] == 'REELS'
            assert data['upload_type'] == 'resumable'
            assert headers['Authorization'] == 'Bearer secret'
            return Response({'id': '111', 'uri': 'https://evil.example/upload' if self.hostile_uri else 'https://rupload.facebook.com/ig-api-upload/v26.0/111'})
        if url.startswith('https://rupload.facebook.com/'):
            self.calls.append('transfer')
            assert data.read() == b'fake video bytes'
            assert headers['file_size'] == str(len(b'fake video bytes'))
            assert headers['Authorization'] == 'OAuth secret'
            return Response({'success': True}, status=500 if self.fail_stage == 'transfer' else 200)
        if url.endswith('/media_publish'):
            self.calls.append('publish')
            assert data['creation_id'] == '111'
            return Response({'id': '999'})
        raise AssertionError(url)

    def get(self, url, headers=None, params=None, **kwargs):
        self.calls.append('status')
        assert params['fields'] == 'status_code,status'
        return Response({'status_code': 'FINISHED'})


def test_local_reel_resumable_api_happy_path(tmp_path):
    file = tmp_path / 'clip.mp4'
    file.write_bytes(b'fake video bytes')
    session = FakeMeta()
    result = publish_reel(file, 'secret', '123', '#GTA6', session=session)
    assert result == '999'
    assert session.calls == ['create', 'transfer', 'status', 'publish']


def test_instagram_token_never_sent_to_untrusted_host(tmp_path):
    file = tmp_path / 'clip.mp4'
    file.write_bytes(b'fake video bytes')
    session = FakeMeta(hostile_uri=True)
    with pytest.raises(InstagramPublishError, match='unexpected upload host'):
        publish_reel(file, 'secret', '123', '#GTA6', session=session)
    assert session.calls == ['create']


def test_instagram_transfer_failure_does_not_publish(tmp_path):
    file = tmp_path / 'clip.mp4'
    file.write_bytes(b'fake video bytes')
    session = FakeMeta(fail_stage='transfer')
    with pytest.raises(InstagramPublishError, match='HTTP 500'):
        publish_reel(file, 'secret', '123', '#GTA6', session=session)
    assert session.calls == ['create', 'transfer']


def test_instagram_is_disabled_by_default_and_requires_secrets():
    config = replace(Settings(), auto_upload=False, instagram_auto_upload=False)
    config.validate()
    with pytest.raises(ValueError, match='IG_USER_ID'):
        replace(config, instagram_auto_upload=True, instagram_page_token='', instagram_user_id='').validate()
    replace(config, instagram_auto_upload=True, instagram_page_token='test', instagram_user_id='123').validate()


def test_legacy_youtube_state_is_retained_after_instagram_publish():
    state = {'clips': {}}
    mark(state, 'xyz:30', 'uploaded_private', 'youtube-legacy-id')
    assert platform_uploaded(state, 'xyz:30', 'youtube')
    # Adding Instagram must not lose the old-format YouTube published marker.
    from app.state import mark_platform
    mark_platform(state, 'xyz:30', 'instagram', 'ig-123')
    mark(state, 'xyz:30', 'published')
    assert platform_uploaded(state, 'xyz:30', 'youtube')
    assert platform_uploaded(state, 'xyz:30', 'instagram')


def test_upload_on_both_platforms_and_retry_only_failed_one(monkeypatch, tmp_path):
    from app import main
    video = {'id': 'ABC12345678', 'title': 'GTA 6 amazing gameplay', 'channel_id': 'ch',
             'channel_title': 'Creator', 'subscribers': 2_000_000, 'duration': 36000,
             'is_live': False, 'is_short': False, 'chat_id': None, 'actual_start': None}
    monkeypatch.setattr(main, 'discover', lambda *args: [video])
    monkeypatch.setattr(main, 'YouTubeData', lambda api_key: type('YT', (), {'comments': lambda *a, **k: []})())
    monkeypatch.setattr(main, 'build_candidates', lambda *args, **kwargs: [])
    monkeypatch.setattr(main, 'non_overlapping', lambda *args, **kwargs: [
        {'timestamp': 100, 'score': 0.9, 'support': 5, 'model_used': 'mock',
         'label': 'GTA 6 reveal', 'start': 80, 'end': 110}
    ])
    monkeypatch.setattr(main, 'find_media_source', lambda *args: '/mock/video.mp4')
    def fake_clip(*args):
        path = tmp_path / 'test_clip.mp4'
        path.write_bytes(b'fake video bytes')
        return path
    monkeypatch.setattr(main, 'clip_media', fake_clip)
    yt_ids = []
    ig_ids = []
    def fake_yt(*args, **kwargs):
        yt_ids.append('yt001')
        return 'yt001'
    def fake_ig(*args, **kwargs):
        ig_ids.append('called')
        if len(ig_ids) == 1:
            raise RuntimeError('temporary instagram failure')
        return 'ig001'
    monkeypatch.setattr(main, 'upload', fake_yt)
    monkeypatch.setattr(main, 'publish_reel', fake_ig)

    config = replace(Settings(), youtube_api_key='test', gemini_api_key='',
                     oauth_token='youtube-mock', auto_upload=True,
                     instagram_auto_upload=True, instagram_page_token='ig-mock',
                     instagram_user_id='123', state_path=tmp_path / 'state.json',
                     report_path=tmp_path / 'report.json', output_dir=tmp_path)
    clock = {'hour': '2026-11-18T08'}
    monkeypatch.setattr(main, 'current_utc_hour', lambda: clock['hour'])
    first = main.run_once(config)
    assert first['stats']['uploaded'] == 1
    assert first['stats']['instagram_uploaded'] == 0
    assert first['videos'][0]['highlights'][0]['uploads']['instagram']['status'] == 'error'

    # A second manual run in the SAME UTC hour cannot retry either platform.
    second = main.run_once(config)
    assert second['stats']['uploaded'] == 0
    assert second['stats']['instagram_uploaded'] == 0
    assert len(yt_ids) == 1 and len(ig_ids) == 1

    # The failed destination can retry one hour later without duplicating YT.
    clock['hour'] = '2026-11-18T09'
    third = main.run_once(config)
    assert third['stats']['uploaded'] == 0
    assert third['stats']['instagram_uploaded'] == 1
    assert len(yt_ids) == 1 and len(ig_ids) == 2
    state = load(config.state_path)
    assert platform_uploaded(state, 'ABC12345678:90', 'youtube')
    assert platform_uploaded(state, 'ABC12345678:90', 'instagram')
    fourth = main.run_once(config)
    assert fourth['videos'][0]['highlights'][0]['status'] == 'already_processed'
    assert len(yt_ids) == 1 and len(ig_ids) == 2
