FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY f1_live_bot.py .
COPY state/sent_items.json state/sent_items.json

ENTRYPOINT ["python", "f1_live_bot.py"]
