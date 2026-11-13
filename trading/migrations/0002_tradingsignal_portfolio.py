from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("portfolio", "0001_initial"),
        ("trading", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="tradingsignal",
            name="portfolio",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="signals",
                to="portfolio.portfolio",
            ),
        ),
    ]