"""Unit tests for src/delivery/ — DeliveryCalculator facade and providers."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from src.delivery.base import BaseDeliveryProvider, ShippingRate
from src.delivery.calculator import DeliveryCalculator, DeliveryQuote, TrackingStatus
from src.delivery.cdek import CDEKProvider
from src.delivery.pochta import PochtaProvider


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_rate(
    provider: str = "СДЭК",
    price: float = 400.0,
    days_min: int = 3,
    days_max: int = 7,
) -> ShippingRate:
    return ShippingRate(
        provider=provider,
        price=price,
        currency="RUB",
        days_min=days_min,
        days_max=days_max,
    )


_DEFAULT_TRACKING_RAW = {
    "status": "В пути",
    "description": "Посылка передана в сортировочный центр",
}


def _make_mock_provider(
    rate: ShippingRate | None = None,
    tracking_number: str = "TEST-001",
    tracking_raw: dict | None = None,
) -> AsyncMock:
    mock = AsyncMock(spec=BaseDeliveryProvider)
    mock.calculate_rate.return_value = rate or _make_rate()
    mock.create_shipment.return_value = tracking_number
    mock.track_shipment.return_value = (
        _DEFAULT_TRACKING_RAW if tracking_raw is None else tracking_raw
    )
    return mock


# ---------------------------------------------------------------------------
# ShippingRate dataclass
# ---------------------------------------------------------------------------


class TestShippingRate:
    def test_defaults(self):
        rate = ShippingRate(provider="СДЭК", price=350.0)
        assert rate.currency == "RUB"
        assert rate.days_min == 0
        assert rate.days_max == 0

    def test_all_fields(self):
        rate = ShippingRate(
            provider="Почта России",
            price=280.0,
            currency="RUB",
            days_min=7,
            days_max=14,
        )
        assert rate.provider == "Почта России"
        assert rate.price == 280.0
        assert rate.days_min == 7
        assert rate.days_max == 14


# ---------------------------------------------------------------------------
# CDEKProvider
# ---------------------------------------------------------------------------


class TestCDEKProvider:
    @pytest.mark.asyncio
    async def test_calculate_rate_basic(self):
        provider = CDEKProvider()
        rate = await provider.calculate_rate("Москва", "Новосибирск", 1.0)
        assert rate.provider == "СДЭК"
        assert rate.price == 400.0  # 350 + 50*1.0
        assert rate.days_min == 3
        assert rate.days_max == 7
        assert rate.currency == "RUB"

    @pytest.mark.asyncio
    async def test_calculate_rate_minimum_weight(self):
        """Минимальный вес 0.1 кг — не должно быть нулевой цены."""
        provider = CDEKProvider()
        rate = await provider.calculate_rate("Москва", "Казань", 0.0)
        assert rate.price == 355.0  # 350 + 50*0.1

    @pytest.mark.asyncio
    async def test_calculate_rate_heavy_parcel(self):
        provider = CDEKProvider()
        rate = await provider.calculate_rate("Москва", "Владивосток", 5.0)
        assert rate.price == 600.0  # 350 + 50*5.0

    @pytest.mark.asyncio
    async def test_create_shipment_not_implemented(self):
        provider = CDEKProvider()
        with pytest.raises(NotImplementedError):
            await provider.create_shipment({"delivery_method": "СДЭК"})

    @pytest.mark.asyncio
    async def test_track_shipment_not_implemented(self):
        provider = CDEKProvider()
        with pytest.raises(NotImplementedError):
            await provider.track_shipment("CDEK-123456")


# ---------------------------------------------------------------------------
# PochtaProvider
# ---------------------------------------------------------------------------


class TestPochtaProvider:
    @pytest.mark.asyncio
    async def test_calculate_rate_basic(self):
        provider = PochtaProvider()
        rate = await provider.calculate_rate("Москва", "Краснодар", 1.0)
        assert rate.provider == "Почта России"
        assert rate.price == 280.0  # 250 + 30*1.0
        assert rate.days_min == 7
        assert rate.days_max == 14
        assert rate.currency == "RUB"

    @pytest.mark.asyncio
    async def test_calculate_rate_minimum_weight(self):
        provider = PochtaProvider()
        rate = await provider.calculate_rate("Москва", "Казань", 0.0)
        assert rate.price == 253.0  # 250 + 30*0.1

    @pytest.mark.asyncio
    async def test_calculate_rate_heavy_parcel(self):
        provider = PochtaProvider()
        rate = await provider.calculate_rate("Москва", "Омск", 3.0)
        assert rate.price == 340.0  # 250 + 30*3.0

    @pytest.mark.asyncio
    async def test_create_shipment_not_implemented(self):
        provider = PochtaProvider()
        with pytest.raises(NotImplementedError):
            await provider.create_shipment({"delivery_method": "Почта России"})

    @pytest.mark.asyncio
    async def test_track_shipment_not_implemented(self):
        provider = PochtaProvider()
        with pytest.raises(NotImplementedError):
            await provider.track_shipment("80123456789RU")


# ---------------------------------------------------------------------------
# DeliveryCalculator.calculate
# ---------------------------------------------------------------------------


class TestDeliveryCalculatorCalculate:
    @pytest.mark.asyncio
    async def test_calculate_cdek(self):
        mock_cdek = _make_mock_provider(rate=_make_rate("СДЭК", 400.0, 3, 7))
        calc = DeliveryCalculator(cdek=mock_cdek)
        quote = await calc.calculate("Новосибирск", 1000, "СДЭК")
        assert isinstance(quote, DeliveryQuote)
        assert quote.provider == "СДЭК"
        assert quote.price == 400.0
        assert quote.days_min == 3
        assert quote.days_max == 7
        mock_cdek.calculate_rate.assert_awaited_once_with(
            origin_city="Москва",
            destination_city="Новосибирск",
            weight_kg=1.0,
        )

    @pytest.mark.asyncio
    async def test_calculate_pochta(self):
        mock_pochta = _make_mock_provider(rate=_make_rate("Почта России", 280.0, 7, 14))
        calc = DeliveryCalculator(pochta=mock_pochta)
        quote = await calc.calculate("Краснодар", 500, "Почта России")
        assert quote.provider == "Почта России"
        assert quote.price == 280.0
        mock_pochta.calculate_rate.assert_awaited_once_with(
            origin_city="Москва",
            destination_city="Краснодар",
            weight_kg=0.5,
        )

    @pytest.mark.asyncio
    async def test_calculate_converts_grams_to_kg(self):
        mock_cdek = _make_mock_provider()
        calc = DeliveryCalculator(cdek=mock_cdek)
        await calc.calculate("Москва", 2500, "СДЭК")
        _, kwargs = mock_cdek.calculate_rate.call_args
        assert kwargs["weight_kg"] == pytest.approx(2.5)

    @pytest.mark.asyncio
    async def test_calculate_custom_sender_city(self):
        mock_cdek = _make_mock_provider()
        calc = DeliveryCalculator(cdek=mock_cdek)
        await calc.calculate("Омск", 1000, "СДЭК", sender_city="Санкт-Петербург")
        _, kwargs = mock_cdek.calculate_rate.call_args
        assert kwargs["origin_city"] == "Санкт-Петербург"

    @pytest.mark.asyncio
    async def test_calculate_unknown_provider_raises(self):
        calc = DeliveryCalculator()
        with pytest.raises(ValueError, match="не поддерживается"):
            await calc.calculate("Москва", 1000, "Яндекс.Доставка")

    @pytest.mark.asyncio
    async def test_calculate_quote_has_currency(self):
        mock_cdek = _make_mock_provider()
        calc = DeliveryCalculator(cdek=mock_cdek)
        quote = await calc.calculate("Казань", 300, "СДЭК")
        assert quote.currency == "RUB"


# ---------------------------------------------------------------------------
# DeliveryCalculator.create_shipment
# ---------------------------------------------------------------------------


class TestDeliveryCalculatorCreateShipment:
    @pytest.mark.asyncio
    async def test_create_shipment_cdek(self):
        mock_cdek = _make_mock_provider(tracking_number="CDEK-987654")
        calc = DeliveryCalculator(cdek=mock_cdek)
        order = {"delivery_method": "СДЭК", "address": "ул. Ленина 1"}
        result = await calc.create_shipment(order)
        assert result == "CDEK-987654"
        mock_cdek.create_shipment.assert_awaited_once_with(order)

    @pytest.mark.asyncio
    async def test_create_shipment_pochta(self):
        mock_pochta = _make_mock_provider(tracking_number="80123456789RU")
        calc = DeliveryCalculator(pochta=mock_pochta)
        order = {"delivery_method": "Почта России", "address": "пр. Мира 5"}
        result = await calc.create_shipment(order)
        assert result == "80123456789RU"

    @pytest.mark.asyncio
    async def test_create_shipment_missing_method_raises(self):
        calc = DeliveryCalculator()
        with pytest.raises(ValueError, match="delivery_method"):
            await calc.create_shipment({"address": "ул. Ленина 1"})

    @pytest.mark.asyncio
    async def test_create_shipment_unknown_provider_raises(self):
        calc = DeliveryCalculator()
        with pytest.raises(ValueError, match="не поддерживается"):
            await calc.create_shipment({"delivery_method": "DHL"})


# ---------------------------------------------------------------------------
# DeliveryCalculator.track
# ---------------------------------------------------------------------------


class TestDeliveryCalculatorTrack:
    @pytest.mark.asyncio
    async def test_track_cdek(self):
        mock_cdek = _make_mock_provider(
            tracking_raw={"status": "Вручено", "description": "Получено адресатом"}
        )
        calc = DeliveryCalculator(cdek=mock_cdek)
        status = await calc.track("CDEK-111", provider_name="СДЭК")
        assert isinstance(status, TrackingStatus)
        assert status.tracking_number == "CDEK-111"
        assert status.provider == "СДЭК"
        assert status.status == "Вручено"
        assert status.description == "Получено адресатом"

    @pytest.mark.asyncio
    async def test_track_pochta(self):
        mock_pochta = _make_mock_provider(
            tracking_raw={"status": "В пути", "description": "Прибыло в место вручения"}
        )
        calc = DeliveryCalculator(pochta=mock_pochta)
        status = await calc.track("80123456789RU", provider_name="Почта России")
        assert status.provider == "Почта России"
        assert status.status == "В пути"

    @pytest.mark.asyncio
    async def test_track_default_provider_is_cdek(self):
        mock_cdek = _make_mock_provider()
        calc = DeliveryCalculator(cdek=mock_cdek)
        await calc.track("CDEK-222")
        mock_cdek.track_shipment.assert_awaited_once_with("CDEK-222")

    @pytest.mark.asyncio
    async def test_track_unknown_provider_raises(self):
        calc = DeliveryCalculator()
        with pytest.raises(ValueError, match="не поддерживается"):
            await calc.track("XYZ-001", provider_name="FedEx")

    @pytest.mark.asyncio
    async def test_track_missing_fields_defaults(self):
        """Если провайдер вернул пустой dict — используются дефолты."""
        mock_cdek = _make_mock_provider(tracking_raw={})
        calc = DeliveryCalculator(cdek=mock_cdek)
        status = await calc.track("CDEK-000")
        assert status.status == "Неизвестно"
        assert status.description == ""


# ---------------------------------------------------------------------------
# DeliveryCalculator.available_providers
# ---------------------------------------------------------------------------


class TestDeliveryCalculatorAvailableProviders:
    def test_returns_two_providers(self):
        calc = DeliveryCalculator()
        providers = calc.available_providers()
        assert len(providers) == 2

    def test_contains_cdek(self):
        calc = DeliveryCalculator()
        assert "СДЭК" in calc.available_providers()

    def test_contains_pochta(self):
        calc = DeliveryCalculator()
        assert "Почта России" in calc.available_providers()


# ---------------------------------------------------------------------------
# Integration: DeliveryCalculator with real CDEKProvider / PochtaProvider
# ---------------------------------------------------------------------------


class TestDeliveryCalculatorRealProviders:
    """Smoke tests with real (stub) providers — no mocking."""

    @pytest.mark.asyncio
    async def test_cdek_smoke(self):
        calc = DeliveryCalculator()
        quote = await calc.calculate("Новосибирск", 500, "СДЭК")
        assert quote.price > 0
        assert quote.days_max >= quote.days_min

    @pytest.mark.asyncio
    async def test_pochta_smoke(self):
        calc = DeliveryCalculator()
        quote = await calc.calculate("Омск", 300, "Почта России")
        assert quote.price > 0
        assert quote.days_max >= quote.days_min

    @pytest.mark.asyncio
    async def test_cdek_create_shipment_raises_not_implemented(self):
        calc = DeliveryCalculator()
        with pytest.raises(NotImplementedError):
            await calc.create_shipment({"delivery_method": "СДЭК"})

    @pytest.mark.asyncio
    async def test_pochta_create_shipment_raises_not_implemented(self):
        calc = DeliveryCalculator()
        with pytest.raises(NotImplementedError):
            await calc.create_shipment({"delivery_method": "Почта России"})

    @pytest.mark.asyncio
    async def test_cdek_track_raises_not_implemented(self):
        calc = DeliveryCalculator()
        with pytest.raises(NotImplementedError):
            await calc.track("CDEK-001", provider_name="СДЭК")

    @pytest.mark.asyncio
    async def test_pochta_track_raises_not_implemented(self):
        calc = DeliveryCalculator()
        with pytest.raises(NotImplementedError):
            await calc.track("80123456789RU", provider_name="Почта России")
