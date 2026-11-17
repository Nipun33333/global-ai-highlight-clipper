import subprocess
import pytest
from app.gta6 import is_gta6_gameplay_video
from app.media import MediaAccessError, classify_media_error, clip_youtube_section
from app.gemini import GeminiRouter

@pytest.mark.parametrize("title",["GTA 6 GAMEPLAY LIVE","Grand Theft Auto VI First Gameplay","GTA VI gameplay walkthrough"])
def test_gameplay_accepted(title):assert is_gta6_gameplay_video(title)
@pytest.mark.parametrize("title",["GTA 6 RELEASE COUNTDOWN LIVE","GTA 6 launch times","GTA 6 gameplay trailer","GTA 6 footage leak","GTA 5 mods with GTA 6 gameplay","GTA 6 LIVE","Grand Theft Auto VI reaction","GTA V gameplay"])
def test_not_gameplay(title):assert not is_gta6_gameplay_video(title)
def test_restriction_reason_is_sanitized():
    e=classify_media_error("Sign in to confirm you're not a bot; secret=xyz")
    assert e.reason=="youtube_bot_check" and "secret" not in str(e)
def test_segment_block_error(monkeypatch,tmp_path):
    def denied(*a,**kw):raise subprocess.CalledProcessError(1,"yt-dlp",stderr="Sign in to confirm you're not a bot")
    monkeypatch.setattr("app.media.subprocess.run",denied)
    with pytest.raises(MediaAccessError,match="youtube_bot_check"):clip_youtube_section("ABC12345678",30,30,tmp_path)
def test_gemini_404_skips_model_for_run():
    router=GeminiRouter("test",("gemini-2.5-flash","gemini-3-flash-preview"))
    router._discovered=list(router.model_ids)
    class R:
        def __init__(self,c,b):self.status_code=c;self.body=b
        def raise_for_status(self):assert self.status_code<400
        def json(self):return self.body
    called=[]
    class S:
        def post(self,url,**kw):
            called.append(url)
            assert kw["json"]["generationConfig"]["maxOutputTokens"]>=512
            if "2.5-flash" in url:return R(404,{})
            return R(200,{"candidates":[{"content":{"parts":[{"text":'{"score":0.9,"label":"Audience hype"}'}]}}]})
    router.session=S()
    x={"timestamp":45,"support":4,"heuristic_score":0.5,"sample_comments":["wow"]}
    assert router.evaluate(x)["model_used"]=="gemini-3-flash-preview"
    assert router.evaluate(x)["model_used"]=="gemini-3-flash-preview"
    assert sum("2.5-flash" in u for u in called)==1
