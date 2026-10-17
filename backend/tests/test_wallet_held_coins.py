import uuid
from unittest.mock import MagicMock

from app.api.routes_wallets import _attach_held_coins

COIN_X = uuid.uuid4()
COIN_Y = uuid.uuid4()
COIN_Z = uuid.uuid4()


class FakeTx:
    def __init__(self, wallet_id, coin_id, direction):
        self.wallet_id = wallet_id
        self.coin_id = coin_id
        self.direction = direction


class FakeWallet:
    def __init__(self, id):
        self.id = id
        self.held_coins = None


def make_db_with_rows(rows):
    """rows: list of (FakeTx, symbol) tuples, already in the exact order
    the real query would return them (wallet_id, coin_id, then
    block_timestamp DESC within each group) - mirrors what the real
    ORDER BY produces, since we're mocking .all() directly rather than
    a real database."""
    db = MagicMock()
    db.query.return_value.join.return_value.filter.return_value.order_by.return_value.all.return_value = rows
    return db


def test_attach_held_coins_uses_most_recent_transaction_direction():
    """wallet A bought coin X (older 'in'), then sold it (newer 'out') -
    should show still_holding=False, using the NEWER transaction, not the
    older one that happens to say 'in'."""
    wallet_a = FakeWallet(id="wallet-a")
    rows = [
        (FakeTx("wallet-a", COIN_X, "out"), "COINX"),  # newer - listed first (DESC order)
        (FakeTx("wallet-a", COIN_X, "in"), "COINX"),   # older
    ]
    db = make_db_with_rows(rows)

    result = _attach_held_coins(db, [wallet_a])

    assert len(result[0].held_coins) == 1
    assert result[0].held_coins[0].still_holding is False
    assert result[0].held_coins[0].symbol == "COINX"


def test_attach_held_coins_still_holding_true_for_unsold_position():
    wallet_a = FakeWallet(id="wallet-a")
    rows = [(FakeTx("wallet-a", COIN_Y, "in"), "COINY")]
    db = make_db_with_rows(rows)

    result = _attach_held_coins(db, [wallet_a])

    assert result[0].held_coins[0].still_holding is True


def test_attach_held_coins_separates_multiple_wallets_correctly():
    wallet_a = FakeWallet(id="wallet-a")
    wallet_b = FakeWallet(id="wallet-b")
    rows = [
        (FakeTx("wallet-a", COIN_X, "in"), "COINX"),
        (FakeTx("wallet-b", COIN_Z, "out"), "COINZ"),
    ]
    db = make_db_with_rows(rows)

    result = _attach_held_coins(db, [wallet_a, wallet_b])

    a = next(w for w in result if w.id == "wallet-a")
    b = next(w for w in result if w.id == "wallet-b")
    assert len(a.held_coins) == 1 and a.held_coins[0].symbol == "COINX"
    assert len(b.held_coins) == 1 and b.held_coins[0].symbol == "COINZ" and b.held_coins[0].still_holding is False


def test_attach_held_coins_wallet_with_no_transactions_gets_empty_list():
    wallet_a = FakeWallet(id="wallet-a")
    db = make_db_with_rows([])

    result = _attach_held_coins(db, [wallet_a])

    assert result[0].held_coins == []


def test_attach_held_coins_empty_wallet_list_returns_empty_no_query():
    db = MagicMock()
    result = _attach_held_coins(db, [])
    assert result == []
    db.query.assert_not_called()


def test_attach_held_coins_multiple_coins_same_wallet():
    """A wallet holding two DIFFERENT coins should show both, not just
    one overwriting the other."""
    wallet_a = FakeWallet(id="wallet-a")
    rows = [
        (FakeTx("wallet-a", COIN_X, "in"), "COINX"),
        (FakeTx("wallet-a", COIN_Y, "out"), "COINY"),
    ]
    db = make_db_with_rows(rows)

    result = _attach_held_coins(db, [wallet_a])

    symbols = {hc.symbol for hc in result[0].held_coins}
    assert symbols == {"COINX", "COINY"}

