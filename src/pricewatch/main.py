from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from pricewatch.api.routes import router as api_router
from pricewatch.config import get_settings
from pricewatch.db.database import init_db
from pricewatch.scheduler import PriceWatchScheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
scheduler = PriceWatchScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    scheduler.start()
    logger.info("Pricewatch started")
    yield
    scheduler.shutdown()
    logger.info("Pricewatch stopped")


app = FastAPI(
    title="Pricewatch",
    description="Track product prices with Ollama and local Good-search MCP",
    version="0.1.0",
    lifespan=lifespan,
)

static_dir = BASE_DIR / "static"
templates_dir = BASE_DIR / "templates"
static_dir.mkdir(exist_ok=True)
templates_dir.mkdir(exist_ok=True)

app.mount("/static", StaticFiles(directory=static_dir), name="static")
templates = Jinja2Templates(directory=templates_dir)
app.include_router(api_router)


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        context={"request": request},
    )


@app.get("/health")
async def health() -> dict:
    from pricewatch.services.good_search import GoodSearchClient, GoodSearchError

    settings = get_settings()
    payload = {
        "status": "ok",
        "ollama": settings.ollama_base_url,
        "model": settings.ollama_model,
        "good_search_mcp_url": settings.good_search_mcp_url,
        "check_interval_minutes": settings.check_interval_minutes,
    }

    try:
        payload["good_search"] = await GoodSearchClient(settings).health_check()
    except GoodSearchError as exc:
        payload["good_search"] = {"reachable": False, "error": str(exc)}

    return payload


def run() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "pricewatch.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    run()
