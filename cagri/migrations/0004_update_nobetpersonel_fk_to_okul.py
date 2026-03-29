"""
SeparateDatabaseAndState: OgrenciCagri.kayit_eden FK'sını nobet.NobetPersonel'den
okul.NobetPersonel'e günceller. Veritabanına dokunulmaz.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cagri", "0003_ogrencicagri_gorusme_muduriyetcagri"),
        ("okul", "0009_rename_nobetpersonel_to_personel"),
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
                        to="okul.personel",
                        verbose_name="Kaydeden (Personel)",
                    ),
                ),
            ],
        ),
    ]
