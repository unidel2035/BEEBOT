"""Провайдер доставки Почта России.

Интеграция с API Почты России для расчёта тарифов, создания отправлений
и отслеживания посылок.

Статус: планируется (заглушка для будущей реализации).
"""

from src.delivery.base import BaseDeliveryProvider, ShippingRate


class PochtaProvider(BaseDeliveryProvider):
    """Провайдер доставки через Почту России."""

    async def calculate_rate(
        self,
        origin_city: str,
        destination_city: str,
        weight_kg: float,
    ) -> ShippingRate:
        raise NotImplementedError("PochtaProvider не реализован")

    async def create_shipment(self, order: dict) -> str:
        raise NotImplementedError("PochtaProvider не реализован")

    async def track_shipment(self, tracking_number: str) -> dict:
        raise NotImplementedError("PochtaProvider не реализован")
