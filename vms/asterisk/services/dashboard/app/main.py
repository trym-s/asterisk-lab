"""Read-only FastAPI + Tabler dashboard for the voicebot JSONL telemetry.

Serves rendered pages backed by a JSON API. Never writes to the sinks it
reads and never calls a model provider.
"""

from __future__ import annotations

import os
import secrets
import sys
import time
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
# Repo tree: services/dashboard/app is a sibling of services/common. The
# installer copies both app/ and common/ to /opt/voicebot-dashboard and
# points VOICEBOT_COMMON_DIR at the copy, since that layout no longer
# matches the repo tree's relative depth.
_DEFAULT_COMMON_DIR = APP_DIR.parent.parent / "common"
COMMON_DIR = Path(os.environ.get("VOICEBOT_COMMON_DIR", str(_DEFAULT_COMMON_DIR)))
if str(COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_DIR))

from fastapi import Depends, FastAPI, HTTPException, Request  # noqa: E402
from fastapi.responses import HTMLResponse  # noqa: E402
from fastapi.security import HTTPBasic, HTTPBasicCredentials  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from fastapi.templating import Jinja2Templates  # noqa: E402

import data  # noqa: E402
from config import Settings, load_settings  # noqa: E402
from usage_summary import parse_since  # noqa: E402

settings = load_settings()
app = FastAPI(title="Voicebot Observability Dashboard")
app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))

_basic_auth = HTTPBasic(auto_error=False)


def require_auth(credentials: HTTPBasicCredentials | None = Depends(_basic_auth)) -> None:
    if not settings.basic_auth_user or not settings.basic_auth_password:
        return
    valid_user = credentials is not None and secrets.compare_digest(
        credentials.username, settings.basic_auth_user
    )
    valid_password = credentials is not None and secrets.compare_digest(
        credentials.password, settings.basic_auth_password
    )
    if not (valid_user and valid_password):
        raise HTTPException(
            status_code=401,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Basic"},
        )


def get_settings() -> Settings:
    return settings


# ---- page routes ----------------------------------------------------------


@app.get("/", response_class=HTMLResponse, dependencies=[Depends(require_auth)])
def page_overview(request: Request):
    return templates.TemplateResponse(
        request, "overview.html", {"refresh_s": settings.refresh_s}
    )


@app.get("/parity", response_class=HTMLResponse, dependencies=[Depends(require_auth)])
def page_parity(request: Request):
    return templates.TemplateResponse(
        request, "parity.html", {"refresh_s": settings.refresh_s}
    )


@app.get("/cost", response_class=HTMLResponse, dependencies=[Depends(require_auth)])
def page_cost(request: Request):
    return templates.TemplateResponse(
        request, "cost.html", {"refresh_s": settings.refresh_s}
    )


@app.get("/transcript", response_class=HTMLResponse, dependencies=[Depends(require_auth)])
def page_transcript(request: Request):
    return templates.TemplateResponse(
        request, "transcript.html", {"refresh_s": settings.refresh_s}
    )


@app.get("/transcriber", response_class=HTMLResponse, dependencies=[Depends(require_auth)])
def page_transcriber(request: Request):
    return templates.TemplateResponse(
        request, "transcriber.html", {"refresh_s": settings.refresh_s}
    )


# ---- JSON API --------------------------------------------------------------


@app.get("/api/calls", dependencies=[Depends(require_auth)])
def api_calls():
    events = data.load_events(settings.events_path)
    return {"calls": data.list_calls(events)}


@app.get("/api/turns", dependencies=[Depends(require_auth)])
def api_turns(call_id: str):
    events = data.load_events(settings.events_path)
    return {"call_id": call_id, "turns": data.turns_for_call(events, call_id)}


@app.get("/api/parity", dependencies=[Depends(require_auth)])
def api_parity():
    events = data.load_events(settings.events_path)
    usage_rows = data.load_usage(settings.usage_path)
    return data.lane_parity(events, usage_rows)


@app.get("/api/cost", dependencies=[Depends(require_auth)])
def api_cost(since: str | None = None):
    usage_rows = data.load_usage(settings.usage_path)
    since_ts = parse_since(since) if since else 0
    return data.cost_summary(usage_rows, since_ts)


@app.get("/api/transcriber", dependencies=[Depends(require_auth)])
def api_transcriber():
    return data.transcriber_status(settings.monitor_dir)


@app.get("/api/healthz")
def healthz():
    return {"status": "ok", "ts": time.time()}
