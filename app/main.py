"""One bounded, GTA 6-only scan per hourly GitHub workflow run."""
import json
import logging
from contextlib import ExitStack
from datetime import datetime, timezone

from .config import Settings
from .gemini import GeminiRouter
from .media import find_media_source, clip_media, clip_youtube_section
from .ranking import build_candidates, non_overlapping
from .state import key, load, mark, save, mark_platform, platform_uploaded
from .uploader import upload
from .instagram import publish_reel
from .youtube import YouTubeData, discover, parse_time
from .gta6 import is_gta6_video
from .live import LiveBuffer, buffer_window

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOG = logging.getLogger(__name__)


def run_once(config: Settings) -> dict:
    config.validate()
    report = {"generated_at": datetime.now(timezone.utc).isoformat(), "videos": [], "stats": {"discovered": 0, "analyzed": 0, "clipped": 0, "uploaded": 0, "instagram_uploaded": 0, "live_found": 0, "live_analyzed": 0, "live_buffered": 0}}
    if not config.youtube_api_key:
        LOG.warning("YOUTUBE_API_KEY is not set. Nothing to discover.")
    else:
        youtube = YouTubeData(config.youtube_api_key)
        router = GeminiRouter(config.gemini_api_key, config.free_models)
        state = load(config.state_path)
        gemini_evaluations = 0
        live_captures = 0
        instagram_reels = 0
        videos = discover(youtube, config.search_terms, config.region_codes,
                          config.min_subscribers, config.min_long_seconds, config.max_search_calls,
                          config.live_search_term)
        report["stats"]["discovered"] = len(videos)
        report["stats"]["live_found"] = sum(bool(v["is_live"]) for v in videos)
        for video in videos[:config.max_videos]:
            if not is_gta6_video(video.get("title", "")):
                continue  # additional topic gate; never export non-GTA-6 videos
            info = {k: video[k] for k in ("id", "title", "channel_id", "channel_title", "subscribers", "duration", "is_live", "is_short")}
            info["url"] = f"https://www.youtube.com/watch?v={video['id']}"
            info["target_highlights"] = config.target_clips_per_video
            info["highlights"] = []
            report["videos"].append(info)
            try:
                stream_start = parse_time(video["actual_start"]) if video["is_live"] else None
                use_live_buffer = bool(
                    video["is_live"] and stream_start and video["chat_id"]
                    and config.live_capture_enabled and config.source_mode == "yt_dlp"
                    and live_captures < config.max_live_captures
                )
                # Capture and chat polling run concurrently. No all-day recorder.
                with ExitStack() as stack:
                    capture = None
                    if use_live_buffer:
                        live_captures += 1
                        try:
                            capture = stack.enter_context(LiveBuffer(video["id"], config.live_capture_seconds))
                        except Exception as buffer_error:
                            info["capture_note"] = f"Live buffer unavailable: {str(buffer_error)[:120]}"
                    if video["is_live"]:
                        if not video["chat_id"] or not stream_start:
                            info["note"] = "Live chat unavailable or broadcast start time missing"
                            continue
                        messages = youtube.live_chat(
                            video["chat_id"], stream_start, polls=config.live_polls,
                            poll_seconds=config.live_poll_seconds,
                            delay_seconds=config.live_chat_delay,
                        )
                        report["stats"]["live_analyzed"] += 1
                        info["live_chat_messages"] = len(messages)
                    else:
                        messages = youtube.comments(video["id"], max_comments=config.max_api_comments)
                    candidates = build_candidates(messages, is_live=video["is_live"],
                                                  duration=video["duration"], min_support=config.min_support)
                    scored = []
                    for candidate in candidates[:60]:
                        if gemini_evaluations < config.max_gemini_evals and config.gemini_api_key:
                            scored.append(router.evaluate(candidate))
                            gemini_evaluations += 1
                        else:
                            scored.append({**candidate, "score": candidate["heuristic_score"],
                                           "label": "Audience reaction highlight", "model_used": "local-heuristic"})
                    highlights = non_overlapping(scored, config.max_clips_per_video,
                                                 config.clip_lead, config.clip_after, config.min_score,
                                                 duration=0 if video["is_live"] else video["duration"])
                    info["highlight_count"] = len(highlights)
                    if len(highlights) < config.target_clips_per_video:
                        info["note"] = "Fewer than 8-9 distinct positive reaction clusters in sampled chat/comments"
                    report["stats"]["analyzed"] += 1
                    recorded = None
                    if capture and highlights:
                        try:
                            recorded = capture.wait()
                            report["stats"]["live_buffered"] += 1
                            info["capture_mode"] = "temporary_live_buffer"
                        except Exception as capture_error:
                            info["capture_note"] = f"Live buffer failed: {str(capture_error)[:120]}"
                    for highlight in highlights:
                        item = {k: highlight[k] for k in ("timestamp", "score", "support", "model_used", "label", "start", "end")}
                        item["status"] = "metadata_only"
                        info["highlights"].append(item)
                        clip_id = key(video["id"], highlight["timestamp"])
                        prior = state["clips"].get(clip_id)
                        youtube_done = not config.auto_upload or platform_uploaded(state, clip_id, "youtube")
                        instagram_done = not config.instagram_auto_upload or platform_uploaded(state, clip_id, "instagram")
                        if prior and youtube_done and instagram_done:
                            item["status"] = "already_processed"
                            continue
                        try:
                            source = find_media_source(video["id"], config.media_dir)
                            if source:
                                output = clip_media(source, video["id"], highlight["start"],
                                                    highlight["end"] - highlight["start"],
                                                    config.output_dir, config.output_format)
                            elif recorded and capture and stream_start and capture.started_at:
                                window = buffer_window(
                                    highlight["start"], highlight["end"], stream_start,
                                    capture.started_at, config.live_capture_seconds,
                                    config.live_clock_shift,
                                )
                                if window:
                                    output = clip_media(str(recorded), video["id"], window.start,
                                                        window.duration, config.output_dir, config.output_format)
                                elif config.source_mode == "yt_dlp":
                                    output = clip_youtube_section(video["id"], highlight["start"],
                                                                  highlight["end"]-highlight["start"],
                                                                  config.output_dir, config.output_format)
                                else:
                                    item["status"] = "outside_recorded_live_window"
                                    continue
                            elif config.source_mode == "yt_dlp":
                                output = clip_youtube_section(video["id"], highlight["start"],
                                                              highlight["end"] - highlight["start"],
                                                              config.output_dir, config.output_format)
                            else:
                                item["status"] = "awaiting_media_source"
                                continue
                            item["status"] = "exported"
                            report["stats"]["clipped"] += 1
                            # Upload targets are independent: Instagram failure must not
                            # cause a duplicate YouTube post on the next hourly run.
                            description = (f"GTA 6 highlight\nOriginal: {info['url']}\n"
                                           f"Creator: {video['channel_title']}\n#GTA6 #Shorts #Gaming")
                            item["uploads"] = {}
                            failed = False
                            if config.auto_upload and not platform_uploaded(state, clip_id, "youtube"):
                                try:
                                    upload_id = upload(output, config.oauth_token,
                                                       f"GTA 6 | {highlight['label']} #Shorts",
                                                       description, privacy=config.upload_privacy)
                                    mark_platform(state, clip_id, "youtube", upload_id)
                                    item["uploads"]["youtube"] = {"status": "published", "id": upload_id}
                                    report["stats"]["uploaded"] += 1
                                    save(config.state_path, state)
                                except Exception as upload_error:
                                    failed = True
                                    item["uploads"]["youtube"] = {"status": "error", "error": str(upload_error)[:120]}
                                    LOG.warning("YouTube upload failed for %s: %s", clip_id, type(upload_error).__name__)
                            if config.instagram_auto_upload and not platform_uploaded(state, clip_id, "instagram"):
                                if instagram_reels >= config.max_instagram_reels_per_run:
                                    item["uploads"]["instagram"] = {"status": "deferred_run_limit"}
                                else:
                                    # Count requests even when the upload errors, so retry
                                    # loops cannot spam the Meta publishing endpoint.
                                    instagram_reels += 1
                                    try:
                                        ig_id = publish_reel(
                                            output, config.instagram_page_token, config.instagram_user_id,
                                            f"GTA 6 | {highlight['label']}\nOriginal: {info['url']}\n"
                                            f"Creator: {video['channel_title']}\n#GTA6 #GTAVI #Gaming",
                                            version=config.instagram_graph_version,
                                        )
                                        mark_platform(state, clip_id, "instagram", ig_id)
                                        item["uploads"]["instagram"] = {"status": "published", "id": ig_id}
                                        report["stats"]["instagram_uploaded"] += 1
                                        save(config.state_path, state)
                                    except Exception as ig_error:
                                        failed = True
                                        item["uploads"]["instagram"] = {"status": "error", "error": str(ig_error)[:120]}
                                        LOG.warning("Instagram upload failed for %s: %s", clip_id, type(ig_error).__name__)
                            item["status"] = "upload_error" if failed else (
                                "published" if any(v.get("status") == "published" for v in item["uploads"].values())
                                else "exported")
                            # Keep per-platform IDs even after another platform fails.
                            mark(state, clip_id, item["status"])
                        except Exception as clip_exc:
                            LOG.warning("Clip %s at %.1f seconds failed: %s", video["id"], highlight["timestamp"], clip_exc)
                            item["status"] = "clip_error"
                            item["error"] = f"{type(clip_exc).__name__}: {str(clip_exc)[:140]}"
                            continue
            except Exception as exc:
                LOG.exception("Processing video %s failed", video["id"])
                info["error"] = f"{type(exc).__name__}: {str(exc)[:180]}"
        save(config.state_path, state)
    config.report_path.parent.mkdir(parents=True, exist_ok=True)
    config.report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf8")
    LOG.info("Report saved: %s; stats=%s", config.report_path, report["stats"])
    return report


if __name__ == "__main__":
    run_once(Settings())
