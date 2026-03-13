"""Базовый интерфейс для служб доставки.

Определяет контракт, который должны реализовывать конкретные провайдеры
(СДЭК, Почта России и др.).

Статус: планируется (заглушка для будущей реализации).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ShippingRate:
    """Тариф доставки."""
    provider: str
    price: float
    currency: str = "RUB"
    days_min: int = 0
    days_max: int = 0


class BaseDeliveryProvider(ABC):
    """Абстрактный провайдер доставки."""

    @abstractmethod
    async def calculate_rate(
        self,
        origin_city: str,
        destination_city: str,
        weight_kg: float,
    ) -> ShippingRate:
        """Рассчитать стоимость доставки."""

    @abstractmethod
    async def create_shipment(self, order: dict) -> str:
        """Создать отправление. Возвращает трек-номер."""

    @abstractmethod
    async def track_shipment(self, tracking_number: str) -> dict:
        """Получить статус отправления по трек-номеру."""
