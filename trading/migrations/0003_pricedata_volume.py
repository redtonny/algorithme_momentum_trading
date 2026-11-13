from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("trading", "0002_tradingsignal_portfolio"),
    ]

    operations = [
        migrations.AddField(
            model_name="pricedata",
            name="volume",
            field=models.BigIntegerField(default=0),
        ),
    ]