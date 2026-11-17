# Global AI Highlight Clipper — GTA 6 Edition

GTA 6-only, worldwide YouTube highlight scanner and optional YouTube Shorts + Instagram Reels publisher. Every workflow run **first searches for GTA 6 gameplay streams currently LIVE**, then checks 10-hour-plus recordings and short videos. Source channels need at least 1,000,000 **public** subscribers. It uses timestamped positive comments / sampled live chat to find highlight candidates, Gemini free-tier models with fallback for scoring, yt-dlp section fetching and FFmpeg to make vertical **30-second Shorts** (20 seconds before a reaction window + 10 seconds after). OAuth can publish selected clips to your YouTube channel; Meta Graph API can cross-post the same local MP4 as an Instagram Reel.

This repo does **not** contain per-creator license/campaign/rights checkers or channel approval lists. The operator supplies the media access and is responsible for permission and for complying with the relevant terms. A general API key or YouTube channel account does not itself demonstrate a license for every creator's footage.

**Status: offline-tested software MVP including a live buffering path, not a guarantee of uninterrupted, zero-cost 24/7 livestream clipping.** The local unit tests validate the logic, not external video retrieval or OAuth publishing. Automated uploads are OFF by default until you configure your own channel OAuth.

## How it works

```text
GitHub Actions (hourly; manual workflow_dispatch also supported)
  -> CURRENTLY LIVE GTA 6 gameplay search (1 dedicated global search/run)
     -> creator >= 1M subscribers + GTA 6 title gate + live status
     -> start one temporary 150s live A/V buffer (yt-dlp URL + FFmpeg)
     -> simultaneously poll live chat 6 times (~20s apart)
     -> cluster positive/hype chat, Gemini rank with model fallback
     -> clip available buffered windows: 20s BEFORE + 10s AFTER
     -> fallback: try time-section extraction if outside live buffer
  -> GTA 6 10h+ recordings and <=3min Shorts (remaining 2 searches)
     -> scan explicit timecoded comments and rank highlights
     -> time-section extraction without a full 10h local download
  -> up to 9 separate 30s vertical Shorts/source (8-9 target)
  -> optionally upload the clip to your YouTube channel and/or Instagram Reels
  -> JSON report + dedup metadata committed by workflow
```

**How many Shorts?** The algorithm produces **up to 9**, with **8** as the target. It will not invent 8 scenes if comments/chat don't support them. A livestream sampled briefly every hour can easily produce fewer or zero timestamped moments. It checks the title to enforce the GTA 6 topic; title metadata cannot prove that all footage is genuinely from GTA 6.

**Live while it is airing:** By default, the first eligible live channel gets a temporary **150-second audio/video capture**, while public live chat is sampled. This is the practical way to include moments from the currently playing feed without saving a whole multi-hour broadcast. Once chat reaction timestamps have been ranked, clips are created only if their full window lies inside the captured segment. Capture is discarded when processing ends. It does not run between hourly jobs, and timestamps are only approximately synchronized with the player; live delay can be tuned with `LIVE_CLOCK_SHIFT_SECONDS`.

**No full 10-hour media file required:** For recorded uploads, `yt-dlp --download-sections` tries to fetch only each 30-second time slice. Live streams that support DVR may also allow a section fallback, but this is **not guaranteed**. A single HTTPS combined A/V playback format, exposed by yt-dlp, is needed for the temporary live buffer. The YouTube Data API itself gives metadata/live-chat messages, not media bytes.

## Quick start

Python 3.11+ and FFmpeg are required. On Windows, install FFmpeg and ensure `ffmpeg` is in `PATH`.

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m pytest -q
python scripts/demo.py
cp .env.example .env  # on Windows use: copy .env.example .env
```

Fill these in `.env`:

```dotenv
YOUTUBE_API_KEY=your_youtube_data_api_v3_key
GEMINI_API_KEY=your_gemini_key
SOURCE_MODE=yt_dlp
LIVE_SEARCH_TERM=GTA 6 gameplay live
LIVE_CAPTURE_ENABLED=true
LIVE_CAPTURE_SECONDS=150
LIVE_POLLS=6
MAX_LIVE_CAPTURES_PER_RUN=1
MAX_CLIPS_PER_VIDEO=9
TARGET_CLIPS_PER_VIDEO=8
CLIP_LEAD_SECONDS=20
CLIP_AFTER_SECONDS=10
AUTO_UPLOAD=false
UPLOAD_PRIVACY=private
INSTAGRAM_AUTO_UPLOAD=false
# Hard cap: max 1 YouTube Short + 1 Instagram Reel per UTC hour.
```

Then run:

```bash
python -m app.main
```

If you prefer your own MP4 files instead of yt-dlp, set `SOURCE_MODE=provided` and put a file at `media/<YouTube-video-id>.mp4`, or use a direct HTTPS URL in the `MEDIA_SOURCE_MAP_JSON` environment variable. That direct URL must be playable by FFmpeg (a normal YouTube watch page is not).

## Automatic upload to your channel

1. In Google Cloud, configure OAuth credentials and download Desktop client `client_secret.json` to your **local** project folder. Do not commit it.
2. Run `python scripts/oauth_setup.py` locally and authorize **your intended channel**.
3. Save the generated token JSON in GitHub Actions **secret** `YOUTUBE_OAUTH_TOKEN`.
4. Set Actions **variable** `AUTO_UPLOAD=true`. Start with `UPLOAD_PRIVACY=private`, then switch to `public` or `unlisted` when you're ready.
5. Add YouTube Data API and Gemini API keys as Actions **secrets**. Run Actions > Hourly worldwide highlight scanner > Run workflow.

The uploader makes ordinary YouTube Shorts uploads. It does **not** create a new live broadcast on your channel. YouTube may impose API verification / privacy limitations on uploads; please verify your project's current status.

## Optional Instagram Reels cross-posting

The same vertical 30-second GTA 6 clip can be posted to **both** platforms or **Instagram only**, via independent switches. Each hourly run picks at most one eligible highlight to publish to its enabled destinations; it does not upload all 8–9 candidates. It is not a live broadcast on Instagram; it is a Reel after clipping. Both publishing switches are `false` by default. Upload attempts are reserved per platform and UTC-hour in persisted state, so a manual rerun in the same hour will not trigger another post. If YouTube succeeds but Instagram fails, later runs will not knowingly repost the same clip to YouTube. A failed/ambiguous request also counts as that hour's attempt; it may be retried in a later hour.

This project uses **Meta Instagram API with Facebook Login** because its **resumable local-file upload** does not need a paid/public video host. Your account must be an **Instagram Professional (Creator/Business)** account linked to a Facebook Page. A Meta Business app / appropriate access must provide the Page access token with `instagram_basic`, `instagram_content_publish`, `pages_read_engagement` and `pages_show_list` as applicable. See [Instagram setup](docs/SETUP.md#instagram-reels-publishing). Personal-only Instagram accounts and direct Instagram username/password posting are not supported.

Add GitHub Actions **secrets** `IG_USER_ID` (Instagram professional account's numeric ID) and `INSTAGRAM_PAGE_ACCESS_TOKEN` (the Page access token), then Actions **variables** `INSTAGRAM_AUTO_UPLOAD=true` and optionally `INSTAGRAM_GRAPH_VERSION=v26.0`. To also upload YouTube Shorts, keep `AUTO_UPLOAD=true` with its own YouTube OAuth secret. Never put access tokens in public variables or repository files. Local MP4 files are uploaded via Meta container -> resumable transfer -> status polling -> publish; no third-party hosting bill is required.

A **hard limit of one upload attempt per platform per UTC hour** applies to both scheduled and manual runs (maximum 24 YouTube Shorts + 24 Instagram Reels per 24h if every hour succeeds). Publishing caps, account eligibility, token lifetime, rate limits and API policies apply. No Instagram posts can happen until credentials are configured and the Instagram switch is explicitly enabled. Real Instagram posting has **not** been end-to-end tested with your account.

## GitHub Actions settings

| Setting | Type | Purpose |
|---|---|---|
| `YOUTUBE_API_KEY` | Secret | YouTube discovery/comments |
| `GEMINI_API_KEY` | Secret | Model routing |
| `YOUTUBE_OAUTH_TOKEN` | Secret | Required to enable YouTube uploads |
| `IG_USER_ID` | Secret | Instagram professional account numeric ID |
| `INSTAGRAM_PAGE_ACCESS_TOKEN` | Secret | Linked Facebook Page access token for the Meta API |
| `INSTAGRAM_AUTO_UPLOAD` | Variable | `false` by default; set `true` to post Reels |
| `INSTAGRAM_GRAPH_VERSION` | Variable | Meta Graph API version (`v26.0` default) |
| `MEDIA_SOURCE_MAP_JSON` | Secret (optional) | Video ID -> direct FFmpeg-compatible HTTPS URL |
| `SOURCE_MODE` | Variable (optional) | `yt_dlp` (default) or `provided` |
| `LIVE_SEARCH_TERM` | Variable | Dedicated search on every workflow start (`GTA 6 gameplay live`) |
| `LIVE_CAPTURE_ENABLED` | Variable | Capture a bounded live sample concurrently with chat polling (`true`) |
| `LIVE_CAPTURE_SECONDS` | Variable | Temporary live segment length: 30–300 (default `150`) |
| `MAX_LIVE_CAPTURES_PER_RUN` | Variable | Default `1`; up to 2, sequentially |
| `LIVE_POLLS` | Variable | Samples live-chat API per stream (default `6`) |
| `LIVE_CLOCK_SHIFT_SECONDS` | Variable | Approximate playback/chat alignment tuning (default `0`) |
| `AUTO_UPLOAD` | Variable | `false` until opted in |
| `UPLOAD_PRIVACY` | Variable | `private` / `unlisted` / `public` |
| `TARGET_CLIPS_PER_VIDEO` | Variable | `8` (target only) |
| `MAX_CLIPS_PER_VIDEO` | Variable | `9` |
| `SEARCH_TERMS` | Variable | GTA 6-only search terms |
| `REGION_CODES` | Variable | Scan rotation, not exhaustive coverage |
| `FREE_MODEL_CANDIDATES` | Variable | Operator-reviewed models available on Gemini free tier |

Schedule runs at `07` minutes past every **UTC** hour (for example 08:07, 09:07 UTC), not at exactly the top of the hour. Scheduled GitHub Actions jobs can be delayed, dropped, or disabled; jobs terminate and cannot record continuously. Default 3 searches/hour means up to 72 `search.list` calls per day, within the documented default separate 100-search allowance, subject to changes and project-specific quotas. Default repository actions budget / runtime are not an unlimited free always-on machine. Uploads and media extraction might hit rate limits. See [setup](docs/SETUP.md) and [architecture](docs/ARCHITECTURE.md).

## Gemini cost and fallback

`FREE_MODEL_CANDIDATES` is a **manually reviewed free-tier model allowlist** (example: `gemini-2.5-flash-lite,gemini-2.5-flash,gemini-3-flash-preview`). Model availability and free pricing are distinct; automatically adding **every** listed model could lead to paid usage on a billed project. The router switches to the next configured model on failures and finally to a local heuristic. Only the first 2 windows per run are sent to Gemini by default, which helps stay under free API limits. A free tier does not guarantee 24-hour uninterrupted unlimited inference.

## Current technical limits

- Comments on ordinary videos do not correspond to video time unless their text contains timestamps like `2:14:20`; the comment publication time cannot identify a scene. Live chat times are approximate offsets from the stream start.
- The workflow samples live-chat streams and captures at most 1 live source by default (150s). It cannot watch every stream worldwide continuously. An 8–9 clip count is a target, not a per-run guarantee.
- A live stream can be geo-restricted, use split A/V formats, lack public chat, expose delayed playback, or prevent extraction from GitHub-hosted IP addresses. Those cases may be metadata-only.
- Buffered video/chat alignment is approximate, especially on low-latency streams, so expect timing adjustments before unattended public uploads.
- `yt-dlp` section retrieval relies on accessible playback; it can break after site changes, require authentication, fail on livestreams, or be unavailable in GitHub-hosted runners.
- Sources are selected by GTA 6 **title** only, not verified by vision. Upload to your own channel requires valid OAuth.
- Clips are not merged together: **each** 30-second highlight becomes an individual Short.

## Reference documentation

- [Meta Instagram Graph API publishing](https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api)
- [YouTube Data API quotas](https://developers.google.com/youtube/data/determine_quota_cost)
- [YouTube API Developer Policies](https://developers.google.com/youtube/terms/developer-policies)
- [yt-dlp download-sections](https://github.com/yt-dlp/yt-dlp#download-options)
- [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing)
- [GitHub Actions scheduling](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)

License: MIT for the source **code** only; it grants no rights to third-party video material.
