# F1 Discord Automation

Hands-off Formula 1 Discord posting for Google Cloud Run Jobs, with GitHub Actions still available as a fallback.

The bot is not a long-running local process. Each run starts, checks the requested task, posts anything new or due, writes dedupe state, and exits cleanly.

## What It Posts

- F1 news every 15 minutes when new RSS items appear
- Driver and constructor standings every 6 hours
- Next race/weekend schedule daily
- Latest available session results during race weekends
- Fastest lap when FastF1 lap data becomes available
- Daily race-weekend reminder
- Daily weather update when `WEATHER_API_URL` is configured

## Data Sources

- FastF1 for F1 schedule, session results, and lap data
- Jolpica/Ergast API for championship standings
- RSS feeds for F1 news
- Optional weather API URL supplied by you
- RaceControl reference: [RACECONTROL.md](RACECONTROL.md)

RaceControl is an archived open-source F1TV desktop client. This bot does not clone, build, or depend on it at runtime; it stays cloud-friendly and avoids local desktop dependencies.

## Files

```text
F1-Discord-Bot/
|-- .github/workflows/f1-bot.yml
|-- .dockerignore
|-- .env.example
|-- AGENTS.md
|-- Dockerfile
|-- RACECONTROL.md
|-- README.md
|-- cloudbuild.yaml
|-- config.example.py
|-- f1_live_bot.py
|-- requirements.txt
`-- state/sent_items.json
```

## Google Cloud Setup

This setup uses:

- Cloud Run Jobs to run the bot once and exit
- Cloud Scheduler to trigger each job on a cron schedule
- Secret Manager for Discord webhook URLs
- Cloud Storage for dedupe state

Set your shell variables:

```bash
export PROJECT_ID="your-google-cloud-project"
export REGION="europe-west2"
export REPOSITORY="f1-discord-bot"
export IMAGE="f1-discord-bot"
export STATE_BUCKET="${PROJECT_ID}-f1-bot-state"
export BOT_SERVICE_ACCOUNT="f1-discord-bot@${PROJECT_ID}.iam.gserviceaccount.com"
export SCHEDULER_SERVICE_ACCOUNT="f1-discord-scheduler@${PROJECT_ID}.iam.gserviceaccount.com"
```

Enable APIs:

```bash
gcloud services enable run.googleapis.com cloudscheduler.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com storage.googleapis.com
```

Create service accounts and state bucket:

```bash
gcloud iam service-accounts create f1-discord-bot --display-name="F1 Discord Bot"
gcloud iam service-accounts create f1-discord-scheduler --display-name="F1 Discord Scheduler"

gcloud storage buckets create "gs://${STATE_BUCKET}" --location="${REGION}"
gcloud storage buckets add-iam-policy-binding "gs://${STATE_BUCKET}" --member="serviceAccount:${BOT_SERVICE_ACCOUNT}" --role="roles/storage.objectAdmin"
```

Create the Artifact Registry repository:

```bash
gcloud artifacts repositories create "${REPOSITORY}" --repository-format=docker --location="${REGION}" --description="F1 Discord bot images"
```

Create Secret Manager secrets. Add only the webhooks you use:

```bash
printf "PASTE_ROTATED_NEWS_WEBHOOK" | gcloud secrets create NEWS_WEBHOOK --data-file=-
printf "PASTE_ROTATED_STANDINGS_WEBHOOK" | gcloud secrets create STANDINGS_WEBHOOK --data-file=-
printf "PASTE_ROTATED_SCHEDULE_WEBHOOK" | gcloud secrets create SCHEDULE_WEBHOOK --data-file=-
printf "PASTE_ROTATED_RESULTS_WEBHOOK" | gcloud secrets create RESULTS_WEBHOOK --data-file=-
printf "PASTE_ROTATED_FASTEST_LAP_WEBHOOK" | gcloud secrets create FASTEST_LAP_WEBHOOK --data-file=-
printf "PASTE_ROTATED_RACE_CONTROL_WEBHOOK" | gcloud secrets create RACE_CONTROL_WEBHOOK --data-file=-
printf "PASTE_ROTATED_WEATHER_WEBHOOK" | gcloud secrets create WEATHER_WEBHOOK --data-file=-
```

Grant the bot service account access to the secrets you created:

```bash
for SECRET in NEWS_WEBHOOK STANDINGS_WEBHOOK SCHEDULE_WEBHOOK RESULTS_WEBHOOK FASTEST_LAP_WEBHOOK RACE_CONTROL_WEBHOOK WEATHER_WEBHOOK; do
  gcloud secrets add-iam-policy-binding "${SECRET}" --member="serviceAccount:${BOT_SERVICE_ACCOUNT}" --role="roles/secretmanager.secretAccessor"
done
```

If you did not create every secret in that list, remove the missing names from the loop and from `COMMON_SECRETS` below.

Build the container:

```bash
gcloud builds submit --config cloudbuild.yaml --substitutions _REGION="${REGION}",_REPOSITORY="${REPOSITORY}",_IMAGE="${IMAGE}"
export IMAGE_URL="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/${IMAGE}:latest"
```

## Cloud Run Jobs

Create one Cloud Run Job per cadence. They all use the same image and only change `BOT_MODE`.

Common settings:

```bash
export COMMON_ENV="STATE_BACKEND=gcs,GCS_STATE_BUCKET=${STATE_BUCKET},GCS_STATE_BLOB=f1-discord-bot/sent_items.json,SEASON=2026,NEWS_LIMIT=5,STANDINGS_LIMIT=10"
export COMMON_SECRETS="NEWS_WEBHOOK=NEWS_WEBHOOK:latest,STANDINGS_WEBHOOK=STANDINGS_WEBHOOK:latest,SCHEDULE_WEBHOOK=SCHEDULE_WEBHOOK:latest,RESULTS_WEBHOOK=RESULTS_WEBHOOK:latest,FASTEST_LAP_WEBHOOK=FASTEST_LAP_WEBHOOK:latest,RACE_CONTROL_WEBHOOK=RACE_CONTROL_WEBHOOK:latest,WEATHER_WEBHOOK=WEATHER_WEBHOOK:latest"
```

`COMMON_SECRETS` must only include Secret Manager secrets that actually exist.

Create jobs:

```bash
gcloud run jobs create f1-bot-news --image="${IMAGE_URL}" --region="${REGION}" --service-account="${BOT_SERVICE_ACCOUNT}" --set-env-vars="${COMMON_ENV},BOT_MODE=news" --set-secrets="${COMMON_SECRETS}" --tasks=1 --max-retries=1 --task-timeout=30m

gcloud run jobs create f1-bot-standings --image="${IMAGE_URL}" --region="${REGION}" --service-account="${BOT_SERVICE_ACCOUNT}" --set-env-vars="${COMMON_ENV},BOT_MODE=standings" --set-secrets="${COMMON_SECRETS}" --tasks=1 --max-retries=1 --task-timeout=30m

gcloud run jobs create f1-bot-schedule --image="${IMAGE_URL}" --region="${REGION}" --service-account="${BOT_SERVICE_ACCOUNT}" --set-env-vars="${COMMON_ENV},BOT_MODE=schedule" --set-secrets="${COMMON_SECRETS}" --tasks=1 --max-retries=1 --task-timeout=30m

gcloud run jobs create f1-bot-race-weekend --image="${IMAGE_URL}" --region="${REGION}" --service-account="${BOT_SERVICE_ACCOUNT}" --set-env-vars="${COMMON_ENV},BOT_MODE=race-weekend" --set-secrets="${COMMON_SECRETS}" --tasks=1 --max-retries=1 --task-timeout=30m

gcloud run jobs create f1-bot-weather --image="${IMAGE_URL}" --region="${REGION}" --service-account="${BOT_SERVICE_ACCOUNT}" --set-env-vars="${COMMON_ENV},BOT_MODE=weather,WEATHER_API_URL=https://your-weather-api.example/forecast" --set-secrets="${COMMON_SECRETS}" --tasks=1 --max-retries=1 --task-timeout=30m
```

Test a job:

```bash
gcloud run jobs execute f1-bot-news --region="${REGION}" --wait
```

## Cloud Scheduler

Grant Scheduler permission to run Cloud Run Jobs:

```bash
for JOB in f1-bot-news f1-bot-standings f1-bot-schedule f1-bot-race-weekend f1-bot-weather; do
  gcloud run jobs add-iam-policy-binding "${JOB}" --region="${REGION}" --member="serviceAccount:${SCHEDULER_SERVICE_ACCOUNT}" --role="roles/run.invoker"
done
```

Cloud Scheduler calls the Cloud Run Jobs Admin API. Use OAuth because the target is `run.googleapis.com`.

```bash
gcloud scheduler jobs create http f1-bot-news-every-15m --location="${REGION}" --schedule="*/15 * * * *" --uri="https://run.googleapis.com/v2/projects/${PROJECT_ID}/locations/${REGION}/jobs/f1-bot-news:run" --http-method=POST --oauth-service-account-email="${SCHEDULER_SERVICE_ACCOUNT}"

gcloud scheduler jobs create http f1-bot-standings-every-6h --location="${REGION}" --schedule="0 */6 * * *" --uri="https://run.googleapis.com/v2/projects/${PROJECT_ID}/locations/${REGION}/jobs/f1-bot-standings:run" --http-method=POST --oauth-service-account-email="${SCHEDULER_SERVICE_ACCOUNT}"

gcloud scheduler jobs create http f1-bot-schedule-daily --location="${REGION}" --schedule="0 9 * * *" --time-zone="Europe/London" --uri="https://run.googleapis.com/v2/projects/${PROJECT_ID}/locations/${REGION}/jobs/f1-bot-schedule:run" --http-method=POST --oauth-service-account-email="${SCHEDULER_SERVICE_ACCOUNT}"

gcloud scheduler jobs create http f1-bot-race-weekend-every-15m --location="${REGION}" --schedule="*/15 * * * *" --uri="https://run.googleapis.com/v2/projects/${PROJECT_ID}/locations/${REGION}/jobs/f1-bot-race-weekend:run" --http-method=POST --oauth-service-account-email="${SCHEDULER_SERVICE_ACCOUNT}"

gcloud scheduler jobs create http f1-bot-weather-daily --location="${REGION}" --schedule="0 8 * * *" --time-zone="Europe/London" --uri="https://run.googleapis.com/v2/projects/${PROJECT_ID}/locations/${REGION}/jobs/f1-bot-weather:run" --http-method=POST --oauth-service-account-email="${SCHEDULER_SERVICE_ACCOUNT}"
```

## Duplicate Prevention

For Google Cloud, set:

```text
STATE_BACKEND=gcs
GCS_STATE_BUCKET=your-f1-bot-state-bucket
GCS_STATE_BLOB=f1-discord-bot/sent_items.json
```

The bot stores sent item IDs and last-run timestamps in that Cloud Storage JSON file. News, session results, and fastest laps are deduped by item/content. Schedule, reminders, and weather are deduped daily. Standings are deduped per 6-hour window.

## GitHub Actions Fallback

GitHub Actions remains available in:

```text
.github/workflows/f1-bot.yml
```

Use GitHub repository secrets with the same webhook names:

```text
NEWS_WEBHOOK
STANDINGS_WEBHOOK
SCHEDULE_WEBHOOK
RESULTS_WEBHOOK
FASTEST_LAP_WEBHOOK
RACE_CONTROL_WEBHOOK
WEATHER_WEBHOOK
LIVE_TIMING_WEBHOOK
```

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

Run validation:

```cmd
python validate_bot.py
python -m py_compile f1_live_bot.py validate_bot.py
```

## Safety

Never hardcode Discord webhook URLs in public files.

If a webhook URL has been pasted into chat, GitHub, or anywhere public, delete and recreate that Discord webhook before using it as a GitHub Secret or Google Secret Manager secret.

## Troubleshooting

- If a data source fails, the bot logs the error and continues with the next section.
- If FastF1 is slow, the job may be downloading timing data for the first time.
- If nothing posts, check the Cloud Run Job logs and confirm the matching Secret Manager secret exists.
- If duplicates happen, check the Cloud Storage state object.
