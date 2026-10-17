import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.coin import Coin
from app.models.wallet import Wallet
from app.models.wallet_transaction import WalletTransaction
from app.schemas.wallet import WalletOut, HeldCoinOut

router = APIRouter(prefix="/api/wallets", tags=["wallets"])


def _attach_held_coins(db: Session, wallets: list[Wallet]) -> list[Wallet]:
    """Computes held_coins for a batch of wallets in ONE query (not one
    per wallet - avoids an N+1 pattern for what's otherwise a simple list
    endpoint). still_holding is a proxy: true if the wallet's most recent
    transaction for that coin was 'in', not a precise balance
    calculation (see WalletTransaction model for why exact balances
    aren't reliable from transfer data alone)."""
    if not wallets:
        return wallets
    wallet_ids = [w.id for w in wallets]

    rows = (
        db.query(WalletTransaction, Coin.symbol)
        .join(Coin, Coin.id == WalletTransaction.coin_id)
        .filter(WalletTransaction.wallet_id.in_(wallet_ids))
        .order_by(WalletTransaction.wallet_id, WalletTransaction.coin_id, WalletTransaction.block_timestamp.desc())
        .all()
    )

    # rows are ordered latest-first within each (wallet_id, coin_id) group,
    # so the first row we see for a given pair is the most recent one.
    latest_per_wallet_coin: dict[tuple, tuple] = {}
    for tx, symbol in rows:
        key = (tx.wallet_id, tx.coin_id)
        if key not in latest_per_wallet_coin:
            latest_per_wallet_coin[key] = (symbol, tx.direction)

    held_by_wallet: dict = {}
    for (wallet_id, coin_id), (symbol, direction) in latest_per_wallet_coin.items():
        held_by_wallet.setdefault(wallet_id, []).append(
            HeldCoinOut(coin_id=coin_id, symbol=symbol, still_holding=(direction == "in"))
        )

    for w in wallets:
        w.held_coins = held_by_wallet.get(w.id, [])
    return wallets


@router.get("", response_model=list[WalletOut])
def list_wallets(
    chain: str | None = None,
    min_positions: int = Query(1, ge=0),
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: Session = Depends(get_db),
):
    query = db.query(Wallet).filter(Wallet.total_positions >= min_positions)
    if chain:
        query = query.filter(Wallet.chain == chain)

    wallets = (
        query.order_by(Wallet.reputation_score.desc().nullslast())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return _attach_held_coins(db, wallets)


@router.get("/{wallet_id}", response_model=WalletOut)
def get_wallet(wallet_id: uuid.UUID, db: Session = Depends(get_db)):
    wallet = db.query(Wallet).filter(Wallet.id == wallet_id).first()
    if wallet is None:
        raise HTTPException(status_code=404, detail="Wallet not found")
    return _attach_held_coins(db, [wallet])[0]
