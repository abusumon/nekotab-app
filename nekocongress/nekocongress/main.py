"""FastAPI application entry point for nekocongress.

Registers all routers and middleware.  Run with:
    uvicorn nekocongress.main:app --host 0.0.0.0 --port 8002 --reload
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from nekocongress.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown hooks."""
    from nekocongress.services.cache import redis_pool
    from nekocongress.websocket.redis_manager import channel_manager

    # Start Redis pub/sub listener for WebSocket fan-out
    await channel_manager.start()

    yield

    # Graceful shutdown
    await channel_manager.stop()
    await redis_pool.aclose()


app = FastAPI(
    title="nekocongress",
    description="Congressional Debate API for NekoTab",
    version="0.1.0",
    lifespan=lifespan,
)

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=r"https://([a-z0-9-]+\.)?nekotab\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Routers ---
from nekocongress.routers import (  # noqa: E402
    amendments,
    chambers,
    docket,
    floor,
    legislators,
    scores,
    sessions,
    standings,
    tournaments,
    ws,
)

app.include_router(tournaments.router)
app.include_router(chambers.router)
app.include_router(legislators.router)
app.include_router(docket.router)
app.include_router(sessions.router)
app.include_router(floor.router)
app.include_router(scores.router)
app.include_router(amendments.router)
app.include_router(standings.router)
app.include_router(ws.router)


@app.get("/api/congress/health")
async def health():
    return {"status": "ok", "service": "nekocongress"}
