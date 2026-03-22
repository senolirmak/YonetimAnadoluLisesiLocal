from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sinav", "0005_sabitsinav"),
    ]

    operations = [
        migrations.AddField(
            model_name="sabitsinav",
            name="seviyeler",
            field=models.CharField(blank=True, default="", max_length=20),
        ),
    ]
