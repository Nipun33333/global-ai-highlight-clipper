#!/usr/bin/env python3
"""Create YouTube OAuth refresh credentials and securely save as a GitHub Actions secret.

Windows PowerShell prerequisites:
    winget install --id GitHub.cli --source winget
    # Open a NEW PowerShell terminal
    gh auth login
    py -m pip install google-auth-oauthlib
    py scripts/setup_youtube_oauth_github.py

The downloaded Desktop OAuth client JSON should be named client_secret*.json
and stored in the project directory or Downloads. Use --client-json PATH
to choose a file explicitly. Never commit this file or the returned token.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO = "Nipun33333/global-ai-highlight-clipper"
SCOPE = "https://www.googleapis.com/auth/youtube.upload"


def find_client(path_arg: str | None) -> Path:
    if path_arg:
        path = Path(path_arg).expanduser()
        if not path.is_file():
            raise RuntimeError(f"Client JSON file not found: {path}")
        return path
    found = {}
    for folder in (Path.cwd(), Path(__file__).resolve().parent, Path.home() / "Downloads"):
        if folder.is_dir():
            for p in folder.glob("client_secret*.json"):
                if p.is_file():
                    found[str(p.resolve())] = p
    if not found:
        raise RuntimeError("No client_secret*.json in current folder/Downloads. Use --client-json PATH.")
    if len(found) != 1:
        print("Multiple client files detected; specify one with --client-json:")
        for p in found.values():
            print(f"  {p}")
        raise RuntimeError("Ambiguous OAuth client JSON.")
    return next(iter(found.values()))


def gh(args: list[str], payload: str | None = None) -> str:
    result = subprocess.run(
        ["gh", *args], input=payload, text=True, capture_output=True,
        encoding="utf-8", check=False, timeout=90
    )
    if result.returncode:
        if payload is not None:
            raise RuntimeError(f"Could not save GitHub secret (exit {result.returncode}). Check gh login/repo access.")
        raise RuntimeError((result.stderr or "GitHub CLI command failed")[:200])
    return result.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client-json", help="Downloaded Google Desktop app client JSON path")
    parser.add_argument("--repo", default=REPO, help="Target GitHub repository")
    parser.add_argument("--also-store-client-json", action="store_true",
                        help="Also store original client JSON in optional YOUTUBE_OAUTH_CLIENT_JSON secret")
    args = parser.parse_args()

    try:
        path = find_client(args.client_json)
        client_json = json.loads(path.read_text(encoding="utf-8-sig"))
        installed = client_json.get("installed", {})
        if not installed.get("client_id") or not installed.get("client_secret"):
            raise RuntimeError("Wrong JSON: download a Desktop application OAuth client JSON, not an API key.")
        if not shutil.which("gh"):
            raise RuntimeError("Install GitHub CLI using: winget install --id GitHub.cli --source winget")
        try:
            gh(["auth", "status", "-h", "github.com"])
        except RuntimeError:
            raise RuntimeError("Authenticate GitHub CLI first: gh auth login")
        actual = gh(["repo", "view", args.repo, "--json", "nameWithOwner", "--jq", ".nameWithOwner"])
        if actual.casefold() != args.repo.casefold():
            raise RuntimeError("GitHub repository ownership/name check failed")

        try:
            from google_auth_oauthlib.flow import InstalledAppFlow
        except ImportError:
            raise RuntimeError("Install dependency: py -m pip install google-auth-oauthlib")
        print(f"Using OAuth file: {path.name}")
        print(f"Saving to GitHub repository: {args.repo}")
        print("Google will open in your browser. Sign in as the intended YouTube channel owner.")
        flow = InstalledAppFlow.from_client_config(client_json, [SCOPE])
        credentials = flow.run_local_server(
            host="localhost", port=0, open_browser=True, prompt="consent", access_type="offline"
        )
        if not credentials.refresh_token:
            raise RuntimeError("Google did not provide a refresh token. Retry after revoking old app consent.")
        # Credentials JSON contains access/refresh tokens plus client ID/secret.
        # Send only on stdin, never as shell args or stdout.
        gh(["secret", "set", "YOUTUBE_OAUTH_TOKEN", "--repo", args.repo],
           payload=credentials.to_json())
        print("SUCCESS: GitHub Actions secret YOUTUBE_OAUTH_TOKEN updated.")
        if args.also_store_client_json:
            gh(["secret", "set", "YOUTUBE_OAUTH_CLIENT_JSON", "--repo", args.repo],
               payload=json.dumps(client_json))
            print("SUCCESS: Optional YOUTUBE_OAUTH_CLIENT_JSON secret updated.")
        print("Do not enable AUTO_UPLOAD until a private publishing test succeeds.")
        return 0
    except (RuntimeError, OSError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        print(f"Setup stopped: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
