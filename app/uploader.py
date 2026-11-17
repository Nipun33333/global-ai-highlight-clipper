"""Optional OAuth upload to operator's own YouTube channel."""
import json
from pathlib import Path


def upload(path: Path, oauth_json: str, title: str, description: str, privacy: str = "private") -> str:
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    if privacy not in {"private", "unlisted", "public"}:
        raise ValueError("Unexpected privacy value")
    creds = Credentials.from_authorized_user_info(json.loads(oauth_json), scopes=["https://www.googleapis.com/auth/youtube.upload"])
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    if not creds.valid:
        raise RuntimeError("YouTube OAuth token invalid/expired; rerun scripts/oauth_setup.py")
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
    request = youtube.videos().insert(
        part="snippet,status",
        body={"snippet": {"title": title[:100], "description": description[:5000], "categoryId": "20"},
              "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False}},
        media_body=MediaFileUpload(str(path), mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True),
    )
    response = None
    while response is None:
        _, response = request.next_chunk()
    return response["id"]
