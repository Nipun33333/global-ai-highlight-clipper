"""Privately upload a 30-second clip from a LOCAL approved video on Windows.

No YouTube video download or GitHub Secrets required. You must own the footage
or have permission to upload it. The user selects the video and Google account.

From your repository root (PowerShell):
    py scripts/upload_local_mp4.py --video "E:\Videos\my-gta6-gameplay.mp4" --title "GTA VI gameplay #Shorts"
Requires installed Python dependencies and ffmpeg on PATH.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from app.media import clip_media
from app.uploader import upload

SCOPE = "https://www.googleapis.com/auth/youtube.upload"
ALLOWED_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm"}


def validate_file(value: str) -> Path:
    path = Path(value).expanduser().resolve()
    if path.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise ValueError("Input must be a local MP4/MOV/MKV/WebM video.")
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError("Video not found or empty. Enter the full local file path.")
    return path


def get_oauth_token(client_path: Path, token_path: Path) -> str:
    """Use a local token if valid; otherwise sign in using user's own browser."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow

    credentials = None
    if token_path.is_file():
        try:
            credentials = Credentials.from_authorized_user_file(str(token_path), scopes=[SCOPE])
            if credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
            if not credentials.valid:
                credentials = None
        except Exception:
            credentials = None
    if credentials is None:
        if not client_path.is_file():
            raise ValueError("OAuth Desktop JSON missing. Put client_secret.json in this project folder.")
        print("Google authorization will open in your browser. Select your intended YouTube channel.")
        flow = InstalledAppFlow.from_client_secrets_file(str(client_path), [SCOPE])
        credentials = flow.run_local_server(port=0, prompt="consent", access_type="offline")
    if not credentials.valid:
        raise RuntimeError("Google authorization did not complete.")
    if not credentials.refresh_token:
        raise RuntimeError("Google did not provide a refresh token; revoke the old app consent and retry.")
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(credentials.to_json(), encoding="utf8")
    return credentials.to_json()


def run(video: str, title: str, start: float, client_json: str,
        token_file: str, confirmed: bool = False) -> str:
    path = validate_file(video)
    if start < 0:
        raise ValueError("Start seconds must be >= 0.")
    if not title.strip():
        raise ValueError("Provide a truthful video title.")
    if not shutil.which("ffmpeg"):
        raise RuntimeError("FFmpeg not installed. Windows: winget install --id Gyan.FFmpeg")
    print(f"Local input: {path.name}")
    print(f"Selected clip: start {start:g}s, length 30s, vertical 9:16.")
    print("You are responsible for confirming this is real GTA VI gameplay and you may upload it.")
    print("Destination: the YouTube channel selected during Google OAuth; privacy: PRIVATE.")
    if not confirmed and input("Type UPLOAD to continue (anything else cancels): ").strip() != "UPLOAD":
        raise RuntimeError("Upload cancelled by user.")
    oauth_json = get_oauth_token(Path(client_json), Path(token_file))
    # clip_media does not fetch YouTube: it reads the local video file using FFmpeg.
    out = clip_media(str(path), "localGTA6v1", float(start), 30.0, Path("output"), "vertical")
    result = upload(
        out, oauth_json, title.strip()[:100],
        "Original/approved GTA VI gameplay footage. #GTA6 #GTAVI #Shorts",
        privacy="private",
    )
    return f"https://www.youtube.com/watch?v={result}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", required=True, help="Full path to local gameplay MP4/MOV/MKV/WebM")
    parser.add_argument("--title", default="GTA VI gameplay highlight #Shorts")
    parser.add_argument("--start", type=float, default=0, help="Clip starting second")
    parser.add_argument("--client-json", default="client_secret.json", help="OAuth Desktop JSON")
    parser.add_argument("--token-file", default=".youtube_oauth_token.json", help="Local OAuth cache")
    args = parser.parse_args()
    try:
        url = run(args.video, args.title, args.start, args.client_json, args.token_file)
    except (OSError, RuntimeError, ValueError, KeyboardInterrupt) as exc:
        # Never print Google tokens, signed URLs, or raw network exceptions.
        print("Upload did not complete. " + (str(exc) if type(exc) in (OSError, ValueError, RuntimeError)
                                            and "token" not in str(exc).lower()
                                            else type(exc).__name__), file=sys.stderr)
        return 1
    except Exception as exc:
        print("Upload failed: " + type(exc).__name__ + ". Check OAuth permissions and account.", file=sys.stderr)
        return 1
    print("SUCCESS! Private YouTube upload confirmed:")
    print(url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
