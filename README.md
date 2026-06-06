# F1 Discord Automation

Hands-off Formula 1 Discord posting powered by GitHub Actions.

The bot does not run as a long-lived local process. GitHub wakes it every 15 minutes, the script runs once, posts anything new or due, updates a small dedupe state file, and exits.

## What It Posts

- F1 news every 15 minutes when new RSS items appear
- Driver and constructor standings every 6 hours
- Next race/weekend schedule daily
- Latest available session results during race weekends
- Fastest lap when FastF1 lap data becomes available
- Daily race-weekend reminder

## Data Sources

- FastF1 for F1 schedule, session results, and lap data
- Jolpica/Ergast API for championship standings
- RSS feeds for F1 news
- RaceControl reference: [RACECONTROL.md](RACECONTROL.md)

RaceControl is an archived open-source F1TV desktop client. This bot does not clone, build, or depend on it at runtime; it stays GitHub Actions friendly and avoids local desktop dependencies.

## Files

```text
F1-Discord-Bot/
├── .github/workflows/f1-bot.yml
├── AGENTS.md
├── RACECONTROL.md
├── README.md
├── requirements.txt
├── .gitignore
├── config.example.py
├── config.py              # local only, never upload
├── f1_live_bot.py
└── state/sent_items.json  # created by GitHub Actions
```

## GitHub Setup

For exact push commands, see [PUSH_TO_GITHUB.md](PUSH_TO_GITHUB.md).

1. Create a GitHub repository.
2. Upload these files.
3. Do not upload `config.py`.
4. Open **Settings** in the GitHub repo.
5. Go to **Secrets and variables** then **Actions**.
6. Add these repository secrets:

```text
SCHEDULE_WEBHOOK
LIVE_TIMING_WEBHOOK
FASTEST_LAP_WEBHOOK
RACE_CONTROL_WEBHOOK
NEWS_WEBHOOK
WEATHER_WEBHOOK
STANDINGS_WEBHOOK
RESULTS_WEBHOOK
```

Only the webhooks you use need real values. Missing webhook secrets are skipped safely.

Optional repository variables:

```text
SEASON=2026
NEWS_LIMIT=5
STANDINGS_LIMIT=10
```

## Running

The workflow runs automatically every 15 minutes:

```text
.github/workflows/f1-bot.yml
```

You can also start it manually:

1. Open the repo on GitHub.
2. Click **Actions**.
3. Select **F1 Discord Automation**.
4. Click **Run workflow**.
5. Choose a mode: `auto`, `news`, `standings`, `schedule`, `race-weekend`, or `all`.

## Duplicate Prevention

The bot stores sent item IDs in:

```text
state/sent_items.json
```

GitHub Actions commits that file back to the repo when it changes. News, session results, and fastest laps are deduped by item/content. Schedule and reminder posts are deduped daily. Standings are deduped per 6-hour window so they can still post on the requested cadence.

## Local Testing

Local testing is optional. It is not required for the bot to run while your PC is off.

```cmd
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy config.example.py config.py
python f1_live_bot.py --mode news
```

Keep `config.py` private. It is ignored by Git.

You can also run a quick repo validation:

```cmd
python validate_bot.py
```

## Safety

Never hardcode Discord webhook URLs in `f1_live_bot.py`.

If a webhook URL has been pasted into chat, GitHub, or anywhere public, delete and recreate that Discord webhook before using it as a GitHub Secret.

## Troubleshooting

- If a data source fails, the bot logs the error and continues with the next section.
- If FastF1 is slow, the workflow may be downloading timing data for the first time.
- If nothing posts, check the Actions log and confirm the matching webhook secret exists.
- If duplicate posts happen, check that `state/sent_items.json` is being committed by the workflow.
