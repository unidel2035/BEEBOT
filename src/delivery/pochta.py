"""Провайдер доставки Почта России.

Расчёт тарифов через публичный API tariff.pochta.ru (без авторизации).
При ошибке — фиксированный тариф (fallback).

Публичный калькулятор:
  GET https://tariff.pochta.ru/v2/calculate/tariff?json
    &object=47030  (Посылка онлайн — до 20 кг)
    &from=101000   (почтовый индекс отправителя)
    &to=630000     (почтовый индекс получателя)
    &weight=1000   (вес в граммах)
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from src.delivery.base import BaseDeliveryProvider, ShippingRate

logger = logging.getLogger(__name__)

# Фиксированный тариф (fallback)
_FALLBACK_BASE = 250.0
_FALLBACK_PER_KG = 30.0
_FALLBACK_DAYS_MIN = 7
_FALLBACK_DAYS_MAX = 14

# Почта России: публичный API тарифов
_TARIFF_URL = "https://tariff.pochta.ru/v2/calculate/tariff"
_SUGGEST_URL = "https://tariff.pochta.ru/v2/suggest/postoffice"

# Тип отправления: 47030 = Посылка онлайн (стандарт), 27030 = Посылка нестандартная
_MAIL_TYPE = 47030

# Индекс Москвы (отправитель по умолчанию)
_MOSCOW_INDEX = "101000"

# Кэш: название города → почтовый индекс
_index_cache: dict[str, str] = {
    "москва": "101000",
    "санкт-петербург": "190000",
    "новосибирск": "630000",
    "екатеринбург": "620000",
    "казань": "420000",
    "нижний новгород": "603000",
    "челябинск": "454000",
    "самара": "443000",
    "омск": "644000",
    "ростов-на-дону": "344000",
    "уфа": "450000",
    "красноярск": "660000",
    "воронеж": "394000",
    "пермь": "614000",
    "волгоград": "400000",
    "краснодар": "350000",
    "саратов": "410000",
    "тюмень": "625000",
    "тольятти": "445000",
    "ижевск": "426000",
    "барнаул": "656000",
    "иркутск": "664000",
    "ульяновск": "432000",
    "хабаровск": "680000",
    "владивосток": "690000",
    "ярославль": "150000",
    "махачкала": "367000",
    "томск": "634000",
    "оренбург": "460000",
    "кемерово": "650000",
    "рязань": "390000",
    "набережные челны": "423800",
    "пенза": "440000",
    "астрахань": "414000",
    "липецк": "398000",
    "тула": "300000",
    "киров": "610000",
    "чебоксары": "428000",
    "калининград": "236000",
    "брянск": "241000",
    "курск": "305000",
    "иваново": "153000",
    "магнитогорск": "455000",
    "улан-удэ": "670000",
    "тверь": "170000",
    "ставрополь": "355000",
    "белгород": "308000",
    "сочи": "354000",
}


def _extract_city(address: str) -> str:
    """Извлечь название города из адреса."""
    if not address:
        return ""
    part = address.split(",")[0].strip()
    for prefix in ("г.", "г ", "город "):
        if part.lower().startswith(prefix):
            part = part[len(prefix):].strip()
    return part


async def _find_postal_index(
    client: httpx.AsyncClient, city_name: str
) -> Optional[str]:
    """Найти почтовый индекс города."""
    key = city_name.strip().lower()
    if key in _index_cache:
        return _index_cache[key]

    # Попробовать API подсказок Почты России
    try:
        resp = await client.get(
            _SUGGEST_URL,
            params={"term": city_name, "size": 1},
        )
        if resp.status_code == 200:
            data = resp.json()
            suggestions = data if isinstance(data, list) else data.get("suggestions", [])
            if suggestions:
                index = str(suggestions[0].get("index", ""))
                if index and len(index) == 6:
                    _index_cache[key] = index
                    return index
    except Exception:
        pass

    return None


class PochtaProvider(BaseDeliveryProvider):
    """Провайдер доставки через Почту России.

    Использует публичный тарифный API tariff.pochta.ru.
    При ошибке возвращает фиксированный тариф.
    """

    async def calculate_rate(
        self,
        origin_city: str,
        destination_city: str,
        weight_kg: float,
    ) -> ShippingRate:
        rate = await self._try_api(origin_city, destination_city, weight_kg)
        if rate:
            return rate
        return self._fallback(weight_kg)

    async def _try_api(
        self,
        origin_city: str,
        destination_city: str,
        weight_kg: float,
    ) -> Optional[ShippingRate]:
        """Расчёт через публичный API tariff.pochta.ru."""
        dest_name = _extract_city(destination_city)
        if not dest_name:
            return None

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Индекс отправителя
                origin_name = _extract_city(origin_city) or "Москва"
                from_index = await _find_postal_index(client, origin_name)
                if not from_index:
                    from_index = _MOSCOW_INDEX

                # Индекс получателя
                to_index = await _find_postal_index(client, dest_name)
                if not to_index:
                    logger.info("Почта: индекс '%s' не найден", dest_name)
                    return None

                weight_g = max(int(weight_kg * 1000), 100)

                resp = await client.get(
                    _TARIFF_URL,
                    params={
                        "json": "",
                        "object": _MAIL_TYPE,
                        "from": from_index,
                        "to": to_index,
                        "weight": weight_g,
                    },
                )
                if resp.status_code != 200:
                    logger.warning("Почта tariff %d: %s", resp.status_code, resp.text[:200])
                    return None

                data = resp.json()

                # Цена в копейках → рубли
                pay = data.get("pay")
                if pay is None:
                    # Альтернативный формат ответа
                    pay = data.get("paynds") or data.get("ground", {}).get("pay")
                if pay is None:
                    return None

                price_rub = round(int(pay) / 100, 0)

                # Сроки доставки
                delivery = data.get("delivery", {})
                days_min = delivery.get("min", _FALLBACK_DAYS_MIN)
                days_max = delivery.get("max", _FALLBACK_DAYS_MAX)

                return ShippingRate(
                    provider="Почта России",
                    price=price_rub,
                    currency="RUB",
                    days_min=days_min,
                    days_max=days_max,
                )

        except Exception as e:
            logger.warning("Почта API ошибка: %s", e)
            return None

    @staticmethod
    def _fallback(weight_kg: float) -> ShippingRate:
        price = round(_FALLBACK_BASE + _FALLBACK_PER_KG * max(weight_kg, 0.1), 0)
        return ShippingRate(
            provider="Почта России",
            price=price,
            currency="RUB",
            days_min=_FALLBACK_DAYS_MIN,
            days_max=_FALLBACK_DAYS_MAX,
        )

    async def create_shipment(self, order: dict) -> str:
        raise NotImplementedError("PochtaProvider.create_shipment не реализован")

    async def track_shipment(self, tracking_number: str) -> dict:
        raise NotImplementedError("PochtaProvider.track_shipment не реализован")
