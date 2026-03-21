"""FastAPI application entry point.

Registers all routers and middleware.  Run with:
    uvicorn nekospeech.main:app --host 0.0.0.0 --port 8001 --reload
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from nekospeech.config import settings
from nekospeech.routers import ballots, draw, entries, events, standings, ws


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown hooks."""
    # Import here to avoid circular imports on module load
    from nekospeech.services.cache import redis_pool

    yield
    # Graceful shutdown
    await redis_pool.aclose()


app = FastAPI(
    title="nekospeech",
    description="Individual Speech Events API for NekoTab",
    version="0.1.0",
    lifespan=lifespan,
    root_path="/api/ie",
)

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Routers ---
app.include_router(events.router)
app.include_router(entries.router)
app.include_router(draw.router)
app.include_router(ballots.router)
app.include_router(standings.router)
app.include_router(ws.router)


@app.get("/api/ie/health")
async def health():
    return {"status": "ok", "service": "nekospeech"}
