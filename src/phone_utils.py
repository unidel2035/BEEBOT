"""Валидация и нормализация российских телефонных номеров.

Поддерживаемые форматы ввода:
  +7 (999) 123-45-67
  8 999 123 45 67
  89991234567
  +79991234567
  9991234567

Нормализация: все форматы → +7XXXXXXXXXX (11 цифр).
"""

from __future__ import annotations

import re


def normalize_phone(raw: str) -> str | None:
    """Нормализовать телефон в формат +7XXXXXXXXXX.

    Returns:
        Нормализованный номер или None если невалидный.
    """
    digits = re.sub(r"\D", "", raw)

    # 11 цифр: 8XXXXXXXXXX или 7XXXXXXXXXX
    if len(digits) == 11:
        if digits[0] == "8":
            return "+7" + digits[1:]
        if digits[0] == "7":
            return "+7" + digits[1:]

    # 10 цифр: 9XXXXXXXXX (без кода страны)
    if len(digits) == 10 and digits[0] == "9":
        return "+7" + digits

    return None


def format_phone(normalized: str) -> str:
    """Форматировать для отображения: +7 (999) 123-45-67."""
    if not normalized or len(normalized) != 12:
        return normalized or ""
    d = normalized[2:]  # 10 цифр после +7
    return f"+7 ({d[:3]}) {d[3:6]}-{d[6:8]}-{d[8:10]}"


def validate_phone(raw: str) -> tuple[str | None, str]:
    """Валидировать и нормализовать телефон.

    Returns:
        (normalized, error) — если normalized is None, error содержит сообщение.
    """
    normalized = normalize_phone(raw)
    if normalized is None:
        return None, (
            "Введите российский номер телефона в любом формате:\n"
            "+7 999 123-45-67, 89991234567 или 9991234567"
        )
    return normalized, ""
