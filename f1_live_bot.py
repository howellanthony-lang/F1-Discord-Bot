from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable

import fastf1
import feedparser
import requests

try:
    import config
except ImportError:
    config = None


CACHE_DIR = Path("cache")
STATE_DIR = Path("state")
STATE_FILE = STATE_DIR / "sent_items.json"
JOLPICA_BASE_URL = "https://api.jolpi.ca/ergast/f1"
RACE_CONTROL_REPO = "https://github.com/robvdpol/RaceControl.git"

SESSION_ORDER = ["R", "Q", "SQ", "S", "FP3", "FP2", "FP1"]
SESSION_NAMES = {
    "R": "Race",
    "Q": "Qualifying",
    "SQ": "Sprint Qualifying",
    "S": "Sprint",
    "FP3": "Practice 3",
    "FP2": "Practice 2",
    "FP1": "Practice 1",
}

DEFAULT_NEWS_FEEDS = [
    "https://www.formula1.com/en/latest/all.xml",
    "https://www.motorsport.com/rss/f1/news/",
    "https://www.autosport.com/rss/f1/news/",
]

WEBHOOK_ENV = {
    "schedule": "SCHEDULE_WEBHOOK",
    "standings": "STANDINGS_WEBHOOK",
    "news": "NEWS_WEBHOOK",
    "results": "RESULTS_WEBHOOK",
    "fastest_lap": "FASTEST_LAP_WEBHOOK",
    "race_control": "RACE_CONTROL_WEBHOOK",
    "weather": "WEATHER_WEBHOOK",
    "live_timing": "LIVE_TIMING_WEBHOOK",
}


@dataclass
class BotConfig:
    season: int
    news_limit: int
    standings_limit: int
    news_feeds: list[str]
    webhooks: dict[str, str]


def main() -> None:
    args = parse_args()
    bot_config = load_config()
    state = load_state()

    print("Starting F1 Discord automation.")
    print(f"Mode: {args.mode}")
    print(f"Season: {bot_config.season}")
    print(f"RaceControl reference: {RACE_CONTROL_REPO}")

    setup_fastf1_cache()

    tasks = get_tasks_for_mode(args.mode)
    for task_name, task_func in tasks:
        run_task(task_name, task_func, bot_config, state, force=args.force)

    prune_state(state)
    save_state(state)
    print("Finished. This run is complete.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the F1 Discord automation once.")
    parser.add_argument(
        "--mode",
        choices=["auto", "news", "standings", "schedule", "race-weekend", "all"],
        default=os.getenv("BOT_MODE", "auto"),
        help="Which automation group to run.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=os.getenv("FORCE_POST", "").lower() in {"1", "true", "yes"},
        help="Ignore due intervals and duplicate checks.",
    )
    return parser.parse_args()


def load_config() -> BotConfig:
    webhooks = {}
    configured_webhooks = getattr(config, "WEBHOOKS", {}) if config else {}
    if isinstance(configured_webhooks, dict):
        webhooks.update(configured_webhooks)

    for key, env_name in WEBHOOK_ENV.items():
        local_value = getattr(config, env_name, "") if config else ""
        webhooks[key] = os.getenv(env_name, local_value)

    return BotConfig(
        season=int(os.getenv("SEASON", getattr(config, "SEASON", datetime.now(timezone.utc).year))),
        news_limit=int(os.getenv("NEWS_LIMIT", getattr(config, "NEWS_LIMIT", 5))),
        standings_limit=int(os.getenv("STANDINGS_LIMIT", getattr(config, "STANDINGS_LIMIT", 10))),
        news_feeds=list(getattr(config, "NEWS_FEEDS", DEFAULT_NEWS_FEEDS) if config else DEFAULT_NEWS_FEEDS),
        webhooks=webhooks,
    )


def setup_fastf1_cache() -> None:
    CACHE_DIR.mkdir(exist_ok=True)
    fastf1.Cache.enable_cache(str(CACHE_DIR))
    print(f"FastF1 cache ready: {CACHE_DIR.resolve()}")


def get_tasks_for_mode(mode: str) -> list[tuple[str, Callable[[BotConfig, dict[str, Any], bool], None]]]:
    all_tasks = [
        ("news", post_news),
        ("standings", post_standings),
        ("schedule", post_next_weekend_schedule),
        ("race_weekend_reminder", post_race_weekend_reminder),
        ("session_results", post_latest_session_results),
        ("fastest_lap", post_fastest_lap),
    ]
    if mode == "all":
        return all_tasks
    if mode == "auto":
        return all_tasks
    if mode == "race-weekend":
        return all_tasks[3:]
    if mode == "schedule":
        return [all_tasks[2], all_tasks[3]]
    if mode == "standings":
        return [all_tasks[1]]
    if mode == "news":
        return [all_tasks[0]]
    return all_tasks


def run_task(
    task_name: str,
    task_func: Callable[[BotConfig, dict[str, Any], bool], None],
    bot_config: BotConfig,
    state: dict[str, Any],
    force: bool,
) -> None:
    print(f"\n--- {task_name} ---")
    try:
        task_func(bot_config, state, force)
    except Exception as error:
        print(f"Error in {task_name}: {error}")


def post_news(bot_config: BotConfig, state: dict[str, Any], force: bool) -> None:
    if not is_due(state, "news", minutes=15, force=force):
        print("Skipping news: not due yet.")
        return

    entries = []
    for feed_url in bot_config.news_feeds:
        try:
            print(f"Reading RSS feed: {feed_url}")
            feed = feedparser.parse(feed_url)
            entries.extend(feed.entries)
        except Exception as error:
            print(f"RSS feed failed: {feed_url}: {error}")

    if not entries:
        print("No news entries found.")
        return

    posted = 0
    entries = sorted(entries, key=get_feed_timestamp, reverse=True)
    for entry in entries[: bot_config.news_limit]:
        entry_id = news_item_id(entry)
        if was_sent(state, "news", entry_id) and not force:
            continue

        title = clean_text(entry.get("title", "Untitled"))
        link = entry.get("link", "")
        source = clean_text(entry.get("source", {}).get("title", "")) if isinstance(entry.get("source"), dict) else ""
        published = format_feed_time(entry)
        lines = ["**F1 News**", f"**{title}**"]
        if source:
            lines.append(f"Source: {source}")
        if published:
            lines.append(f"Published: {published}")
        if link:
            lines.append(link)

        if post_to_discord(bot_config, "news", "\n".join(lines)):
            record_sent(state, "news", entry_id)
            posted += 1

    print(f"News posts sent: {posted}")


def post_standings(bot_config: BotConfig, state: dict[str, Any], force: bool) -> None:
    if not is_due(state, "standings", hours=6, force=force):
        print("Skipping standings: not due yet.")
        return

    driver_lines = get_driver_standings_lines(bot_config)
    constructor_lines = get_constructor_standings_lines(bot_config)
    sent_id = f"{bot_config.season}:standings:{six_hour_window_key(now_utc())}"

    if was_sent(state, "standings", sent_id) and not force:
        print("Skipping standings: already posted for this 6-hour window.")
        mark_run(state, "standings")
        return

    message = "\n\n".join(
        [
            "\n".join(driver_lines),
            "\n".join(constructor_lines),
        ]
    )
    if post_to_discord(bot_config, "standings", message):
        record_sent(state, "standings", sent_id)
    mark_run(state, "standings")


def post_next_weekend_schedule(bot_config: BotConfig, state: dict[str, Any], force: bool) -> None:
    if not is_due(state, "schedule", hours=24, force=force):
        print("Skipping schedule: not due yet.")
        return

    event = get_next_or_current_event(bot_config.season)
    if event is None:
        print("No schedule event found.")
        mark_run(state, "schedule")
        return

    event_id = f"{bot_config.season}:schedule:{event['RoundNumber']}:{date_key(now_utc())}"
    if was_sent(state, "schedule", event_id) and not force:
        print("Skipping schedule: already posted today.")
        mark_run(state, "schedule")
        return

    if post_to_discord(bot_config, "schedule", format_event_schedule(event, "Next F1 Weekend")):
        record_sent(state, "schedule", event_id)
    mark_run(state, "schedule")


def post_race_weekend_reminder(bot_config: BotConfig, state: dict[str, Any], force: bool) -> None:
    if not is_due(state, "race_weekend_reminder", hours=24, force=force):
        print("Skipping reminder: not due yet.")
        return

    event = get_next_or_current_event(bot_config.season)
    if event is None or not is_race_weekend(event):
        print("No active race weekend for reminder.")
        mark_run(state, "race_weekend_reminder")
        return

    reminder_id = f"{bot_config.season}:reminder:{event['RoundNumber']}:{date_key(now_utc())}"
    if was_sent(state, "race_weekend_reminder", reminder_id) and not force:
        print("Skipping reminder: already posted today.")
        mark_run(state, "race_weekend_reminder")
        return

    lines = [
        "**Race Weekend Reminder**",
        f"{event['EventName']} is underway or about to start.",
        f"Location: {event['Location']}, {event['Country']}",
        "",
        format_event_schedule(event, "Weekend Schedule"),
    ]
    if post_to_discord(bot_config, "race_control", "\n".join(lines), fallback="schedule"):
        record_sent(state, "race_weekend_reminder", reminder_id)
    mark_run(state, "race_weekend_reminder")


def post_latest_session_results(bot_config: BotConfig, state: dict[str, Any], force: bool) -> None:
    event = get_next_or_current_event(bot_config.season)
    if event is None or not is_race_weekend(event):
        print("Skipping session results: not a race weekend.")
        return

    session = get_latest_available_session(bot_config.season)
    if session is None:
        print("No completed FastF1 session found.")
        return

    results = session.results
    if results is None or results.empty:
        print("Latest session has no results.")
        return

    session_id = f"{bot_config.season}:results:{session.event['RoundNumber']}:{session.name}"
    digest = stable_hash(results.head(10).to_string())
    sent_id = f"{session_id}:{digest}"
    if was_sent(state, "session_results", sent_id) and not force:
        print("Skipping session results: already posted this result set.")
        return

    lines = [
        "**Latest F1 Session Results**",
        f"{session.event['EventName']} - {SESSION_NAMES.get(session.name, session.name)}",
    ]
    for _, row in results.head(10).iterrows():
        position = safe_int(row.get("Position"), "-")
        abbreviation = row.get("Abbreviation", "UNK")
        full_name = row.get("FullName", abbreviation)
        lines.append(f"{position}. {abbreviation} - {full_name}")

    if post_to_discord(bot_config, "results", "\n".join(lines)):
        record_sent(state, "session_results", sent_id)


def post_fastest_lap(bot_config: BotConfig, state: dict[str, Any], force: bool) -> None:
    event = get_next_or_current_event(bot_config.season)
    if event is None or not is_race_weekend(event):
        print("Skipping fastest lap: not a race weekend.")
        return

    session = get_latest_available_session(bot_config.season)
    if session is None or session.laps is None or session.laps.empty:
        print("No FastF1 lap data available yet.")
        return

    fastest = session.laps.pick_fastest()
    lap_time = str(fastest["LapTime"])
    sent_id = stable_hash(
        f"{bot_config.season}:{session.event['RoundNumber']}:{session.name}:{fastest['Driver']}:{lap_time}"
    )
    if was_sent(state, "fastest_lap", sent_id) and not force:
        print("Skipping fastest lap: already posted.")
        return

    lines = [
        "**Fastest Lap Available**",
        f"{session.event['EventName']} - {SESSION_NAMES.get(session.name, session.name)}",
        f"Driver: {fastest['Driver']}",
        f"Team: {fastest['Team']}",
        f"Lap time: {lap_time}",
    ]
    if post_to_discord(bot_config, "fastest_lap", "\n".join(lines)):
        record_sent(state, "fastest_lap", sent_id)


def get_driver_standings_lines(bot_config: BotConfig) -> list[str]:
    data = get_json(f"{JOLPICA_BASE_URL}/{bot_config.season}/driverstandings/")
    standings = data["MRData"]["StandingsTable"]["StandingsLists"][0]["DriverStandings"]
    lines = [f"**F1 Driver Standings {bot_config.season}**"]
    for item in standings[: bot_config.standings_limit]:
        driver = item["Driver"]
        name = f"{driver['givenName']} {driver['familyName']}"
        lines.append(f"{item['position']}. {name} - {item['points']} pts")
    return lines


def get_constructor_standings_lines(bot_config: BotConfig) -> list[str]:
    data = get_json(f"{JOLPICA_BASE_URL}/{bot_config.season}/constructorstandings/")
    standings = data["MRData"]["StandingsTable"]["StandingsLists"][0]["ConstructorStandings"]
    lines = [f"**F1 Constructor Standings {bot_config.season}**"]
    for item in standings[: bot_config.standings_limit]:
        constructor = item["Constructor"]["name"]
        lines.append(f"{item['position']}. {constructor} - {item['points']} pts")
    return lines


def get_next_or_current_event(season: int) -> Any | None:
    schedule = fastf1.get_event_schedule(season, include_testing=False)
    current_time = now_utc()
    future_or_current = []

    for _, event in schedule.iterrows():
        start, end = event_window(event)
        if end >= current_time:
            future_or_current.append((start, event))

    if future_or_current:
        return sorted(future_or_current, key=lambda item: item[0])[0][1]
    if schedule.empty:
        return None
    return schedule.iloc[-1]


def get_latest_available_session(season: int) -> Any | None:
    schedule = fastf1.get_event_schedule(season, include_testing=False)
    current_time = now_utc()
    past_events = []

    for _, event in schedule.iterrows():
        start, _ = event_window(event)
        if start <= current_time:
            past_events.append((start, event))

    for _, event in sorted(past_events, key=lambda item: item[0], reverse=True):
        round_number = int(event["RoundNumber"])
        for session_name in SESSION_ORDER:
            try:
                print(f"Trying {event['EventName']} {SESSION_NAMES.get(session_name, session_name)}...")
                session = fastf1.get_session(season, round_number, session_name)
                session.load(laps=True, telemetry=False, weather=False, messages=False)
                has_results = session.results is not None and not session.results.empty
                has_laps = session.laps is not None and not session.laps.empty
                if has_results or has_laps:
                    print(f"Using {event['EventName']} {SESSION_NAMES.get(session_name, session_name)}.")
                    return session
            except Exception as error:
                print(f"Session unavailable: {error}")
    return None


def format_event_schedule(event: Any, heading: str) -> str:
    lines = [
        f"**{heading}**",
        f"**{event['EventName']}**",
        f"Location: {event['Location']}, {event['Country']}",
    ]
    for index in range(1, 6):
        name = event.get(f"Session{index}") or f"Session {index}"
        date_value = event.get(f"Session{index}Date")
        if has_value(date_value):
            lines.append(f"{name}: {format_datetime(to_utc(date_value))}")
    return "\n".join(lines)


def is_race_weekend(event: Any) -> bool:
    start, end = event_window(event)
    current_time = now_utc()
    return start - timedelta(hours=12) <= current_time <= end + timedelta(hours=36)


def event_window(event: Any) -> tuple[datetime, datetime]:
    dates = []
    for index in range(1, 6):
        value = event.get(f"Session{index}Date")
        if has_value(value):
            dates.append(to_utc(value))
    if not dates:
        event_date = to_utc(event["EventDate"])
        return event_date, event_date
    return min(dates), max(dates)


def post_to_discord(
    bot_config: BotConfig,
    webhook_name: str,
    content: str,
    fallback: str | None = None,
) -> bool:
    webhook_url = bot_config.webhooks.get(webhook_name, "")
    if (not webhook_url or "YOUR_" in webhook_url) and fallback:
        webhook_url = bot_config.webhooks.get(fallback, "")
        webhook_name = fallback

    if not webhook_url or "YOUR_" in webhook_url:
        print(f"Skipping Discord post for {webhook_name}: webhook is missing or placeholder.")
        return False

    print(f"Posting to Discord webhook: {webhook_name}")
    response = requests.post(webhook_url, json={"content": content[:1900]}, timeout=20)
    response.raise_for_status()
    print(f"Posted successfully: {webhook_name}")
    return True


def get_json(url: str) -> dict[str, Any]:
    print(f"Requesting API data: {url}")
    response = requests.get(url, timeout=20)
    response.raise_for_status()
    return response.json()


def load_state() -> dict[str, Any]:
    if not STATE_FILE.exists():
        return {"sent": {}, "last_runs": {}}
    try:
        with STATE_FILE.open("r", encoding="utf-8") as file:
            state = json.load(file)
        state.setdefault("sent", {})
        state.setdefault("last_runs", {})
        return state
    except Exception as error:
        print(f"Could not read state file; starting fresh: {error}")
        return {"sent": {}, "last_runs": {}}


def save_state(state: dict[str, Any]) -> None:
    STATE_DIR.mkdir(exist_ok=True)
    with STATE_FILE.open("w", encoding="utf-8") as file:
        json.dump(state, file, indent=2, sort_keys=True)
        file.write("\n")
    print(f"State saved: {STATE_FILE}")


def is_due(
    state: dict[str, Any],
    task_name: str,
    minutes: int = 0,
    hours: int = 0,
    force: bool = False,
) -> bool:
    if force:
        return True
    interval = timedelta(minutes=minutes, hours=hours)
    if interval <= timedelta(0):
        return True
    last_run = state.get("last_runs", {}).get(task_name)
    if not last_run:
        return True
    return now_utc() - datetime.fromisoformat(last_run) >= interval


def mark_run(state: dict[str, Any], task_name: str) -> None:
    state.setdefault("last_runs", {})[task_name] = now_utc().isoformat()


def was_sent(state: dict[str, Any], category: str, item_id: str) -> bool:
    return item_id in state.setdefault("sent", {}).setdefault(category, {})


def record_sent(state: dict[str, Any], category: str, item_id: str) -> None:
    state.setdefault("sent", {}).setdefault(category, {})[item_id] = now_utc().isoformat()


def prune_state(state: dict[str, Any]) -> None:
    cutoff = now_utc() - timedelta(days=60)
    for category, items in state.setdefault("sent", {}).items():
        for item_id, timestamp in list(items.items()):
            try:
                if datetime.fromisoformat(timestamp) < cutoff:
                    del items[item_id]
            except ValueError:
                del items[item_id]


def news_item_id(entry: Any) -> str:
    raw_id = entry.get("id") or entry.get("guid") or entry.get("link") or entry.get("title") or json.dumps(entry)
    return stable_hash(str(raw_id))


def stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def get_feed_timestamp(entry: Any) -> float:
    parsed_time = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed_time:
        return datetime(*parsed_time[:6], tzinfo=timezone.utc).timestamp()
    published = entry.get("published") or entry.get("updated")
    if published:
        try:
            return parsedate_to_datetime(published).timestamp()
        except Exception:
            return 0
    return 0


def format_feed_time(entry: Any) -> str:
    timestamp = get_feed_timestamp(entry)
    if not timestamp:
        return ""
    return format_datetime(datetime.fromtimestamp(timestamp, tz=timezone.utc))


def to_utc(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def has_value(value: Any) -> bool:
    if value is None:
        return False
    try:
        return value == value
    except Exception:
        return True


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def date_key(value: datetime) -> str:
    return value.strftime("%Y-%m-%d")


def six_hour_window_key(value: datetime) -> str:
    window_start = (value.hour // 6) * 6
    return f"{value.strftime('%Y-%m-%d')}T{window_start:02d}"


def format_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def clean_text(value: str) -> str:
    return " ".join(str(value).split())


def safe_int(value: Any, fallback: str) -> int | str:
    try:
        if value != value:
            return fallback
        return int(value)
    except Exception:
        return fallback


if __name__ == "__main__":
    main()
