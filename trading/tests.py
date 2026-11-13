from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import TestCase
from django.urls import reverse

from portfolio.models import Portfolio, Position
from trading.models import MomentumScore, Stock, TradingSignal
from trading.models import PriceData
from trading.services.momentum_universe import (
	GOLD_TICKER,
	SP500_LARGE_CAPS,
	sync_momentum_universe,
)


class TradingSignalGenerationTests(TestCase):
	def test_post_generates_buy_and_sell_signals_without_execution(self):
		portfolio = Portfolio.objects.create(
			name="Test portfolio",
			initial_cash=Decimal("1000.00"),
			current_cash=Decimal("1000.00"),
			total_value=Decimal("1000.00"),
		)
		stocks = [
			Stock.objects.create(ticker=f"T{i}", name=f"Stock {i}")
			for i in range(5)
		]
		for rank, stock in enumerate(stocks):
			MomentumScore.objects.create(
				stock=stock,
				calculation_date=date.today(),
				momentum_score=Decimal(rank),
				period_start=date.today() - timedelta(days=365),
				period_end=date.today() - timedelta(days=30),
			)
		Position.objects.create(
			portfolio=portfolio,
			stock=stocks[0],
			quantity=3,
			current_value=Decimal("30.00"),
		)

		with patch("trading.views.MomentumCalculator") as calculator_class:
			calculator_class.return_value.calculate_momentum_scores_bulk.return_value = list(
				MomentumScore.objects.filter(calculation_date=date.today())
			)
			response = self.client.post(
				reverse("trading:trading_signals"),
				{
					"portfolio": portfolio.pk,
					"tickers": ", ".join(stock.ticker for stock in stocks),
				},
			)
		self.assertEqual(Stock.objects.filter(is_active=True).count(), 5)
		calculator_class.assert_called_once()

		self.assertRedirects(
			response,
			f"{reverse('trading:trading_signals')}?portfolio={portfolio.pk}",
		)
		self.assertEqual(
			list(
				TradingSignal.objects.order_by("signal_type").values_list(
					"signal_type", "portfolio_id", "is_executed"
				)
			),
			[("BUY", portfolio.pk, False), ("SELL", portfolio.pk, False)],
		)


class MomentumUniverseTests(TestCase):
	@patch("trading.services.momentum_calculator.get_massive_client")
	def test_momentum_calculator_initializes_massive_client(self, get_client):
		from trading.services.momentum_calculator import MomentumCalculator

		client = object()
		get_client.return_value = client

		calculator = MomentumCalculator()

		self.assertIs(calculator.massive_client, client)

	@patch("trading.services.momentum_calculator.get_massive_client")
	def test_bulk_calculation_uses_initialized_massive_client(self, get_client):
		from trading.services.momentum_calculator import MomentumCalculator

		stock = Stock.objects.create(ticker="MSFT", name="Microsoft")
		get_client.return_value.fetch_bulk_momentum_data.return_value = {
			"MSFT": {"price_12m": 100, "price_1m": 110}
		}

		scores = MomentumCalculator().calculate_momentum_scores_bulk(
			stock_list=[stock], calculation_date=date.today()
		)

		self.assertEqual(len(scores), 1)
		self.assertEqual(scores[0].momentum_score, Decimal("0.1"))
		get_client.return_value.fetch_bulk_momentum_data.assert_called_once()

	@patch("trading.services.momentum_calculator.get_massive_client")
	def test_bulk_calculation_uses_stored_prices_before_calling_massive(self, get_client):
		from trading.services.momentum_calculator import MomentumCalculator

		stock = Stock.objects.create(ticker="AAPL", name="Apple")
		calculation_date = date(2026, 10, 26)
		for price_date, close in (
			(date(2025, 10, 23), Decimal("259.5800")),
			(date(2026, 9, 23), Decimal("337.0200")),
		):
			PriceData.objects.create(
				stock=stock,
				date=price_date,
				open_price=close,
				high=close,
				low=close,
				close=close,
				volume=0,
			)

		scores = MomentumCalculator().calculate_momentum_scores_bulk(
			stock_list=[stock], calculation_date=calculation_date
		)

		self.assertEqual(len(scores), 1)
		self.assertEqual(
			scores[0].momentum_score,
			(Decimal("337.0200") - Decimal("259.5800")) / Decimal("259.5800"),
		)
		get_client.return_value.fetch_bulk_momentum_data.assert_not_called()

	def test_sync_persists_51_scores_and_exposes_top_and_bottom_ten(self):
		class FakeMassiveClient:
			def __init__(self):
				self.client = self
				self.grouped_call = 0
				self.forex_call = 0

			def get_grouped_daily_aggs(self, date, **kwargs):
				self.grouped_call += 1
				close = 100 if self.grouped_call == 1 else 110
				return [
					SimpleNamespace(
						ticker=ticker,
						timestamp=int(
							datetime.combine(
								date, datetime.min.time(), tzinfo=timezone.utc
							).timestamp() * 1000
						),
						open=close,
						high=close,
						low=close,
						close=close,
						volume=1000,
					)
					for ticker in SP500_LARGE_CAPS
				]

			def list_aggs(self, ticker, multiplier, timespan, from_, to, **kwargs):
				self.forex_call += 1
				close = 100 if self.forex_call == 1 else 110
				return [
					SimpleNamespace(
						timestamp=int(
							datetime.combine(
								to, datetime.min.time(), tzinfo=timezone.utc
							).timestamp() * 1000
						),
						open=close,
						high=close,
						low=close,
						close=close,
						volume=0,
					)
				]

		calculation_date = date(2026, 10, 23)
		result = sync_momentum_universe(
			calculation_date=calculation_date,
			api_client=FakeMassiveClient(),
		)

		self.assertEqual(len(SP500_LARGE_CAPS), 50)
		self.assertEqual(result["scores_calculated"], 51)
		self.assertEqual(Stock.objects.filter(is_active=True).count(), 51)
		self.assertEqual(PriceData.objects.count(), 102)
		self.assertTrue(Stock.objects.filter(ticker=GOLD_TICKER).exists())
		self.assertEqual(
			MomentumScore.objects.filter(calculation_date=calculation_date).count(),
			51,
		)

		response = self.client.get(reverse("trading:momentum_scores"))

		self.assertEqual(response.status_code, 200)
		self.assertEqual(len(response.context["top_scores"]), 10)
		self.assertEqual(len(response.context["bottom_scores"]), 10)
		self.assertEqual(response.context["top_scores"][0].momentum_score, Decimal("0.1"))


class MomentumBackfillTests(TestCase):
	@patch("trading.services.momentum_calculator.get_massive_client")
	def test_backfill_persists_all_new_bars_and_skips_existing_dates(self, get_client):
		from trading.services.momentum_calculator import MomentumCalculator

		stock = Stock.objects.create(ticker="AAPL", name="Apple")
		client = Mock()
		client.fetch_stock_data.return_value = [
			{
				"date": date(2026, 10, day),
				"open": 100 + day,
				"high": 102 + day,
				"low": 99 + day,
				"close": 101 + day,
				"volume": 1000,
			}
			for day in (1, 2, 3)
		]
		get_client.return_value = client
		calculator = MomentumCalculator()

		created = calculator.backfill_price_data(stock, days_back=30)
		repeated = calculator.backfill_price_data(stock, days_back=30)

		self.assertEqual(created, 3)
		self.assertEqual(repeated, 0)
		self.assertEqual(stock.price_data.count(), 3)
		self.assertEqual(stock.price_data.order_by("date").first().ajusted_close, Decimal("102"))
		self.assertEqual(client.fetch_stock_data.call_count, 2)

	@patch("trading.services.momentum_calculator.get_massive_client")
	def test_validation_accepts_a_trading_year_of_price_data(self, get_client):
		from trading.services.momentum_calculator import MomentumCalculator

		stock = Stock.objects.create(ticker="MSFT", name="Microsoft")
		calculation_date = date(2026, 10, 26)
		price_rows = []
		for days_back in range(238):
			price_date = calculation_date - timedelta(days=days_back)
			close = Decimal("110") if days_back == 30 else Decimal("105")
			price_rows.append(
				PriceData(
					stock=stock,
					date=price_date,
					open_price=close,
					high=close,
					low=close,
					close=close,
					volume=1000,
				)
			)
		for days_back in (364, 365):
			price_rows.append(
				PriceData(
					stock=stock,
					date=calculation_date - timedelta(days=days_back),
					open_price=Decimal("100"),
					high=Decimal("100"),
					low=Decimal("100"),
					close=Decimal("100"),
					volume=1000,
				)
			)
		PriceData.objects.bulk_create(price_rows)
		get_client.return_value = Mock()

		result = MomentumCalculator().validate_momentum_calculation(
			stock, calculation_date
		)

		self.assertEqual(result["data_points_available"], 240)
		self.assertTrue(result["has_sufficient_data"])
		self.assertEqual(result["momentum_score"], Decimal("0.1"))

	@patch("trading.services.momentum_calculator.get_massive_client")
	def test_validate_momentum_uses_related_price_data_manager(self, get_client):
		from trading.services.momentum_calculator import MomentumCalculator

		stock = Stock.objects.create(ticker="AAPL", name="Apple")
		calculation_date = date(2026, 10, 26)
		for price_date, close in (
			(date(2025, 10, 23), Decimal("100")),
			(date(2026, 9, 23), Decimal("110")),
		):
			PriceData.objects.create(
				stock=stock,
				date=price_date,
				open_price=close,
				high=close,
				low=close,
				close=close,
				volume=0,
			)
		get_client.return_value = Mock()

		result = MomentumCalculator().validate_momentum_calculation(
			stock, calculation_date
		)

		self.assertEqual(result["data_points_available"], 2)
		self.assertEqual(result["momentum_score"], Decimal("0.1"))
		self.assertNotIn("error", result)

	def test_get_price_on_date_returns_none_for_empty_api_results(self):
		from trading.services.massive_client import MassiveApiClient

		client = MassiveApiClient.__new__(MassiveApiClient)
		client.fetch_stock_data = Mock(return_value=[])

		price = client.get_price_on_date("AAPL", date(2026, 10, 1))

		self.assertIsNone(price)
