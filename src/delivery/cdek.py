"""Провайдер доставки СДЭК.

Интеграция с API СДЭК v2 для расчёта тарифов.
При отсутствии ключей или ошибке API — фиксированный тариф (fallback).

Требуемые переменные окружения:
  CDEK_CLIENT_ID     — идентификатор клиента СДЭК
  CDEK_CLIENT_SECRET — секретный ключ
"""

from __future__ import annotations

import logging
import time
from typing import Optional

import httpx

from src import config
from src.delivery.base import BaseDeliveryProvider, ShippingRate

logger = logging.getLogger(__name__)

# Фиксированный тариф (fallback)
_FALLBACK_BASE = 350.0
_FALLBACK_PER_KG = 50.0
_FALLBACK_DAYS_MIN = 3
_FALLBACK_DAYS_MAX = 7

# СДЭК API v2
_API_BASE = "https://api.cdek.ru/v2"
_TOKEN_URL = f"{_API_BASE}/oauth/token"
_CITIES_URL = f"{_API_BASE}/location/cities"
_CALC_URL = f"{_API_BASE}/calculator/tarifflist"
_ORDERS_URL = f"{_API_BASE}/orders"

# Код Москвы в СДЭК
_MOSCOW_CODE = 44

# Кэш OAuth-токена
_token_cache: dict = {"token": None, "expires": 0}

# Кэш кодов городов: {"москва": 44, ...}
_city_cache: dict[str, int] = {"москва": _MOSCOW_CODE}


async def _get_token(client: httpx.AsyncClient) -> Optional[str]:
    """Получить OAuth2 токен СДЭК (с кэшированием)."""
    cid = getattr(config, "CDEK_CLIENT_ID", None)
    secret = getattr(config, "CDEK_CLIENT_SECRET", None)
    if not cid or not secret:
        return None

    now = time.time()
    if _token_cache["token"] and _token_cache["expires"] > now + 60:
        return _token_cache["token"]

    resp = await client.post(
        _TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": cid,
            "client_secret": secret,
        },
    )
    if resp.status_code != 200:
        logger.warning("СДЭК OAuth ошибка %d: %s", resp.status_code, resp.text[:200])
        return None

    data = resp.json()
    _token_cache["token"] = data["access_token"]
    _token_cache["expires"] = now + data.get("expires_in", 3600)
    return _token_cache["token"]


async def _find_city_code(
    client: httpx.AsyncClient, token: str, city_name: str
) -> Optional[int]:
    """Найти код города СДЭК по названию."""
    key = city_name.strip().lower()
    if key in _city_cache:
        return _city_cache[key]

    resp = await client.get(
        _CITIES_URL,
        params={"city": city_name, "size": 1, "country_codes": "RU"},
        headers={"Authorization": f"Bearer {token}"},
    )
    if resp.status_code != 200:
        return None

    cities = resp.json()
    if not cities:
        return None

    code = cities[0].get("code")
    if code:
        _city_cache[key] = code
    return code


def _extract_city(address: str) -> str:
    """Извлечь название города из адреса.

    Простая эвристика: берём первый элемент до запятой,
    или первое слово, если запятых нет.
    """
    if not address:
        return ""
    # «г. Новосибирск, ул. Ленина, 1» → «Новосибирск»
    part = address.split(",")[0].strip()
    # Убрать «г.», «город»
    for prefix in ("г.", "г ", "город "):
        if part.lower().startswith(prefix):
            part = part[len(prefix):].strip()
    return part


class CDEKProvider(BaseDeliveryProvider):
    """Провайдер доставки через СДЭК.

    Пытается рассчитать через реальный API СДЭК v2.
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
        """Попытка расчёта через реальный API СДЭК."""
        dest_name = _extract_city(destination_city)
        if not dest_name:
            return None

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                token = await _get_token(client)
                if not token:
                    return None

                # Код города отправления
                origin_name = _extract_city(origin_city) or "Москва"
                from_code = await _find_city_code(client, token, origin_name)
                if not from_code:
                    from_code = _MOSCOW_CODE

                # Код города получателя
                to_code = await _find_city_code(client, token, dest_name)
                if not to_code:
                    logger.info("СДЭК: город '%s' не найден", dest_name)
                    return None

                # Расчёт тарифов
                weight_g = max(int(weight_kg * 1000), 100)
                resp = await client.post(
                    _CALC_URL,
                    json={
                        "from_location": {"code": from_code},
                        "to_location": {"code": to_code},
                        "packages": [{"weight": weight_g}],
                    },
                    headers={"Authorization": f"Bearer {token}"},
                )
                if resp.status_code != 200:
                    logger.warning("СДЭК calculator %d: %s", resp.status_code, resp.text[:200])
                    return None

                data = resp.json()
                tariffs = data.get("tariff_codes", [])
                if not tariffs:
                    return None

                # Выбираем самый дешёвый тариф «дверь-дверь» или «склад-дверь»
                best = min(tariffs, key=lambda t: t.get("delivery_sum", 99999))

                return ShippingRate(
                    provider="СДЭК",
                    price=round(best["delivery_sum"], 0),
                    currency="RUB",
                    days_min=best.get("period_min", _FALLBACK_DAYS_MIN),
                    days_max=best.get("period_max", _FALLBACK_DAYS_MAX),
                )

        except Exception as e:
            logger.warning("СДЭК API ошибка: %s", e)
            return None

    @staticmethod
    def _fallback(weight_kg: float) -> ShippingRate:
        price = round(_FALLBACK_BASE + _FALLBACK_PER_KG * max(weight_kg, 0.1), 0)
        return ShippingRate(
            provider="СДЭК",
            price=price,
            currency="RUB",
            days_min=_FALLBACK_DAYS_MIN,
            days_max=_FALLBACK_DAYS_MAX,
        )

    async def create_shipment(self, order: dict) -> str:
        raise NotImplementedError("CDEKProvider.create_shipment не реализован")

    async def track_shipment(self, tracking_number: str) -> dict:
        """Получить статус отправления СДЭК по трек-номеру (cdek_number или im_number)."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                token = await _get_token(client)
                if not token:
                    return {"status": "Неизвестно", "description": "Нет токена СДЭК"}

                resp = await client.get(
                    _ORDERS_URL,
                    params={"cdek_number": tracking_number},
                    headers={"Authorization": f"Bearer {token}"},
                )
                if resp.status_code != 200:
                    # Попробовать по im_number
                    resp = await client.get(
                        _ORDERS_URL,
                        params={"im_number": tracking_number},
                        headers={"Authorization": f"Bearer {token}"},
                    )
                if resp.status_code != 200:
                    return {"status": "Неизвестно", "description": f"СДЭК HTTP {resp.status_code}"}

                data = resp.json()
                entity = data.get("entity", {})
                statuses = entity.get("statuses", [])
                if not statuses:
                    return {"status": "Неизвестно", "description": "Нет данных о статусе"}

                latest = statuses[0]  # самый свежий — первый
                return {
                    "status": latest.get("name", "Неизвестно"),
                    "description": latest.get("city", ""),
                    "code": latest.get("code", ""),
                    "date": latest.get("date_time", ""),
                }

        except Exception as e:
            logger.warning("СДЭК tracking ошибка: %s", e)
            return {"status": "Неизвестно", "description": str(e)}
