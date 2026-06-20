"""FastAPI application entrypoint."""
import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .db import Base, engine
from .logging_config import configure_logging, log_event
from .monitor import offline_monitor
from .routers import agents, analysis, attribution, comparison, tasks

configure_logging()
logger = logging.getLogger("minidrop.server")
access_logger = logging.getLogger("minidrop.access")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Models are imported via routers; create all tables on boot (MVP migration strategy).
    Base.metadata.create_all(engine)
    os.makedirs(settings.artifacts_dir, exist_ok=True)
    monitor_task = asyncio.create_task(offline_monitor())
    log_event(logger, "server started", artifacts_dir=settings.artifacts_dir)
    try:
        yield
    finally:
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass
        log_event(logger, "server stopped")


app = FastAPI(title="Mini-Drop Server", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def access_log(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
    log_event(
        access_logger, "http",
        method=request.method, path=request.url.path,
        status=response.status_code, latency_ms=elapsed_ms,
    )
    return response


app.include_router(tasks.router)
app.include_router(agents.router)
app.include_router(analysis.router)
app.include_router(attribution.router)
app.include_router(comparison.router)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}
