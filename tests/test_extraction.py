from decimal import Decimal

from invoice_ai.extraction import parse_money


def test_parse_money_with_none():
    assert parse_money(None) is None


def test_parse_money_with_indian_format():
    assert parse_money("2,596.00") == Decimal("2596.00")


def test_parse_money_with_currency():
    assert parse_money("INR 2,200.00") == Decimal("2200.00")


def test_parse_money_with_empty_string():
    assert parse_money("") is None