"""Persist deduped clip IDs, not user comments or raw API text."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path


def load(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf8"))
        return data if isinstance(data, dict) and isinstance(data.get("clips"), dict) else {"clips": {}}
    except (OSError, json.JSONDecodeError):
        return {"clips": {}}


def key(video_id: str, timestamp: float) -> str:
    return f"{video_id}:{int(timestamp // 30) * 30}"


def save(path: Path, state: dict) -> None:
    # Retain only 29 days to reduce persisted metadata lifetime.
    cutoff = datetime.now(timezone.utc) - timedelta(days=29)
    kept = {}
    for k, record in state.get("clips", {}).items():
        try:
            at = datetime.fromisoformat(record["at"])
            if at >= cutoff:
                kept[k] = record
        except (KeyError, TypeError, ValueError):
            continue
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"clips": kept}, indent=2), encoding="utf8")


def mark(state: dict, clip_key: str, status: str, upload_id: str | None = None) -> None:
    entry = state.setdefault("clips", {}).setdefault(clip_key, {})
    entry.update({"at": datetime.now(timezone.utc).isoformat(),
                  "status": status, "upload_id": upload_id})


def platform_uploaded(state: dict, clip_key: str, platform: str) -> bool:
    record = state.get("clips", {}).get(clip_key, {})
    entry = record.get("platforms", {}).get(platform, {})
    if entry.get("status") == "published" and entry.get("id"):
        return True
    # Old state format from before Instagram support.
    return platform == "youtube" and str(record.get("status", "")).startswith("uploaded_")


def mark_platform(state: dict, clip_key: str, platform: str, media_id: str) -> None:
    if platform not in {"youtube", "instagram"} or not media_id:
        raise ValueError("Platform and media ID required")
    entry = state.setdefault("clips", {}).setdefault(clip_key, {})
    # Upgrade previously uploaded YouTube-only state without losing its ID.
    if str(entry.get("status", "")).startswith("uploaded_") and entry.get("upload_id"):
        entry.setdefault("platforms", {}).setdefault("youtube", {
            "status": "published", "id": entry["upload_id"]
        })
    entry["at"] = datetime.now(timezone.utc).isoformat()
    entry.setdefault("platforms", {})[platform] = {"status": "published", "id": media_id}
