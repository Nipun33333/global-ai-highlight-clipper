# GTAClipper: free local setup on Windows 11 (16 GB RAM)

This is the complete GTAClipper application source with a free local AI overlay.

## Requirements

- Windows 11 (64-bit Intel/AMD) with WSL2; Docker Desktop set to Linux containers.
- 16 GB system RAM recommended, 25 GB or more available storage.
- An internet connection for initial Docker/AI model downloads.
- Docker Desktop running. Set its WSL2 memory limit to approximately 8 GB or higher if available.

## Install

1. Download the ZIP of this repository; extract it.
2. Open the extracted folder in File Explorer, type `powershell` into the address bar and press Enter.
3. Enter:

    powershell -ExecutionPolicy Bypass -File .\setup-free-windows.ps1

4. The script copies `.env.example` to `.env` if needed, generates 3 random local auth secrets, starts Docker and Ollama, pulls both free Qwen models, and builds the app.
5. Open http://localhost:3107 after the containers have started. You can register a local account without email verification.

If Docker says WSL2 is missing, run `wsl --install` from an Administrator PowerShell, reboot, and open Docker again.

## What runs locally

- `TRANSCRIPTION_PROVIDER=whisper` and `WHISPER_MODEL_SIZE=base`
- `WHISPER_FALLBACK_MODEL=tiny`
- `LLM=ollama:qwen2.5:3b`
- `LOCAL_LLM_FALLBACK=ollama:qwen2.5:1.5b`
- `OLLAMA_BASE_URL=http://ollama:11434/v1`
- `SELF_HOST=true`

The `docker-compose.local.yml` overlay supplies those values to the backend and worker and runs Ollama in a Docker container. Both models are pulled automatically and persist between restarts. The Whisper model is downloaded on its first use. No AssemblyAI or Gemini billing is needed for the default clip workflow.

## Troubleshooting

If `http://localhost:3107` is not loading, allow the containers to initialize, then inspect:

    docker compose -f docker-compose.yml -f docker-compose.local.yml ps
    docker compose -f docker-compose.yml -f docker-compose.local.yml logs --tail 100 backend worker frontend ollama ollama-setup

If it is slow, begin with a 10–20 minute video. CPU inference can take considerably longer than hosted APIs, especially with several candidates. Close memory-heavy apps. If YouTube download fails, try an authorized local MP4 first.

To stop:

    docker compose -f docker-compose.yml -f docker-compose.local.yml down

Do not upload or commit the generated `.env` file; it contains secrets. Do not rely on this configuration for 24/7 streaming. GTAClipper does not support clipping an ongoing livestream; use finished VODs.

## Provenance

Source: https://github.com/V413havai/GTAClipper . License: AGPL-3.0. The original notices and README are retained. The fallback changes were added to this customized distribution. This repository's AI models are free to run locally but the output is not guaranteed, and all Docker build and application integration testing should be performed on the laptop.
