from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import yaml


REQUIRED_FILES = [
    ".github/workflows/f1-bot.yml",
    ".gitignore",
    "AGENTS.md",
    ".env.example",
    "PUSH_TO_GITHUB.md",
    "RACECONTROL.md",
    "README.md",
    "Dockerfile",
    "cloudbuild.yaml",
    "config.example.py",
    "f1_live_bot.py",
    "requirements.txt",
    "state/sent_items.json",
]

REQUIRED_FUNCTIONS = [
    "post_news",
    "post_standings",
    "post_next_weekend_schedule",
    "post_latest_session_results",
    "post_fastest_lap",
    "post_race_weekend_reminder",
    "post_weather",
    "load_state",
    "save_state",
    "was_sent",
    "record_sent",
]


def main() -> int:
    failures = []

    for file_path in REQUIRED_FILES:
        if not Path(file_path).exists():
            failures.append(f"Missing required file: {file_path}")

    bot_file = Path("f1_live_bot.py")
    if bot_file.exists():
        try:
            tree = ast.parse(bot_file.read_text(encoding="utf-8"))
            functions = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
            for function_name in REQUIRED_FUNCTIONS:
                if function_name not in functions:
                    failures.append(f"Missing required function: {function_name}")
        except SyntaxError as error:
            failures.append(f"Python syntax error: {error}")

    workflow_file = Path(".github/workflows/f1-bot.yml")
    if workflow_file.exists():
        try:
            workflow = yaml.safe_load(workflow_file.read_text(encoding="utf-8"))
            trigger = workflow.get("on", workflow.get(True, {}))
            cron = trigger["schedule"][0]["cron"]
            if cron != "*/15 * * * *":
                failures.append(f"Expected 15-minute workflow schedule, got: {cron}")
            if workflow.get("permissions", {}).get("contents") != "write":
                failures.append("Workflow needs permissions.contents: write for dedupe state commits.")
        except Exception as error:
            failures.append(f"Workflow parse/check failed: {error}")

    public_files = [
        "f1_live_bot.py",
        ".github/workflows/f1-bot.yml",
        "README.md",
        "config.example.py",
        ".env.example",
        "Dockerfile",
        "cloudbuild.yaml",
        "RACECONTROL.md",
    ]
    live_webhook_pattern = re.compile(r"discord\.com/api/webhooks/\d+")
    for file_path in public_files:
        path = Path(file_path)
        if path.exists() and live_webhook_pattern.search(path.read_text(encoding="utf-8")):
            failures.append(f"Live Discord webhook appears in public file: {file_path}")

    if failures:
        print("Validation failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("Validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
