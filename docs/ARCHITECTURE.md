# Architecture and next steps

## Files

- `app/gta6.py`: explicit GTA 6 title gate, checked at discovery and again before output
- `app/youtube.py`: guaranteed live-first search, >=1M subscribers, VOD comments and public live-chat sampling
- `app/ranking.py`: positive-reaction clustering at timestamped scenes and non-overlapping windows
- `app/gemini.py`: configured free-tier model fallback, then local heuristic
- `app/media.py`: FFmpeg video cuts, local/direct media, optional yt-dlp 30-second section extraction
- `app/live.py`: bounded 150-second live A/V sampling while chat is being polled, plus timestamp mapping
- `app/uploader.py`: OAuth upload of each selected Short to your channel
- `app/main.py`: hourly orchestration and JSON report
- `.github/workflows/hourly.yml`: hourly scheduled workflow

## Controls and limits

- No per-channel license approval checks are included. The source operator is responsible for permission and compliance. Video ID format and media format are still validated as technical input checks.
- A YouTube Data API metadata query cannot retrieve video bytes. `yt-dlp` section fetching is a separate video retrieval method; may fail for ongoing livestreams, and may transfer extra media data.
- Distinct scene counts cannot be guaranteed. 8/9 is the target/cap, never a reason to fabricate scenes.
- Each window is `[highlight - 20 seconds, highlight + 10 seconds]` with 30-second duration, except if the source ends.
- `source_mode=provided` skips direct yt-dlp media extraction, useful when a source is a licensed MP4 or direct HTTPS media feed.
- No always-on monitoring: a scheduled job records an ephemeral 150-second sample for at most one live stream by default; no persistent recording between hourly jobs.
- Live timestamps are approximate; the video playback edge can lag chat. A buffer is only used if the full 30-second window exists.
- 8–9 clips require independent moments spread out over enough footage; one 150-second buffer cannot produce 9 non-overlapping 30-second Shorts.
- No guaranteed cost-free unlimited Gemini calls or video uploads.

## Recommended next engineering milestones

1. Add persistent cross-run chat/stream checkpoints so multiple hourly samples can produce more clips per source.
2. Add speech transcription/audio peaks to find highlights when comments lack explicit timestamps.
3. Add language-aware GTA 6 classification beyond titles and detect irrelevant/misleading clips.
4. Improve GPU-free face/subject-aware 9:16 reframing and burned-in captions.
5. Record a limited set of authorized streams on persistent storage for reliable livestream DVR clipping.
6. Add OAuth refresh-token rotation, queue retry, upload idempotency, and a review UI.
