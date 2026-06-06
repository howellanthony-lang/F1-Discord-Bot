# RaceControl Reference

Reference repository:

https://github.com/robvdpol/RaceControl.git

RaceControl is an archived open-source F1TV desktop client for Windows. This automation system does not clone, build, run, or depend on RaceControl in GitHub Actions.

The goal here is different: a hands-off Discord automation bot that runs as scheduled GitHub Actions jobs, uses public F1 data sources, stores lightweight dedupe state, and exits after each run.

Keeping RaceControl as a reference avoids adding desktop runtime dependencies, F1TV account requirements, Windows-only build steps, or long-running local processes.
