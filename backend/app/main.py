from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db import SessionLocal
from app.routers import health, jobs
from app.services.jobs import JobRunner

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
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
app.include_router(health.router, prefix="/api")
app.include_router(jobs.router, prefix="/api")
