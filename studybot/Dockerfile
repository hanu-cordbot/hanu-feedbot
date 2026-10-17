# Build from the repo root:  docker build -f studybot/Dockerfile -t studybot .
FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 STUDYBOT_DATA_DIR=/data

COPY studybot/requirements.txt studybot/requirements.txt
RUN pip install --no-cache-dir -r studybot/requirements.txt

COPY studybot/ studybot/

# The database lives here; mount a volume so decks and scores survive redeploys.
VOLUME /data
CMD ["python", "-m", "studybot"]
