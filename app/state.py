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
    state.setdefault("clips", {})[clip_key] = {"at": datetime.now(timezone.utc).isoformat(),
                                                "status": status, "upload_id": upload_id}
