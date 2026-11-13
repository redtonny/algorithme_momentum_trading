from datetime import date, datetime, timedelta, timezone as datetime_timezone
from decimal import Decimal

from django.utils import timezone

from trading.models import MomentumScore, PriceData, Stock
from trading.services.massive_client import MassiveApiClient


SP500_LARGE_CAPS = {
    "NVDA": "NVIDIA Corporation",
    "MSFT": "Microsoft Corporation",
    "AAPL": "Apple Inc.",
    "AMZN": "Amazon.com, Inc.",
    "GOOGL": "Alphabet Inc. Class A",
    "GOOG": "Alphabet Inc. Class C",
    "META": "Meta Platforms, Inc.",
    "AVGO": "Broadcom Inc.",
    "BRK.B": "Berkshire Hathaway Inc. Class B",
    "TSLA": "Tesla, Inc.",
    "WMT": "Walmart Inc.",
    "JPM": "JPMorgan Chase & Co.",
    "LLY": "Eli Lilly and Company",
    "V": "Visa Inc.",
    "MA": "Mastercard Incorporated",
    "XOM": "Exxon Mobil Corporation",
    "ORCL": "Oracle Corporation",
    "COST": "Costco Wholesale Corporation",
    "NFLX": "Netflix, Inc.",
    "JNJ": "Johnson & Johnson",
    "ABBV": "AbbVie Inc.",
    "PG": "The Procter & Gamble Company",
    "HD": "The Home Depot, Inc.",
    "BAC": "Bank of America Corporation",
    "CRM": "Salesforce, Inc.",
    "CVX": "Chevron Corporation",
    "KO": "The Coca-Cola Company",
    "AMD": "Advanced Micro Devices, Inc.",
    "MRK": "Merck & Co., Inc.",
    "GE": "GE Aerospace",
    "CAT": "Caterpillar Inc.",
    "CSCO": "Cisco Systems, Inc.",
    "IBM": "International Business Machines Corporation",
    "LIN": "Linde plc",
    "MCD": "McDonald's Corporation",
    "PM": "Philip Morris International Inc.",
    "TMO": "Thermo Fisher Scientific Inc.",
    "WFC": "Wells Fargo & Company",
    "ABT": "Abbott Laboratories",
    "ACN": "Accenture plc",
    "GS": "The Goldman Sachs Group, Inc.",
    "DIS": "The Walt Disney Company",
    "RTX": "RTX Corporation",
    "NOW": "ServiceNow, Inc.",
    "QCOM": "QUALCOMM Incorporated",
    "TXN": "Texas Instruments Incorporated",
    "AMGN": "Amgen Inc.",
    "ISRG": "Intuitive Surgical, Inc.",
    "VZ": "Verizon Communications Inc.",
    "PEP": "PepsiCo, Inc.",
}

GOLD_TICKER = "C:SD"
GOLD_NAME = "Gold / US Dollar"


def sync_momentum_universe(calculation_date=None, api_client=None):
    calculation_date = calculation_date or timezone.localdate()
    api_client = api_client or MassiveApiClient()
    tickers = list(SP500_LARGE_CAPS)
    stocks = {}

    for ticker, name in SP500_LARGE_CAPS.items():
        stock, _ = Stock.objects.update_or_create(
            ticker=ticker,
            defaults={"name": name, "is_active": True},
        )
        stocks[ticker] = stock

    gold, _ = Stock.objects.update_or_create(
        ticker=GOLD_TICKER,
        defaults={"name": GOLD_NAME, "is_active": True},
    )
    stocks[GOLD_TICKER] = gold

    period_start_target = calculation_date - timedelta(days=365)
    period_end_target = calculation_date - timedelta(days=30)
    old_bars = _fetch_grouped_stock_bars(
        api_client, tickers, period_start_target
    )
    recent_bars = _fetch_grouped_stock_bars(
        api_client, tickers, period_end_target
    )
    old_bars[GOLD_TICKER] = _fetch_gold_bar(api_client, period_start_target)
    recent_bars[GOLD_TICKER] = _fetch_gold_bar(api_client, period_end_target)

    saved_prices = 0
    scores = []
    for ticker, stock in stocks.items():
        old_bar = old_bars.get(ticker)
        recent_bar = recent_bars.get(ticker)
        if not old_bar or not recent_bar:
            continue

        _save_price_bar(stock, old_bar)
        _save_price_bar(stock, recent_bar)
        saved_prices += 2

        old_close = Decimal(str(old_bar["close"]))
        recent_close = Decimal(str(recent_bar["close"]))
        if old_close <= 0:
            continue

        score, _ = MomentumScore.objects.update_or_create(
            stock=stock,
            calculation_date=calculation_date,
            defaults={
                "momentum_score": (recent_close - old_close) / old_close,
                "period_start": old_bar["date"],
                "period_end": recent_bar["date"],
            },
        )
        scores.append(score)

    scores.sort(key=lambda item: (-item.momentum_score, item.stock.ticker))
    total_scores = len(scores)
    for index, score in enumerate(scores):
        score.rank = index + 1
        score.quintile = min(5, index * 5 // total_scores + 1)
        score.is_top_quintile = score.quintile == 1
        score.save(update_fields=["rank", "quintile", "is_top_quintile"])

    return {
        "stocks_added": len(stocks),
        "prices_saved": saved_prices,
        "scores_calculated": total_scores,
        "calculation_date": calculation_date,
    }


def _fetch_grouped_stock_bars(api_client, tickers, target_date):
    remaining = set(tickers)
    found = {}
    for days_back in range(8):
        requested_date = target_date - timedelta(days=days_back)
        _respect_rate_limit(api_client)
        grouped_bars = api_client.client.get_grouped_daily_aggs(
            date=requested_date,
            adjusted=True,
            market_type="stocks",
        )
        for bar in grouped_bars:
            ticker = getattr(bar, "ticker", None)
            if ticker not in remaining:
                continue
            found[ticker] = _bar_record(bar, requested_date)
            remaining.remove(ticker)
        if not remaining:
            break
    return found


def _fetch_gold_bar(api_client, target_date):
    start_date = target_date - timedelta(days=7)
    _respect_rate_limit(api_client)
    bars = api_client.client.list_aggs(
        GOLD_TICKER,
        1,
        "day",
        start_date,
        target_date,
        adjusted=True,
        limit=100,
    )
    available = []
    for bar in bars:
        bar_date = datetime.fromtimestamp(
            bar.timestamp / 1000, tz=datetime_timezone.utc
        ).date()
        if start_date <= bar_date <= target_date:
            available.append(_bar_record(bar, bar_date))
    return max(available, key=lambda item: item["date"]) if available else None


def _respect_rate_limit(api_client):
    rate_limiter = getattr(api_client, "_rate_limit", None)
    if rate_limiter:
        rate_limiter()


def _bar_record(bar, fallback_date):
    timestamp = getattr(bar, "timestamp", None)
    bar_date = (
        datetime.fromtimestamp(timestamp / 1000, tz=datetime_timezone.utc).date()
        if timestamp
        else fallback_date
    )
    return {
        "date": bar_date,
        "open": getattr(bar, "open", getattr(bar, "close", 0)),
        "high": getattr(bar, "high", getattr(bar, "close", 0)),
        "low": getattr(bar, "low", getattr(bar, "close", 0)),
        "close": getattr(bar, "close", 0),
        "volume": getattr(bar, "volume", 0) or 0,
    }


def _save_price_bar(stock, bar):
    close = Decimal(str(bar["close"]))
    PriceData.objects.update_or_create(
        stock=stock,
        date=bar["date"],
        defaults={
            "open_price": Decimal(str(bar["open"])),
            "high": Decimal(str(bar["high"])),
            "low": Decimal(str(bar["low"])),
            "close": close,
            "volume": int(bar["volume"]),
            "ajusted_close": close,
        },
    )