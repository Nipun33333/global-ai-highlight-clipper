"""Run on YOUR computer only; never in public GitHub Actions logs.

Download OAuth desktop client JSON from Google Cloud and name it client_secret.json.
OAuth app must have YouTube Data API v3 enabled and 'youtube.upload' scope.
"""
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

client_file = Path("client_secret.json")
if not client_file.exists():
    raise SystemExit("Missing client_secret.json. See docs/SETUP.md")
flow = InstalledAppFlow.from_client_secrets_file(str(client_file), ["https://www.googleapis.com/auth/youtube.upload"])
creds = flow.run_local_server(port=0)
output = Path(".youtube_oauth_token.json")
output.write_text(creds.to_json(), encoding="utf8")
print(f"Saved refresh token locally to {output}. Add its entire JSON to GitHub secret YOUTUBE_OAUTH_TOKEN.")
print("NEVER commit either the client_secret.json file or the OAuth token JSON.")
