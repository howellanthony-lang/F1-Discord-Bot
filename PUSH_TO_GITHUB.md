# Push This Bot To GitHub

This is the final step that makes the bot run while your PC is off.

## 1. Create An Empty GitHub Repo

Create a new empty GitHub repository named something like:

```text
F1-Discord-Bot
```

Do not add a README, `.gitignore`, or license on GitHub because this local folder already has the files.

Your detected GitHub username is:

```text
howellanthony-lang
```

## 2. Add The GitHub Remote

In Windows CMD or PowerShell:

```cmd
cd C:\Users\howel\OneDrive\Documents\F1-Discord-Bot
git remote add origin https://github.com/howellanthony-lang/F1-Discord-Bot.git
```

## 3. Push The Repo

```cmd
git push -u origin main
```

## 4. Add GitHub Actions Secrets

Open the GitHub repo in your browser.

Go to:

```text
Settings -> Secrets and variables -> Actions -> New repository secret
```

Add the webhook secrets you want to use:

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

Use newly rotated Discord webhooks. Do not reuse webhook URLs that were pasted into chat or exposed publicly.

## 5. Enable And Run The Workflow

Open:

```text
Actions -> F1 Discord Automation
```

Then click:

```text
Run workflow
```

The scheduled workflow will also run automatically every 15 minutes.

## 6. Confirm It Is Hands-Off

After a successful GitHub Actions run, your PC can be off. GitHub Actions will keep running the scheduled bot from GitHub.
