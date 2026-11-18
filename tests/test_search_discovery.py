"""Regression tests for search query planning and GTA VI metadata-based detection."""
import pytest
from app.gta6 import is_gta6_gameplay_video
from app.youtube import YouTubeData, clean_search_terms, discover

@pytest.mark.parametrize("title,description,expected", [
    ("GTA 6 Gameplay LIVE", "", True),
    ("Grand Theft Auto VI gameplay part 1", "", True),
    ("GTA 6 LIVE", "Playing GTA 6 gameplay with my community!", True),
    ("GTA VI first episode", "Welcome to our GTA VI playthrough", True),
    ("GTA 6 LIVE", "GTA 6 release date countdown stream", False),
    ("GTA 6 RELEASE COUNTDOWN LIVE", "Watch actual gameplay right now", False),
    ("GTA VI gameplay trailer", "Full gameplay", False),
    ("GTA VI NEWS", "Gameplay discussion and reaction", False),
    ("GTA V modded with GTA 6 gameplay", "real game", False),
    ("GTA 6 official launch", "Gameplay stream", False),
    ("GTA 6", "The best gameplay ever", False)
])
def test_gameplay_metadata(title, description, expected):
    assert is_gta6_gameplay_video(title, description) is expected


def test_search_uses_50_results_recent_first(monkeypatch):
    yt=YouTubeData("dummy")
    captured=[]
    def fake_get(endpoint, **params):
        captured.append((endpoint,params))
        return {"items":[]}
    monkeypatch.setattr(yt,"get",fake_get)
    yt.search("GTA VI gameplay",mode="live")
    yt.search("GTA VI gameplay",mode="long")
    yt.search("GTA VI gameplay",mode="short")
    assert [x[1]["maxResults"] for x in captured]==[50,50,50]
    assert [x[1]["order"] for x in captured]==["date","date","date"]
    assert captured[0][1]["eventType"]=="live"
    assert captured[1][1]["videoDuration"]=="long"
    assert captured[2][1]["videoDuration"]=="short"


def test_no_conflicting_keywords_or_extra_searches():
    assert clean_search_terms(("GTA 6 gameplay live", "GTA VI gameplay long", "GTA 6 gameplay shorts")) == (
        "GTA 6 gameplay", "GTA VI gameplay"
    )
    class FakeYT:
        def __init__(self):
            self.queries=[]
        def search(self,query,mode,region):
            self.queries.append((query,mode,region))
            return []
    youtube=FakeYT()
    stats={}
    assert discover(youtube,("GTA 6 gameplay live","GTA VI gameplay long","GTA 6 gameplay shorts"),
                    ("US","IN"),1_000_000,36000,max_calls=3,diagnostics=stats)==[]
    assert len(youtube.queries)==3
    for q,mode,region in youtube.queries:
        assert not q.lower().endswith(" short")
        assert not q.lower().endswith(" long")
        assert not q.lower().endswith(" live")
    assert youtube.queries[0][1]=="live"
    assert youtube.queries[1][1]=="long"
    assert youtube.queries[2][1]=="short"
    assert stats["search_calls"]==3


def test_descriptor_live_and_duration_and_sub_filter():
    class FakeYT:
        def search(self,query,mode,region=None):
            return [{"id":{"videoId":"ABC12345678"}}] if mode=="live" else []
        def video_details(self,ids):
            return [{"id":"ABC12345678",
                     "snippet":{"title":"GTA 6 LIVE","description":"GTA VI gameplay with friends",
                                "channelId":"ch","channelTitle":"Example","liveBroadcastContent":"live"},
                     "contentDetails":{"duration":"PT0S"},
                     "liveStreamingDetails":{"activeLiveChatId":"chatid","actualStartTime":"2026-11-19T00:00:00Z"}}]
        def channel_subs(self,ids):
            return {"ch":1_200_000}
    stats={}
    a=discover(FakeYT(),("GTA 6 gameplay",),(),1_000_000,36000,3,"GTA 6 gameplay",stats)
    assert len(a)==1 and a[0]["is_live"]
    assert a[0]["description"]=="GTA VI gameplay with friends"
    assert stats["selected"]==1
