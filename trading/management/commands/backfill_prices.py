from django.core.management.base import BaseCommand, CommandError

from trading.models import Stock
from trading.services.momentum_calculator import MomentumCalculator


class Command(BaseCommand):
    help = "Backfill daily price data for active stocks from Massive."

    def add_arguments(self, parser):
        parser.add_argument(
            "--ticker",
            help="Backfill one ticker only; without it, process all active stocks.",
        )
        parser.add_argument(
            "--days",
            type=int,
            default=420,
            help="Number of calendar days to request (default: 420).",
        )

    def handle(self, *args, **options):
        if options["days"] <= 0:
            raise CommandError("--days must be a positive integer.")

        stocks = Stock.objects.filter(is_active=True)
        if options["ticker"]:
            stocks = stocks.filter(ticker=options["ticker"].strip().upper())
            if not stocks.exists():
                raise CommandError(f"No active stock found for {options['ticker']}.")

        calculator = MomentumCalculator()
        total_added = 0
        for stock in stocks:
            added = calculator.backfill_price_data(stock, days_back=options["days"])
            total_added += added
            self.stdout.write(f"{stock.ticker}: {added} new daily bars")

        self.stdout.write(
            self.style.SUCCESS(f"Backfill complete: {total_added} new price bars.")
        )