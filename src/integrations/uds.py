"""Интеграция с UDS (Unified Discount System).

Получение заказов, клиентов и истории покупок из системы UDS
для «Усадьба Дмитровых».

Статус: планируется (заглушка для будущей реализации).
"""


class UDSClient:
    """Клиент для работы с API UDS."""

    async def get_orders(self, limit: int = 50) -> list[dict]:
        """Получить список заказов из UDS."""
        raise NotImplementedError("UDSClient не реализован")

    async def get_customer(self, customer_id: str) -> dict:
        """Получить данные клиента по ID."""
        raise NotImplementedError("UDSClient не реализован")
