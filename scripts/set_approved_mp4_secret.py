"""Securely save an authorized direct MP4 URL as a GitHub Actions secret.

PowerShell, from repository root:
    py scripts/set_approved_mp4_secret.py
Requires a previous "gh auth login".
"""
import getpass
import shutil
import subprocess
import sys

# Running by script path puts /scripts on sys.path, not necessarily repository root.
from urllib.parse import urlparse


REPO = "Nipun33333/global-ai-highlight-clipper"


def is_approved_url(value: str) -> bool:
    p = urlparse(value)
    return (p.scheme == "https" and bool(p.hostname)
            and not p.username and not p.password
            and p.path.lower().endswith(".mp4")
            and p.hostname.lower() not in {
                "youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be",
                "drive.google.com", "www.drive.google.com",
            })


def main():
    if not shutil.which("gh"):
        print("GitHub CLI missing. Install it and run gh auth login.")
        return 1
    print("Enter a direct HTTPS .mp4 URL of footage you may upload.")
    print("YouTube watch links and Google Drive sharing pages do not work.")
    url = getpass.getpass("MP4 URL (hidden): ").strip()
    if not is_approved_url(url):
        print("Invalid direct HTTPS .mp4 URL.")
        return 1
    try:
        completed = subprocess.run(
            ["gh", "secret", "set", "APPROVED_GTA6_MP4_URL", "--repo", REPO],
            input=url, text=True, capture_output=True, timeout=90,
        )
    except (OSError, subprocess.TimeoutExpired):
        print("Could not reach GitHub CLI. Check network and login.")
        return 1
    if completed.returncode:
        print("Secret was not saved; run gh auth login and check your repository permissions.")
        return 1
    print("SUCCESS: APPROVED_GTA6_MP4_URL stored as a GitHub Actions Secret.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
