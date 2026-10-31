# Build from the repo root:  docker build -f studybot/Dockerfile -t studybot .
FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 STUDYBOT_DATA_DIR=/data

# Noto Sans draws the quiz cards (covers Vietnamese and other accented scripts); ffmpeg + libopus play game music.
RUN apt-get update && apt-get install -y --no-install-recommends fonts-noto-core ffmpeg libopus0 \
    && rm -rf /var/lib/apt/lists/*

COPY studybot/requirements.txt studybot/requirements.txt
RUN pip install --no-cache-dir -r studybot/requirements.txt

COPY studybot/ studybot/

# The database lives here; mount a volume so decks and scores survive redeploys.
VOLUME /data
CMD ["python", "-m", "studybot"]
