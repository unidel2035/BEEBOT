"""Доменные исключения — общие для всех слоёв."""


class BeebotError(Exception):
    """Базовое исключение BEEBOT."""


class CRMUnavailable(BeebotError):
    """Integram CRM недоступна."""


class CRMNotFound(BeebotError):
    """Объект не найден в CRM."""


class LLMUnavailable(BeebotError):
    """LLM (Groq) недоступен."""


class KBNotReady(BeebotError):
    """База знаний не загружена."""


class InvalidStatus(BeebotError):
    """Некорректный статус заказа."""


class PermissionDenied(BeebotError):
    """Недостаточно прав для операции."""


class OrderNotEditable(BeebotError):
    """Заказ нельзя редактировать в текущем статусе."""
