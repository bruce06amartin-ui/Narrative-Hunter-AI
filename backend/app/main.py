import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.api import routes_alerts, routes_coins, routes_ops, routes_wallets, routes_paper_trading

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Narrative Hunter AI",
    description="Meme coin discovery & scoring intelligence platform (MVP: Coin Discovery + Scoring modules).",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten this before deploying publicly
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes_coins.router)
app.include_router(routes_ops.router)
app.include_router(routes_alerts.router)
app.include_router(routes_wallets.router)
app.include_router(routes_paper_trading.router)


@app.on_event("startup")
def on_startup():
    logger.info("Starting Narrative Hunter AI (env=%s)", settings.app_env)
    init_db()


@app.get("/")
def root():
    return {
        "service": "Narrative Hunter AI",
        "status": "running",
        "modules_implemented": [
            "coin_discovery", "narrative_scanner (Reddit/CryptoPanic/X, each optional)",
            "narrative_ai (requires ANTHROPIC_API_KEY)", "wallet_intelligence (EVM only)",
            "community_intelligence (analyzes narrative_scanner data)", "rug_detection",
            "scoring (full spec: liquidity+trend+wallet+narrative+community, risk penalty)",
            "alerts (overall_score + risk_score + narrative_score + community_score thresholds, smart_wallet_accumulation)",
            "dashboard",
        ],
        "modules_pending": [
            "wallet_intelligence (Solana)", "narrative_scanner (Google Trends, Telegram)",
            "trend_detection (full velocity/acceleration/decay model)", "alerts (whale entry)",
        ],
        "docs": "/docs",
    }
