import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models.alert import Alert
from app.schemas.coin import AlertOut

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertOut])
def list_alerts(
    severity: str | None = Query(None, pattern="^(info|warning|critical)$"),
    coin_id: uuid.UUID | None = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: Session = Depends(get_db),
):
    query = db.query(Alert).options(joinedload(Alert.coin))

    if severity:
        query = query.filter(Alert.severity == severity)
    if coin_id:
        query = query.filter(Alert.coin_id == coin_id)

    alerts = query.order_by(Alert.created_at.desc()).offset(offset).limit(limit).all()
    return [_attach_coin_info(a) for a in alerts]


def _attach_coin_info(alert: Alert) -> AlertOut:
    out = AlertOut.model_validate(alert)
    if alert.coin:
        out.coin_symbol = alert.coin.symbol
        out.coin_chain = alert.coin.chain
    return out
