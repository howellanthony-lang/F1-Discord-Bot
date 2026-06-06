# F1 Discord Bot Agent Instructions

This repository contains a beginner-friendly Python Discord webhook bot for Formula 1 updates.

Goal:
- Post F1 weekend schedule using FastF1.
- Post driver standings using the Jolpica/Ergast API.
- Post constructor standings using the Jolpica/Ergast API.
- Post latest F1 news from RSS feeds.
- Post latest available session results using FastF1.
- Post fastest lap from the latest available session using FastF1.

Rules:
- Do not hardcode Discord webhook URLs in `f1_live_bot.py`.
- Read webhook URLs from `config.py`.
- Keep `config.py` local only. It must not be committed.
- Keep `config.example.py` safe for public GitHub use.
- Add clear print statements so beginners can see what the bot is doing.
- Add error handling so one failed section does not stop the whole bot.
- Make the script run once and exit.
- Keep setup and run instructions friendly for Windows CMD users.

Check before finishing:
- Imports are correct.
- `requirements.txt` includes needed packages.
- Bad or missing config is handled clearly.
- Empty webhook values are ignored.
- Discord webhook posting works.
- FastF1 cache uses the local `cache/` folder.
