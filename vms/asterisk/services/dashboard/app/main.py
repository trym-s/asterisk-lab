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
from fastapi.responses import HTMLResponse, RedirectResponse  # noqa: E402
from fastapi.security import HTTPBasic, HTTPBasicCredentials  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from fastapi.templating import Jinja2Templates  # noqa: E402

import data  # noqa: E402
from config import Settings, load_settings  # noqa: E402
from usage_summary import parse_since  # noqa: E402
from zabbix_client import ZabbixClient, ZabbixConfig  # noqa: E402

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


def _page_context(request: Request, **extra):
    context = {
        "request": request,
        "refresh_s": settings.refresh_s,
        "default_range": settings.default_range,
        "cost_bucket": settings.cost_bucket,
    }
    context.update(extra)
    return context


def _since_ts(since: str | None) -> float:
    return parse_since(since or settings.default_range)


def _bucket_s(bucket: str | None) -> int:
    return data.duration_seconds(bucket or settings.cost_bucket, 3600)


def _uptime_payload(since: str | None):
    client = ZabbixClient(
        ZabbixConfig(
            api_url=settings.zabbix_api_url,
            api_token=settings.zabbix_api_token,
        )
    )
    return client.uptime_summary(_since_ts(since))


# ---- page routes ----------------------------------------------------------


@app.get("/", response_class=HTMLResponse, dependencies=[Depends(require_auth)])
def page_overview(request: Request):
    return templates.TemplateResponse(request, "overview.html", _page_context(request))


@app.get("/calls", response_class=HTMLResponse, dependencies=[Depends(require_auth)])
def page_calls(request: Request):
    return templates.TemplateResponse(request, "calls.html", _page_context(request))


@app.get("/calls/{call_id}", response_class=HTMLResponse, dependencies=[Depends(require_auth)])
def page_call_detail(request: Request, call_id: str):
    return templates.TemplateResponse(
        request,
        "call_detail.html",
        _page_context(request, call_id=call_id),
    )


@app.get("/parity", response_class=HTMLResponse, dependencies=[Depends(require_auth)])
def page_parity(request: Request):
    return templates.TemplateResponse(request, "parity.html", _page_context(request))


@app.get("/comparison", response_class=HTMLResponse, dependencies=[Depends(require_auth)])
def page_comparison(request: Request):
    return templates.TemplateResponse(request, "comparison.html", _page_context(request))


@app.get("/cost", response_class=HTMLResponse, dependencies=[Depends(require_auth)])
def page_cost(request: Request):
    return templates.TemplateResponse(request, "cost.html", _page_context(request))


@app.get("/transcript", response_class=HTMLResponse, dependencies=[Depends(require_auth)])
def page_transcript(request: Request):
    call_id = request.query_params.get("call_id")
    if call_id:
        return RedirectResponse(f"/calls/{call_id}", status_code=307)
    return RedirectResponse("/calls", status_code=307)


@app.get("/transcriber", response_class=HTMLResponse, dependencies=[Depends(require_auth)])
def page_transcriber(request: Request):
    return templates.TemplateResponse(request, "transcriber.html", _page_context(request))


# ---- JSON API --------------------------------------------------------------


@app.get("/api/overview", dependencies=[Depends(require_auth)])
def api_overview(since: str | None = None):
    events = data.load_events(settings.events_path)
    usage_rows = data.load_usage(settings.usage_path)
    calls = data.list_calls(
        events,
        settings.monitor_dir,
        active_stale_s=settings.active_call_stale_s,
    )
    active_calls = [call for call in calls if call["in_progress"]]
    return {
        "range": since or settings.default_range,
        "cost": data.cost_summary(usage_rows, _since_ts(since)),
        "active_calls": {
            "count": len(active_calls),
            "calls": active_calls[:8],
        },
        "extensions": data.extension_status(settings.asterisk_cli),
        "uptime": _uptime_payload(since),
        "recent_calls": calls[:8],
    }


@app.get("/api/extensions", dependencies=[Depends(require_auth)])
def api_extensions():
    return data.extension_status(settings.asterisk_cli)


@app.get("/api/uptime", dependencies=[Depends(require_auth)])
def api_uptime(since: str | None = None):
    return _uptime_payload(since)


@app.get("/api/calls", dependencies=[Depends(require_auth)])
def api_calls(status: str | None = None):
    events = data.load_events(settings.events_path)
    calls = data.list_calls(
        events,
        settings.monitor_dir,
        active_stale_s=settings.active_call_stale_s,
    )
    if status == "in-progress":
        calls = [call for call in calls if call["in_progress"]]
    return {"calls": calls}


@app.get("/api/turns", dependencies=[Depends(require_auth)])
def api_turns(call_id: str):
    events = data.load_events(settings.events_path)
    return {
        "call_id": call_id,
        "call": data.call_summary(
            events,
            call_id,
            settings.monitor_dir,
            active_stale_s=settings.active_call_stale_s,
        ),
        "turns": data.turns_for_call(events, call_id),
    }


@app.get("/api/calls/{call_id}/turns", dependencies=[Depends(require_auth)])
def api_call_turns(call_id: str):
    events = data.load_events(settings.events_path)
    return {
        "call_id": call_id,
        "call": data.call_summary(
            events,
            call_id,
            settings.monitor_dir,
            active_stale_s=settings.active_call_stale_s,
        ),
        "turns": data.turns_for_call(events, call_id),
    }


@app.get("/api/parity", dependencies=[Depends(require_auth)])
def api_parity():
    events = data.load_events(settings.events_path)
    usage_rows = data.load_usage(settings.usage_path)
    return data.lane_parity(events, usage_rows)


@app.get("/api/cost", dependencies=[Depends(require_auth)])
def api_cost(since: str | None = None):
    usage_rows = data.load_usage(settings.usage_path)
    return data.cost_summary(usage_rows, _since_ts(since) if since else 0)


@app.get("/api/cost/timeseries", dependencies=[Depends(require_auth)])
def api_cost_timeseries(since: str | None = None, bucket: str | None = None):
    usage_rows = data.load_usage(settings.usage_path)
    return data.cost_timeseries(usage_rows, _since_ts(since), _bucket_s(bucket))


@app.get("/api/transcriber", dependencies=[Depends(require_auth)])
def api_transcriber():
    return data.transcriber_status(settings.monitor_dir)


# ---- LiveKit vs Pipecat fair comparison ----------------------------


@app.get("/api/comparison/fairness", dependencies=[Depends(require_auth)])
def api_comparison_fairness(run_id: str | None = None):
    events = data.load_events(settings.events_path)
    usage_rows = data.load_usage(settings.usage_path)
    return data.fairness_gate(events, usage_rows, run_id)


@app.get("/api/comparison/quality", dependencies=[Depends(require_auth)])
def api_comparison_quality(run_id: str | None = None):
    events = data.load_events(settings.events_path)
    expected_corpus = data.load_expected_corpus(settings.expected_corpus_path)
    return data.paired_quality(events, expected_corpus, run_id)


@app.get("/api/comparison/latency", dependencies=[Depends(require_auth)])
def api_comparison_latency(run_id: str | None = None):
    events = data.load_events(settings.events_path)
    return data.latency_decision(events, run_id, settings.latency_min_n)


@app.get("/api/comparison/reliability", dependencies=[Depends(require_auth)])
def api_comparison_reliability(run_id: str | None = None):
    events = data.load_events(settings.events_path)
    return data.reliability_summary(
        events,
        run_id,
        active_stale_s=settings.active_call_stale_s,
    )


@app.get("/api/comparison/cost", dependencies=[Depends(require_auth)])
def api_comparison_cost(run_id: str | None = None):
    events = data.load_events(settings.events_path)
    usage_rows = data.load_usage(settings.usage_path)
    return data.cost_normalized(usage_rows, events, run_id)


@app.get("/api/healthz")
def healthz():
    return {"status": "ok", "ts": time.time()}
