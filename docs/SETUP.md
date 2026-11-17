# GTA 6 Shorts — detailed setup

## 1. Get API credentials

1. Create/select a Google Cloud project in [Google Cloud](https://console.cloud.google.com/).
2. Enable **YouTube Data API v3** and create an API key. Store as `YOUTUBE_API_KEY`.
3. Create a Gemini API key in [Google AI Studio](https://aistudio.google.com/app/apikey). Store as `GEMINI_API_KEY`.
4. Verify [Gemini free-tier prices](https://ai.google.dev/gemini-api/docs/pricing); the configured model candidates do not guarantee free use in every project/region.

Never commit credentials or OAuth tokens to your GitHub repository.

## 2. GTA 6-only discovery and clips

The built-in title filter requires `GTA 6`, `GTA VI`, or `Grand Theft Auto VI` (and equivalents). `SEARCH_TERMS` defaults to `GTA 6 live,GTA VI gameplay,GTA 6 shorts`. Creator filter: >= 1,000,000 public subscribers.

It checks sampled live broadcasts, 10+ hour video-on-demand, and short videos <= 3 minutes. For 8–9 clips per source, you need **8–9 distinct timecoded positive comment/chat clusters**. Fewer actual reactions mean fewer clips; no fictional timestamps are made.

Each selected clip is 20 sec before the highlight point plus 10 sec afterward, **30 sec** in total (or shorter if the source ends first). Output is 720x1280 vertical.


## Currently-live gameplay mode (new)

Every scheduled/manual workflow run spends its first YouTube search call on an active **GTA 6 gameplay live** broadcast. That search is unlocalized; the remaining calls rotate regions for long/short VOD. The existing GTA 6 title, currently-live flag, and 1M+ subscriber gates are mandatory.

For the first live stream with a public chat, the runner tries `yt-dlp -g -f b --no-live-from-start` to resolve a single combined audio/video stream, and starts a temporary `ffmpeg` recording for `LIVE_CAPTURE_SECONDS=150`. Chat polling occurs **at the same time**. Chat comments are mapped to approximate stream-relative timestamps and the detected highlight is cut from available recorded seconds. The temporary clip buffer is automatically deleted. If a selected highlight is outside the buffer, the app tries existing time-section extraction, which often fails on active streams without seekable DVR.

GitHub Actions variables (all optional): `LIVE_SEARCH_TERM=GTA 6 gameplay live`, `LIVE_CAPTURE_ENABLED=true`, `LIVE_CAPTURE_SECONDS=150` (30..300), `MAX_LIVE_CAPTURES_PER_RUN=1`, `LIVE_POLLS=6`, `LIVE_POLL_SECONDS=20`, `LIVE_CLOCK_SHIFT_SECONDS=0`. Do **not** expect 8-9 independent 30-second moments from only 150 seconds of recording. Runs do not persist video buffers across hours. Live-chat timestamp and video playback can be offset by several seconds.

Test with **Run workflow** on a real active GTA 6 source and inspect `reports/latest.json`: `stats.live_found`, `stats.live_analyzed`, `stats.live_buffered`, `stats.clipped`, and per-highlight `status` will show what happened. No real-world live-stream test can be done without working keys/source access. If a live source has no chat or is not playable from the runner, no fabricated highlights will be produced.

## 3. Section-only media extraction

`SOURCE_MODE=yt_dlp` (default) tells the script to run `yt-dlp --download-sections` for the selected 30-sec window (primarily for recorded VOD). This avoids first downloading the complete 10-hour video. FFmpeg converts the result to a vertical Short. The section extraction is best effort: some YouTube streams don't allow seeking (especially live), and some formats require downloading extra data or fail entirely.

Alternatively, choose `SOURCE_MODE=provided` and supply `media/<video-id>.mp4` or configure `MEDIA_SOURCE_MAP_JSON={"VIDEO_ID":"https://cdn.example/direct.mp4"}`. Local/direct sources always take priority when present. No campaign or channel-approval database is part of this program.

**Important:** The project does not automatically validate your media license. The operator is responsible for ensuring the chosen source and publishing use match their actual rights and the relevant service terms.

## 4. YouTube upload OAuth

1. In Google Cloud create OAuth consent configuration and Desktop application credentials.
2. Download `client_secret.json` onto your own device in the project directory (this filename is ignored by Git).
3. Run `python scripts/oauth_setup.py` locally and authorize the appropriate YouTube channel.
4. Put the resulting `.youtube_oauth_token.json` text into GitHub Actions **secret** `YOUTUBE_OAUTH_TOKEN`.
5. Configure Actions variables `AUTO_UPLOAD=true` and initially `UPLOAD_PRIVACY=private`. Switch to `public` when ready.

Without valid OAuth, automatic publishing cannot start. It uploads normal Shorts; it doesn't initiate new live broadcasts.

## Instagram Reels publishing

**Meta official API, not login scraping:** This integration uses the Instagram API **with Facebook Login**, as it supports direct resumable uploads of the locally generated MP4. An Instagram Professional (Business or Creator) account must be linked to a **Facebook Page** managed by your Meta app/account. A personal-only Instagram account is not supported by this API.

1. In [Meta for Developers](https://developers.facebook.com/apps/) create/configure a Business app with Instagram Graph API / Facebook Login for Business. Get the appropriate permissions for your account, including `pages_show_list`, `instagram_basic`, `instagram_content_publish`, and `pages_read_engagement`, as required by your app configuration. A production deployment may require app review / access approval.
2. Connect your **Professional Instagram account** to your Facebook Page. Use Meta Graph API Explorer to get a User token with the required Page/Instagram scopes. From `GET /me/accounts?fields=name,access_token,instagram_business_account` select the correct Page, its **Page access token** and the linked Instagram `instagram_business_account.id` (this is **not** your @handle).
3. GitHub > repository > **Settings > Secrets and variables > Actions > Secrets**: add `IG_USER_ID` and `INSTAGRAM_PAGE_ACCESS_TOKEN`. Never put the token in a code file, README, log, issue or GitHub variable.
4. Under **Actions > Variables** set `INSTAGRAM_AUTO_UPLOAD=true` when you're ready to publish. The cap is hard-coded at **1 attempt per platform per UTC hour**; optional `INSTAGRAM_GRAPH_VERSION=v26.0`. YouTube and Instagram can be independently enabled (`AUTO_UPLOAD` governs only YouTube).
5. Manually run the scanner and inspect `reports/latest.json`: `stats.instagram_uploaded` and each highlight's `uploads.instagram` status / returned media ID. Verify the Reel directly on Instagram. If the run fails, inspect status codes; professional/page link, permissions, token expiry and publish limits are common causes.

**Mechanism:** POST to `/{ig-user-id}/media` with `media_type=REELS&upload_type=resumable`, POST the local MP4 bytes to the Meta `rupload.facebook.com` URL, poll the container until `FINISHED`, then POST to `/{ig-user-id}/media_publish`. This avoids separately hosting the clip at a public URL and avoids paid video storage. Valid Meta API access, rate limits, media requirements (vertical H.264/AAC recommended), and eligibility still apply. The integration is unit-tested with simulated responses, **not verified live against your Instagram account**. Published Instagram Reels are not equivalent to opening an Instagram live broadcast.

Sources: [Meta's Instagram API guide](https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api) and [Instagram content publishing docs](https://developers.facebook.com/docs/instagram-platform/content-publishing/).

## 5. Push to your GitHub profile

Create an **empty** repository `global-ai-highlight-clipper` at https://github.com/new. Extract the ZIP, open terminal in the extracted folder and run:

```bash
git init
git add .
git commit -m "feat: GTA 6-only AI Shorts clipper"
git branch -M main
git remote add origin https://github.com/Nipun33333/global-ai-highlight-clipper.git
git push -u origin main
```

Add the keys to **Settings > Secrets and variables > Actions > Secrets**. The workflow variables can be added under the **Variables** tab. Open **Actions > Hourly worldwide highlight scanner > Run workflow** for a manual smoke test.

## 6. Test locally

```bash
pip install -r requirements.txt
python -m pytest -q
python scripts/demo.py
python -m app.main
```

The Python tests include simulated live-chat and live-buffer integration but require no API keys; the final live command requires valid keys to discover videos. Real-world section downloading and OAuth uploading require integration testing with your account and source.

## 7. Free-tier limitations

- Google documents a default separate search quota of 100 `search.list` calls/day; this workflow uses up to 72/day at default settings, with other API costs in separate buckets.
- GitHub hourly workflows are not a continuously running 24/7 process; scheduling and processing time can vary.
- Gemini free-tier rate limits and model access are not fixed guarantees. The router tries only configured verified free candidates, then local scoring.
- Site video playback restrictions and authenticated live playback may prevent `yt-dlp` from getting individual sections.
- If you start with private uploads, changing `UPLOAD_PRIVACY` to public later does not retroactively change already-uploaded videos.


## One short per hour on each platform

The hourly scanner is allowed to **attempt at most one YouTube Short and one Instagram Reel upload in each UTC-hour bucket**, even if manually rerun. It uses the same candidate MP4 for both platforms when both are enabled. The 8–9 highlight detection target remains but only one highlight is selected for publishing in a run. A failed or timed-out upload still consumes the hour's attempt, so unexpected API responses do not trigger immediate duplicate uploads.

Cross-run limits live in `state/processed.json` (`hourly_upload_attempts`) and are committed by the GitHub Actions workflow. This is best-effort idempotency, not a transactional guarantee: a runner crash, rejected state push, unknown API result or workflows from other installations can result in duplicates. The workflow's concurrency group serializes runs in this repository. GitHub scheduling is not exact and a missing video, absent API credentials or API failure can mean zero uploads in an hour.

The workflow runs at minute **07 UTC** (minute **37 IST**) every hour, not at exactly HH:00 IST. Never store tokens in the repository.
