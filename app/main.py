"""One bounded, GTA 6-only scan per hourly GitHub workflow run."""
import json
import logging
from contextlib import ExitStack
from datetime import datetime, timezone

from .config import Settings
from .gemini import GeminiRouter
from .media import find_media_source, clip_media, clip_youtube_section, MediaAccessError
from .ranking import build_candidates, non_overlapping
from .state import key, load, mark, save, mark_platform, platform_uploaded, hour_has_attempt, reserve_hour
from .uploader import upload
from .instagram import publish_reel
from .youtube import YouTubeData, discover, parse_time
from .gta6 import is_gta6_gameplay_video
from .live import LiveBuffer, buffer_window

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOG = logging.getLogger(__name__)


def current_utc_hour() -> str:
    """Recheck on each upload; a job may cross the hour boundary."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H")


def run_once(config: Settings) -> dict:
    config.validate()
    report = {"generated_at": datetime.now(timezone.utc).isoformat(), "videos": [], "stats": {"discovered": 0, "analyzed": 0, "clipped": 0, "uploaded": 0, "instagram_uploaded": 0, "live_found": 0, "live_analyzed": 0, "live_buffered": 0, "media_restricted": 0, "gemini_fallbacks": 0}}
    if not config.youtube_api_key:
        LOG.warning("YOUTUBE_API_KEY is not set. Nothing to discover.")
    else:
        youtube = YouTubeData(config.youtube_api_key)
        router = GeminiRouter(config.gemini_api_key, config.free_models)
        state = load(config.state_path)
        gemini_evaluations = 0
        live_captures = 0
        attempted_this_run: set[str] = set()
        enabled_platforms = {
            "youtube": config.auto_upload,
            "instagram": config.instagram_auto_upload,
        }
        videos = discover(youtube, config.search_terms, config.region_codes,
                          config.min_subscribers, config.min_long_seconds, config.max_search_calls,
                          config.live_search_term)
        report["stats"]["discovered"] = len(videos)
        report["stats"]["live_found"] = sum(bool(v["is_live"]) for v in videos)
        for video in videos[:config.max_videos]:
            # A workflow invocation never publishes more than one clip per platform.
            # It also respects reservations from earlier runs within the same UTC hour.
            if any(enabled_platforms.values()) and not any(
                active and platform not in attempted_this_run
                and not hour_has_attempt(state, platform, current_utc_hour())
                for platform, active in enabled_platforms.items()
            ):
                break
            if not is_gta6_gameplay_video(video.get("title", "")):
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
                    capture_failure = None
                    if use_live_buffer:
                        live_captures += 1
                        try:
                            capture = stack.enter_context(LiveBuffer(video["id"], config.live_capture_seconds))
                        except MediaAccessError as buffer_error:
                            capture_failure = buffer_error
                            info["capture_note"] = f"Live media restricted ({buffer_error.reason})"
                            info["media_restriction"] = buffer_error.reason
                            report["stats"]["media_restricted"] += 1
                        except Exception as buffer_error:
                            info["capture_note"] = f"Live buffer unavailable: {type(buffer_error).__name__}"
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
                    report["stats"]["gemini_fallbacks"] = router.fallback_count
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
                        targets = [
                            platform for platform, active in enabled_platforms.items()
                            if active and platform not in attempted_this_run
                            and not platform_uploaded(state, clip_id, platform)
                            and not hour_has_attempt(state, platform, current_utc_hour())
                        ]
                        if any(enabled_platforms.values()) and not targets:
                            item["status"] = "already_processed_or_hourly_limit"
                            continue
                        try:
                            source = find_media_source(video["id"], config.media_dir)
                            if capture_failure is not None and not source:
                                raise capture_failure
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
                            # Both platforms receive the SAME rendered clip, max one attempt
                            # per UTC hour and per workflow run. A failed/unknown-result request
                            # consumes the hour too, preventing aggressive duplicate retries.
                            description = (f"GTA 6 highlight\nOriginal: {info['url']}\n"
                                           f"Creator: {video['channel_title']}\n#GTA6 #Shorts #Gaming")
                            item["uploads"] = {}
                            failed = False
                            for platform in targets:
                                hour = current_utc_hour()
                                if not reserve_hour(state, platform, hour, clip_id):
                                    item["uploads"][platform] = {"status": "deferred_hourly_limit"}
                                    continue
                                attempted_this_run.add(platform)
                                # Persist locally BEFORE calling the external API.
                                save(config.state_path, state)
                                try:
                                    if platform == "youtube":
                                        media_id = upload(
                                            output, config.oauth_token,
                                            f"GTA 6 | {highlight['label']} #Shorts",
                                            description, privacy=config.upload_privacy,
                                        )
                                        report["stats"]["uploaded"] += 1
                                    else:
                                        media_id = publish_reel(
                                            output, config.instagram_page_token, config.instagram_user_id,
                                            f"GTA 6 | {highlight['label']}\nOriginal: {info['url']}\n"
                                            f"Creator: {video['channel_title']}\n#GTA6 #GTAVI #Gaming",
                                            version=config.instagram_graph_version,
                                        )
                                        report["stats"]["instagram_uploaded"] += 1
                                    mark_platform(state, clip_id, platform, media_id)
                                    item["uploads"][platform] = {"status": "published", "id": media_id}
                                    save(config.state_path, state)
                                except Exception as upload_error:
                                    failed = True
                                    item["uploads"][platform] = {
                                        "status": "error", "error": str(upload_error)[:120]
                                    }
                                    LOG.warning("%s upload failed for %s: %s",
                                                platform, clip_id, type(upload_error).__name__)
                            item["status"] = "upload_error" if failed else (
                                "published" if any(v.get("status") == "published" for v in item["uploads"].values())
                                else "exported")
                            mark(state, clip_id, item["status"])
                        except MediaAccessError as media_exc:
                            item["status"] = "media_restricted"
                            item["error_code"] = media_exc.reason
                            if not info.get("media_restriction"):
                                report["stats"]["media_restricted"] += 1
                            info["media_restriction"] = media_exc.reason
                            info["media_source_hint"] = "Use an authorized direct HTTPS media source or operator-provided MP4"
                            LOG.warning("Media blocked for %s (%s); skipping further fetches", video["id"], media_exc.reason)
                            break
                        except Exception as clip_exc:
                            LOG.warning("Clip %s at %.1f seconds failed: %s", video["id"], highlight["timestamp"], clip_exc)
                            item["status"] = "clip_error"
                            item["error"] = f"{type(clip_exc).__name__}: {str(clip_exc)[:140]}"
                            continue
                        if attempted_this_run:
                            break
            except Exception as exc:
                LOG.exception("Processing video %s failed", video["id"])
                info["error"] = f"{type(exc).__name__}: {str(exc)[:180]}"
        save(config.state_path, state)
    report["status"] = "clips_generated" if report["stats"]["clipped"] else "scan_completed_no_clips"
    config.report_path.parent.mkdir(parents=True, exist_ok=True)
    config.report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf8")
    LOG.info("Report saved: %s; stats=%s", config.report_path, report["stats"])
    return report


if __name__ == "__main__":
    run_once(Settings())
