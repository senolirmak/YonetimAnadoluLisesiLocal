"""
SeparateDatabaseAndState: Gorusme.gorusulen_ogretmen ve Gorusme.rehber FK'larını
nobet.NobetPersonel'den okul.NobetPersonel'e günceller. Veritabanına dokunulmaz.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("rehberlik", "0006_drop_ogrencicagri_table"),
        ("okul", "0009_rename_nobetpersonel_to_personel"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AlterField(
                    model_name="gorusme",
                    name="gorusulen_ogretmen",
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="gorusulen_gorusmeler",
                        to="okul.personel",
                        verbose_name="Görüşülen Öğretmen",
                    ),
                ),
                migrations.AlterField(
                    model_name="gorusme",
                    name="rehber",
                    field=models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="gorusmeler",
                        to="okul.personel",
                        verbose_name="Rehber Öğretmen",
                    ),
                ),
            ],
        ),
    ]
