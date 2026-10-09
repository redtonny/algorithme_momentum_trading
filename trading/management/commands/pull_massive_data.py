from django.core.management.base import BaseCommand
from trading.services.massive_client import MassiveApiClient
from datetime import date

class Command(BaseCommand):
        
    def handle(self, *args, **options):
        client = MassiveApiClient()
        result= client.fetch_bulk_momentum_data(["AAPL", "NVDA"], date(2026, 10, 9))
        print(result)
        breakpoint()
       