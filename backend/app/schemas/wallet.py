import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class HeldCoinOut(BaseModel):
    """One coin a wallet has transacted with. still_holding is a proxy
    based on whether the wallet's MOST RECENT transaction for this coin
    was an 'in' (likely still holding) or 'out' (likely sold, or moved
    to another wallet it controls - transfer data alone can't fully
    distinguish those, see WalletTransaction model)."""

    coin_id: uuid.UUID
    symbol: str | None
    still_holding: bool


class WalletOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    chain: str
    address: str
    total_positions: int
    positions_with_known_roi: int
    wins: int
    win_rate: float | None
    avg_roi_pct: float | None
    avg_hold_time_seconds: float | None
    early_entry_count: int
    early_entry_frequency: float | None
    reputation_score: float | None
    held_coins: list[HeldCoinOut] = []
    first_seen_at: datetime
    updated_at: datetime
