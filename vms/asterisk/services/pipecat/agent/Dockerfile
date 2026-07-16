FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# Large wheels (torch via silero) can stall a single read; give pip a generous
# per-read timeout and several retries so a transient hiccup does not fail the
# whole build. Especially relevant behind constrained/NATed lab networks.
RUN pip install --no-cache-dir --timeout 180 --retries 8 -r requirements.txt

COPY audiosocket.py agent.py ./

CMD ["python", "-u", "agent.py"]
