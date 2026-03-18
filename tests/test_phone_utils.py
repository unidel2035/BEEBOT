"""Тесты валидации и нормализации российских номеров телефонов."""

from __future__ import annotations

import pytest

from src.phone_utils import normalize_phone, format_phone, validate_phone


class TestNormalizePhone:
    """normalize_phone: различные форматы → +7XXXXXXXXXX."""

    @pytest.mark.parametrize("raw, expected", [
        # 11 цифр с 8
        ("89991234567", "+79991234567"),
        ("8 999 123 45 67", "+79991234567"),
        ("8-999-123-45-67", "+79991234567"),
        ("8(999)123-45-67", "+79991234567"),
        # 11 цифр с 7
        ("79991234567", "+79991234567"),
        ("7 999 123 45 67", "+79991234567"),
        # +7 формат
        ("+79991234567", "+79991234567"),
        ("+7 (999) 123-45-67", "+79991234567"),
        ("+7 999 123 45 67", "+79991234567"),
        # 10 цифр (без кода страны)
        ("9991234567", "+79991234567"),
        ("999 123 45 67", "+79991234567"),
    ])
    def test_valid_formats(self, raw: str, expected: str) -> None:
        assert normalize_phone(raw) == expected

    @pytest.mark.parametrize("raw", [
        "",
        "123",
        "12345678",       # 8 цифр — не подходит
        "29991234567",    # 11 цифр но не 8 и не 7
        "+19991234567",   # не Россия
        "abc",
        "123456789012",   # 12 цифр
    ])
    def test_invalid_formats(self, raw: str) -> None:
        assert normalize_phone(raw) is None


class TestFormatPhone:
    """format_phone: +7XXXXXXXXXX → +7 (999) 123-45-67."""

    def test_standard(self) -> None:
        assert format_phone("+79991234567") == "+7 (999) 123-45-67"

    def test_short_passthrough(self) -> None:
        assert format_phone("+7999") == "+7999"

    def test_none(self) -> None:
        assert format_phone(None) == ""

    def test_empty(self) -> None:
        assert format_phone("") == ""


class TestValidatePhone:
    """validate_phone: возвращает (normalized, error)."""

    def test_valid(self) -> None:
        normalized, error = validate_phone("+7 999 123-45-67")
        assert normalized == "+79991234567"
        assert error == ""

    def test_invalid(self) -> None:
        normalized, error = validate_phone("123")
        assert normalized is None
        assert "Введите российский номер" in error
