from datetime import date

from django.core.management.base import BaseCommand, CommandError

from trading.services.momentum_universe import sync_momentum_universe


class Command(BaseCommand):
    help = "Importe les grandes capitalisations S&P 500 et XAU/USD puis calcule leur momentum."

    def add_arguments(self, parser):
        parser.add_argument(
            "--date",
            type=date.fromisoformat,
            help="Date de calcul au format AAAA-MM-JJ (par défaut : aujourd'hui).",
        )

    def handle(self, *args, **options):
        try:
            result = sync_momentum_universe(calculation_date=options["date"])
        except Exception as error:
            raise CommandError(f"Échec de la synchronisation Massive : {error}") from error

        if not result["scores_calculated"]:
            raise CommandError(
                "Aucun score calculé. Vérifie l'accès Massive et la disponibilité des données."
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"{result['scores_calculated']} scores calculés pour "
                f"{result['stocks_added']} actifs ; "
                f"{result['prices_saved']} barres sauvegardées "
                f"({result['calculation_date']})."
            )
        )