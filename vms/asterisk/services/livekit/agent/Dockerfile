FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agent.py .

# NOTE: Silero VAD model is downloaded on first agent start (~15 MB, ~2s).
# We could pre-download it in the image, but keeping it out lets the layer
# stay reproducible and simplifies plugin version bumps.

CMD ["python", "agent.py", "start"]
