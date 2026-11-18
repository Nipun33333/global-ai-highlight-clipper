# Global AI Highlight Clipper — Free Local Edition

A Windows-friendly installation of the open-source [GTAClipper](https://github.com/V413havai/GTAClipper) project, configured for **local transcription and local AI clip selection**. This repository contains the full GTAClipper application source (excluding upstream GitHub Actions workflows).

## Free AI stack for Windows 11 (16 GB RAM)

| Task | Primary | Fallback |
| --- | --- | --- |
| Find video highlights | Ollama: Qwen2.5 3B | Ollama: Qwen2.5 1.5B |
| Audio transcription + word timings | Whisper Base | Whisper Tiny |
| Crop, captions, export | FFmpeg + GTAClipper | — |

The free models run on your own PC without API keys. No per-request charges for Ollama, Whisper or FFmpeg. Processing will be slower on CPU than GPU. Model downloads, disk space, electricity and any optional third-party service costs still apply.

## Run on your Windows laptop

1. Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) with WSL2. Start it and wait for **Engine running**.
2. Download this GitHub repository as ZIP. Extract to a short folder path such as Documents\GTAClipper.
3. Open PowerShell in the extracted folder (type **powershell** into File Explorer's address bar).
4. Run:

    powershell -ExecutionPolicy Bypass -File .\setup-free-windows.ps1

5. Docker builds the application and downloads both Ollama models. Open **http://localhost:3107** when the app is ready.
6. Create your local account. Upload your own video or paste a finished YouTube video link to generate Shorts.

Minimum: 8 GB RAM; recommended: **16 GB RAM and 25+ GB free disk**. Give Docker Desktop 8 GB or more memory if possible. Initial setup needs an internet connection.

## Daily commands

Run these in PowerShell from the repository directory:

- Start: docker compose -f docker-compose.yml -f docker-compose.local.yml up -d
- Stop: docker compose -f docker-compose.yml -f docker-compose.local.yml down
- Troubleshoot: docker compose -f docker-compose.yml -f docker-compose.local.yml logs --tail 100 backend worker ollama ollama-setup

Read [FREE_LOCAL_SETUP.md](FREE_LOCAL_SETUP.md) for detailed instructions.

## Fallback behavior and limitations

If an AI inference call fails, the clip analysis runner retries with Qwen2.5 1.5B. If Whisper Base fails, transcription retries with Whisper Tiny. These are **best-effort** fallbacks, not guarantees of success. Smaller models can produce lower-quality transcripts or rankings.

**Live streams are not supported**: wait for a YouTube/Twitch/Kick broadcast to end and process the VOD, or upload a recording you have permission to use. YouTube downloading may require authentication or fail due to platform restrictions. The upstream application's optional cloud and premium features may require separate accounts or paid services; the default clipping workflow uses no paid AI API.

## Attribution and license

This is a modified distribution of **GTAClipper**, originally by Vaibhav Hedaoo, under **AGPL-3.0**. The original [README](README_UPSTREAM.md), [LICENSE](LICENSE), and [NOTICE](NOTICE) are preserved. If you deploy modified code publicly, comply with the AGPL's source-sharing requirements.
