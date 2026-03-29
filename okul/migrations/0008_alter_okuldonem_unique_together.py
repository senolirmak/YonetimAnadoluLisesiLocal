# State-only: unique_together zaten DB'de mevcut, sadece migration state senkronize ediliyor.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("okul", "0007_update_okulYonetici_personel_fk"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AlterUniqueTogether(
                    name="okuldonem",
                    unique_together={("egitim_yili", "donem")},
                ),
            ],
        ),
    ]
