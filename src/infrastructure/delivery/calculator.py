"""Фасад для расчёта стоимости доставки.

Объединяет провайдеров СДЭК и Почта России под единым интерфейсом.
Позволяет сравнивать тарифы и создавать отправления через нужного провайдера.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.delivery.base import BaseDeliveryProvider, ShippingRate
from src.delivery.cdek import CDEKProvider
from src.delivery.pochta import PochtaProvider


@dataclass
class DeliveryQuote:
    """Котировка доставки от конкретного провайдера."""

    provider: str
    price: float
    currency: str
    days_min: int
    days_max: int


@dataclass
class TrackingStatus:
    """Статус отслеживания отправления."""

    tracking_number: str
    provider: str
    status: str
    description: str


_GRAMS_PER_KG = 1000.0
_PROVIDER_CDEK = "СДЭК"
_PROVIDER_POCHTA = "Почта России"


class DeliveryCalculator:
    """Фасад для работы с провайдерами доставки.

    Использование::

        calc = DeliveryCalculator()
        quote = await calc.calculate("Москва", 500, "СДЭК")
        tracking_num = await calc.create_shipment(order)
        status = await calc.track(tracking_num)
    """

    def __init__(
        self,
        cdek: Optional[BaseDeliveryProvider] = None,
        pochta: Optional[BaseDeliveryProvider] = None,
    ) -> None:
        self._providers: dict[str, BaseDeliveryProvider] = {
            _PROVIDER_CDEK: cdek or CDEKProvider(),
            _PROVIDER_POCHTA: pochta or PochtaProvider(),
        }

    # ------------------------------------------------------------------
    # Публичный API
    # ------------------------------------------------------------------

    async def calculate(
        self,
        city: str,
        weight_grams: int,
        method: str,
        sender_city: str = "Москва",
    ) -> DeliveryQuote:
        """Рассчитать стоимость доставки.

        Args:
            city: Город получателя.
            weight_grams: Вес отправления в граммах.
            method: Название провайдера («СДЭК» или «Почта России»).
            sender_city: Город отправителя (по умолчанию «Москва»).

        Returns:
            :class:`DeliveryQuote` с ценой и сроком.

        Raises:
            ValueError: Если провайдер ``method`` не поддерживается.
        """
        provider = self._get_provider(method)
        weight_kg = weight_grams / _GRAMS_PER_KG
        rate: ShippingRate = await provider.calculate_rate(
            origin_city=sender_city,
            destination_city=city,
            weight_kg=weight_kg,
        )
        return DeliveryQuote(
            provider=rate.provider,
            price=rate.price,
            currency=rate.currency,
            days_min=rate.days_min,
            days_max=rate.days_max,
        )

    async def create_shipment(self, order: dict) -> str:
        """Создать отправление у выбранного провайдера.

        Args:
            order: Словарь с данными заказа. Ожидаемые ключи:
                - ``delivery_method`` — название провайдера (обязательно),
                - остальные поля передаются провайдеру как есть.

        Returns:
            Трек-номер отправления.

        Raises:
            ValueError: Если ``delivery_method`` не указан или не поддерживается.
        """
        method = order.get("delivery_method")
        if not method:
            raise ValueError("Поле 'delivery_method' обязательно для создания отправления")
        provider = self._get_provider(method)
        return await provider.create_shipment(order)

    async def track(self, tracking_number: str, provider_name: str = _PROVIDER_CDEK) -> TrackingStatus:
        """Получить статус отправления по трек-номеру.

        Args:
            tracking_number: Трек-номер отправления.
            provider_name: Название провайдера. По умолчанию «СДЭК».

        Returns:
            :class:`TrackingStatus` с текущим статусом.

        Raises:
            ValueError: Если провайдер не поддерживается.
        """
        provider = self._get_provider(provider_name)
        raw: dict = await provider.track_shipment(tracking_number)
        return TrackingStatus(
            tracking_number=tracking_number,
            provider=provider_name,
            status=raw.get("status", "Неизвестно"),
            description=raw.get("description", ""),
        )

    def available_providers(self) -> list[str]:
        """Вернуть список поддерживаемых провайдеров."""
        return list(self._providers.keys())

    # ------------------------------------------------------------------
    # Вспомогательные методы
    # ------------------------------------------------------------------

    def _get_provider(self, method: str) -> BaseDeliveryProvider:
        provider = self._providers.get(method)
        if provider is None:
            supported = ", ".join(self._providers)
            raise ValueError(
                f"Провайдер '{method}' не поддерживается. Доступные: {supported}"
            )
        return provider
