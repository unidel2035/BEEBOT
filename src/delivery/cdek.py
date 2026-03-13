"""Провайдер доставки СДЭК.

Интеграция с API СДЭК для расчёта тарифов, создания отправлений
и отслеживания посылок.

Статус: планируется (заглушка для будущей реализации).
"""

from src.delivery.base import BaseDeliveryProvider, ShippingRate


class CDEKProvider(BaseDeliveryProvider):
    """Провайдер доставки через СДЭК."""

    async def calculate_rate(
        self,
        origin_city: str,
        destination_city: str,
        weight_kg: float,
    ) -> ShippingRate:
        raise NotImplementedError("CDEKProvider не реализован")

    async def create_shipment(self, order: dict) -> str:
        raise NotImplementedError("CDEKProvider не реализован")

    async def track_shipment(self, tracking_number: str) -> dict:
        raise NotImplementedError("CDEKProvider не реализован")
