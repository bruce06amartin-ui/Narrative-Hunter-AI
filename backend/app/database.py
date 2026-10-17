import logging

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config import settings

logger = logging.getLogger(__name__)

engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)

Base = declarative_base()


def get_db():
    """FastAPI dependency that yields a DB session and closes it afterward."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables. For an MVP this replaces Alembic migrations —
    swap in Alembic once the schema stabilizes (see README)."""
    # Import models so they register with Base.metadata before create_all
    from app.models import coin, price_history, score, risk_flag, alert, wallet, wallet_transaction, social_post, narrative, community, paper_trade  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _add_missing_columns()


def _add_missing_columns():
    """Safety net for a real recurring problem: create_all() only creates
    tables that don't exist yet - it never adds new COLUMNS to a table that
    already exists. Without Alembic, adding a nullable field to a model
    (which has happened multiple times as this project grew - e.g. adding
    lunarcrush_galaxy_score to Community, or social_enrichment_checked_at to
    Coin) would otherwise silently crash any already-running deployment the
    next time that field gets touched, with a cryptic
    "column ... does not exist" error that has nothing to do with the
    actual feature being added.

    This walks every mapped table, compares its expected columns against
    what's actually in the live database, and ADD COLUMNs anything missing.

    This is explicitly NOT a substitute for Alembic: it only handles the
    "a new nullable column showed up" case - it cannot rename columns,
    change types, add NOT NULL constraints safely, or remove columns. If
    the schema ever needs one of those, this project needs real migrations
    at that point, not more logic bolted onto this function.
    """
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not inspector.has_table(table.name):
                continue  # brand new table - create_all() already handled it

            existing_columns = {col["name"] for col in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing_columns:
                    continue

                col_type = column.type.compile(dialect=engine.dialect)
                nullable_clause = "" if column.nullable else " NOT NULL"

                # If this column is NOT NULL and the table already has rows,
                # Postgres requires a DEFAULT to backfill existing rows -
                # otherwise the ALTER TABLE itself fails. Translate the
                # model's Python-side default (e.g. default="posts") into a
                # real SQL DEFAULT clause when one exists.
                default_clause = ""
                if not column.nullable and column.default is not None and getattr(column.default, "is_scalar", False):
                    default_value = column.default.arg
                    if isinstance(default_value, str):
                        default_clause = f" DEFAULT '{default_value}'"
                    elif isinstance(default_value, bool):
                        default_clause = f" DEFAULT {str(default_value).upper()}"
                    elif isinstance(default_value, (int, float)):
                        default_clause = f" DEFAULT {default_value}"
                    # else: no safe generic way to render this default - fall
                    # through without one, which will surface as a clear
                    # ALTER TABLE error rather than silently doing the wrong thing

                ddl = f'ALTER TABLE {table.name} ADD COLUMN "{column.name}" {col_type}{default_clause}{nullable_clause}'
                logger.info("Schema drift detected - adding missing column: %s", ddl)
                try:
                    conn.execute(text(ddl))
                except Exception:  # noqa: BLE001 - don't let one bad column block the whole startup
                    logger.exception("Failed to add missing column %s.%s", table.name, column.name)
