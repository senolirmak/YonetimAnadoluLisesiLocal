"""
SeparateDatabaseAndState: OgrenciCagri.kayit_eden FK'sını nobet.NobetPersonel'den
okul.NobetPersonel'e günceller. Veritabanına dokunulmaz.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cagri", "0003_ogrencicagri_gorusme_muduriyetcagri"),
        ("okul", "0006_add_nobetpersonel"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AlterField(
                    model_name="ogrencicagri",
                    name="kayit_eden",
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="okul.nobetpersonel",
                        verbose_name="Kaydeden (Personel)",
                    ),
                ),
            ],
        ),
    ]
