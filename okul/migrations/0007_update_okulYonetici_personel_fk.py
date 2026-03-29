"""
SeparateDatabaseAndState: OkulYonetici.personel FK'sını nobet.NobetPersonel'den
okul.NobetPersonel'e günceller. Veritabanına dokunulmaz.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("okul", "0006_add_nobetpersonel"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AlterField(
                    model_name="okulyonetici",
                    name="personel",
                    field=models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="okul_yonetici",
                        to="okul.nobetpersonel",
                        verbose_name="Personel",
                    ),
                ),
            ],
        ),
    ]
