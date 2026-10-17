from unittest.mock import MagicMock

from app.services.youtube_scanner_service import YouTubeScannerService


class FakeCoin:
    def __init__(self, symbol, name):
        self.symbol = symbol
        self.name = name


def make_service():
    return YouTubeScannerService(db=MagicMock())


def test_has_searchable_text_rejects_hangul_filler():
    service = make_service()
    assert service._has_searchable_text("ㅤ") is False


def test_has_searchable_text_accepts_normal_symbol():
    service = make_service()
    assert service._has_searchable_text("Robinhood") is True


def test_has_searchable_text_accepts_mixed_script_with_real_letters():
    service = make_service()
    assert service._has_searchable_text("mɔ") is True


def test_has_searchable_text_rejects_whitespace_only():
    service = make_service()
    assert service._has_searchable_text("   ") is False


def test_has_searchable_text_rejects_empty_string():
    service = make_service()
    assert service._has_searchable_text("") is False


def test_has_searchable_text_rejects_none():
    service = make_service()
    assert service._has_searchable_text(None) is False


def test_has_searchable_text_rejects_zero_width_space():
    service = make_service()
    assert service._has_searchable_text("\u200B") is False


def test_has_searchable_text_rejects_multiple_invisible_chars_combined():
    service = make_service()
    assert service._has_searchable_text("\u3164\u200B\uFEFF") is False


def test_build_search_query_uses_symbol_when_usable():
    service = make_service()
    coin = FakeCoin(symbol="Robinhood", name="Robinhood Coin")
    assert service._build_search_query(coin) == '"Robinhood" meme coin'


def test_build_search_query_falls_back_to_name_when_symbol_blank():
    service = make_service()
    coin = FakeCoin(symbol="ㅤ", name="Hello Kitty")
    assert service._build_search_query(coin) == '"Hello Kitty" meme coin'


def test_build_search_query_returns_none_when_neither_usable():
    service = make_service()
    coin = FakeCoin(symbol="ㅤ", name="ㅤ")
    assert service._build_search_query(coin) is None


def test_build_search_query_returns_none_when_both_blank_and_none():
    service = make_service()
    coin = FakeCoin(symbol="", name=None)
    assert service._build_search_query(coin) is None
