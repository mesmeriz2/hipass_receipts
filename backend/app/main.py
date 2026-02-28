import asyncio
import uuid
from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request

from . import config, scraper, scheduler

# Active background jobs: job_id -> {"total": N, "done": N, "current_date": str, "finished": bool}
_jobs: dict[str, dict] = {}

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.start(config.SCHEDULE_HOUR)
    yield
    scheduler.stop()


app = FastAPI(title="HiPass Receipt Viewer", lifespan=lifespan)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount(
    "/screenshots",
    StaticFiles(directory=str(config.SCREENSHOTS_DIR)),
    name="screenshots",
)


def _list_screenshots() -> list[dict]:
    """Return sorted list of {date, filename} for existing PNGs."""
    results = []
    today = date.today()
    cutoff = today - timedelta(days=config.RETENTION_DAYS - 1)

    for i in range(config.RETENTION_DAYS):
        d = today - timedelta(days=i)
        if d < cutoff:
            break
        date_str = d.strftime("%Y-%m-%d")
        filename = f"하이패스({date_str}).png"
        exists = (config.SCREENSHOTS_DIR / filename).exists()
        results.append(
            {
                "date": date_str,
                "filename": filename if exists else None,
                "exists": exists,
            }
        )
    return results


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    screenshots = _list_screenshots()
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "screenshots": screenshots},
    )


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/api/screenshots")
async def api_screenshots():
    return _list_screenshots()


@app.post("/api/refresh")
async def api_refresh(background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"total": config.RETENTION_DAYS, "done": 0, "current_date": "", "finished": False}

    def progress_cb(done: int, total: int, current_date: str):
        _jobs[job_id]["done"] = done
        _jobs[job_id]["current_date"] = current_date

    async def run():
        await scraper.capture_last_n_days(
            n=config.RETENTION_DAYS, progress_callback=progress_cb
        )
        _jobs[job_id]["finished"] = True

    background_tasks.add_task(run)
    return {"job_id": job_id}


@app.get("/api/status/{job_id}")
async def api_status(job_id: str):
    job = _jobs.get(job_id)
    if job is None:
        return {"error": "not found"}
    return job


@app.post("/api/capture/{date_str}")
async def api_capture_single(date_str: str, background_tasks: BackgroundTasks):
    try:
        target_date = date.fromisoformat(date_str)
    except ValueError:
        return {"error": f"날짜 형식 오류: {date_str!r} (YYYY-MM-DD 필요)"}

    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"total": 1, "done": 0, "current_date": date_str, "finished": False}

    def progress_cb(done: int, total: int, current_date: str):
        _jobs[job_id]["done"] = done
        _jobs[job_id]["current_date"] = current_date

    async def run():
        await scraper.capture_single_date_standalone(
            target_date=target_date, progress_callback=progress_cb
        )
        _jobs[job_id]["finished"] = True

    background_tasks.add_task(run)
    return {"job_id": job_id}


@app.get("/api/logs")
async def api_logs():
    return scraper.capture_logs
