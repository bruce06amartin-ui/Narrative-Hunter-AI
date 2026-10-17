import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from sqlalchemy import or_

from app.database import get_db
from app.models.alert import Alert
from app.models.coin import Coin
from app.models.community import Community
from app.models.narrative import Narrative
from app.models.risk_flag import RiskFlag
from app.models.score import Score, HistoricalScore
from app.models.social_post import SocialPost
from app.models.wallet import Wallet
from app.models.wallet_transaction import WalletTransaction
from app.api.routes_wallets import _attach_held_coins
from app.schemas.coin import (
    CoinOut, CoinWithScoreOut, HistoricalScorePoint, RiskFlagOut, AlertOut,
    NarrativeOut, SocialPostOut, CommunityOut,
)
from app.schemas.wallet import WalletOut

router = APIRouter(prefix="/api/coins", tags=["coins"])


@router.get("", response_model=list[CoinWithScoreOut])
def list_coins(
    chain: str | None = None,
    min_liquidity: float | None = None,
    search: str | None = Query(None, description="Case-insensitive match on symbol or name"),
    sort_by: str = Query(
        "overall_score",
        pattern="^(overall_score|risk_score|liquidity_usd|volume_24h_usd|launch_time)$",
    ),
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: Session = Depends(get_db),
):
    query = db.query(Coin).options(joinedload(Coin.scores)).filter(Coin.is_active.is_(True))

    if chain:
        query = query.filter(Coin.chain == chain)
    if min_liquidity is not None:
        query = query.filter(Coin.liquidity_usd >= min_liquidity)
    if search:
        like = f"%{search}%"
        query = query.filter(or_(Coin.symbol.ilike(like), Coin.name.ilike(like)))

    if sort_by in ("overall_score", "risk_score"):
        query = query.outerjoin(Score, Score.coin_id == Coin.id)
        sort_col = Score.overall_score if sort_by == "overall_score" else Score.risk_score
        query = query.order_by(sort_col.desc().nullslast())
    else:
        query = query.order_by(getattr(Coin, sort_by).desc().nullslast())

    coins = query.offset(offset).limit(limit).all()
    return [_attach_score(c) for c in coins]


@router.get("/top", response_model=list[CoinWithScoreOut])
def top_opportunities(limit: int = Query(20, le=100), db: Session = Depends(get_db)):
    coins = (
        db.query(Coin)
        .join(Score, Score.coin_id == Coin.id)
        .filter(Coin.is_active.is_(True), Score.overall_score.isnot(None))
        .order_by(Score.overall_score.desc())
        .limit(limit)
        .all()
    )
    return [_attach_score(c) for c in coins]


@router.get("/high-risk", response_model=list[CoinWithScoreOut])
def high_risk_coins(limit: int = Query(20, le=100), db: Session = Depends(get_db)):
    coins = (
        db.query(Coin)
        .join(Score, Score.coin_id == Coin.id)
        .filter(Coin.is_active.is_(True), Score.risk_score.isnot(None))
        .order_by(Score.risk_score.desc())
        .limit(limit)
        .all()
    )
    return [_attach_score(c) for c in coins]


@router.get("/{coin_id}", response_model=CoinWithScoreOut)
def get_coin(coin_id: uuid.UUID, db: Session = Depends(get_db)):
    coin = db.query(Coin).filter(Coin.id == coin_id).first()
    if coin is None:
        raise HTTPException(status_code=404, detail="Coin not found")
    return _attach_score(coin)


@router.get("/{coin_id}/history", response_model=list[HistoricalScorePoint])
def get_coin_score_history(coin_id: uuid.UUID, limit: int = Query(200, le=1000), db: Session = Depends(get_db)):
    coin = db.query(Coin).filter(Coin.id == coin_id).first()
    if coin is None:
        raise HTTPException(status_code=404, detail="Coin not found")

    history = (
        db.query(HistoricalScore)
        .filter(HistoricalScore.coin_id == coin_id)
        .order_by(HistoricalScore.recorded_at.desc())
        .limit(limit)
        .all()
    )
    return list(reversed(history))


@router.get("/{coin_id}/risk-flags", response_model=list[RiskFlagOut])
def get_coin_risk_flags(coin_id: uuid.UUID, db: Session = Depends(get_db)):
    coin = db.query(Coin).filter(Coin.id == coin_id).first()
    if coin is None:
        raise HTTPException(status_code=404, detail="Coin not found")

    return (
        db.query(RiskFlag)
        .filter(RiskFlag.coin_id == coin_id)
        .order_by(RiskFlag.points.desc())
        .all()
    )


@router.get("/{coin_id}/alerts", response_model=list[AlertOut])
def get_coin_alerts(coin_id: uuid.UUID, db: Session = Depends(get_db)):
    coin = db.query(Coin).filter(Coin.id == coin_id).first()
    if coin is None:
        raise HTTPException(status_code=404, detail="Coin not found")

    alerts = (
        db.query(Alert)
        .filter(Alert.coin_id == coin_id)
        .order_by(Alert.created_at.desc())
        .all()
    )
    out = []
    for a in alerts:
        item = AlertOut.model_validate(a)
        item.coin_symbol = coin.symbol
        item.coin_chain = coin.chain
        out.append(item)
    return out


@router.get("/{coin_id}/wallets", response_model=list[WalletOut])
def get_coin_holding_wallets(coin_id: uuid.UUID, limit: int = Query(20, le=100), db: Session = Depends(get_db)):
    """Wallets currently holding this coin (net inflow > 0), ranked by
    reputation. EVM chains only - see wallet_service.py for why Solana
    isn't covered."""
    coin = db.query(Coin).filter(Coin.id == coin_id).first()
    if coin is None:
        raise HTTPException(status_code=404, detail="Coin not found")

    from sqlalchemy import func, case

    net_expr = func.sum(
        case((WalletTransaction.direction == "in", WalletTransaction.amount), else_=-WalletTransaction.amount)
    )
    holding_ids_subq = (
        db.query(WalletTransaction.wallet_id)
        .filter(WalletTransaction.coin_id == coin_id)
        .group_by(WalletTransaction.wallet_id)
        .having(net_expr > 1e-9)
        .subquery()
    )

    wallets = (
        db.query(Wallet)
        .filter(Wallet.id.in_(db.query(holding_ids_subq.c.wallet_id)))
        .order_by(Wallet.reputation_score.desc().nullslast())
        .limit(limit)
        .all()
    )
    return _attach_held_coins(db, wallets)


@router.get("/{coin_id}/narrative", response_model=NarrativeOut)
def get_coin_narrative(coin_id: uuid.UUID, db: Session = Depends(get_db)):
    coin = db.query(Coin).filter(Coin.id == coin_id).first()
    if coin is None:
        raise HTTPException(status_code=404, detail="Coin not found")

    narrative = db.query(Narrative).filter(Narrative.coin_id == coin_id).first()
    if narrative is None:
        raise HTTPException(status_code=404, detail="No narrative analysis available for this coin yet")
    return narrative


@router.get("/{coin_id}/social-posts", response_model=list[SocialPostOut])
def get_coin_social_posts(
    coin_id: uuid.UUID, limit: int = Query(20, le=100), db: Session = Depends(get_db)
):
    coin = db.query(Coin).filter(Coin.id == coin_id).first()
    if coin is None:
        raise HTTPException(status_code=404, detail="Coin not found")

    posts = (
        db.query(SocialPost)
        .filter(SocialPost.coin_id == coin_id)
        .order_by(SocialPost.engagement_score.desc())
        .limit(limit)
        .all()
    )
    return posts


@router.get("/{coin_id}/community", response_model=CommunityOut)
def get_coin_community(coin_id: uuid.UUID, db: Session = Depends(get_db)):
    coin = db.query(Coin).filter(Coin.id == coin_id).first()
    if coin is None:
        raise HTTPException(status_code=404, detail="Coin not found")

    community = db.query(Community).filter(Community.coin_id == coin_id).first()
    if community is None:
        raise HTTPException(status_code=404, detail="No community analysis available for this coin yet")
    return community


def _attach_score(coin: Coin) -> CoinWithScoreOut:
    out = CoinWithScoreOut.model_validate(coin)
    if coin.scores:
        out.score = coin.scores[0] if isinstance(coin.scores, list) else coin.scores
    return out
