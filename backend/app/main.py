from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.db import SessionLocal
from app.routers import auth, ba, brd, campaigns, contract, health, jobs, plans, projects
from app.services import job_handlers, paypal_client  # noqa: F401  (job_handlers registers the job handlers)
from app.services.jobs import JobRunner

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # With PAYPAL_CLIENT_ID/SECRET set the real client replaces the fail-safe placeholders; without them money never moves.
    paypal_client.configure_from_settings(settings)
    runner = JobRunner(SessionLocal)
    runner.start()
    try:
        yield
    finally:
        await runner.stop()


app = FastAPI(title="BriefPay API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(HTTPException)
async def http_error(_request, exc: HTTPException) -> JSONResponse:
    """SPEC 10 error shape: {"error": {"code", "message", "details"}} at the top level."""
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        return JSONResponse(exc.detail, status_code=exc.status_code)
    return JSONResponse({"error": {"code": f"HTTP_{exc.status_code}", "message": str(exc.detail), "details": {}}},
                        status_code=exc.status_code)


for r in (health.router, auth.router, jobs.router, projects.router, ba.router, brd.router, contract.router, campaigns.router, plans.router):
    app.include_router(r, prefix="/api")
