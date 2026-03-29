"""
SeparateDatabaseAndState: SinavBilgisi'nin kurum/egitim_yili_fk/donem_fk
FK referanslarını nobet.* → okul.* olarak günceller.
Tablolar aynı kaldığından veritabanına dokunulmaz.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sinav", "0041_data_takvim_ders_saati"),
        ("okul", "0003_add_school_calendar_models"),
        ("nobet", "0018_remove_school_calendar_models"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AlterField(
                    model_name="sinavbilgisi",
                    name="kurum",
                    field=models.ForeignKey(
                        blank=True, null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="sinavlar",
                        to="okul.okulbilgi",
                        verbose_name="Kurum",
                    ),
                ),
                migrations.AlterField(
                    model_name="sinavbilgisi",
                    name="egitim_yili_fk",
                    field=models.ForeignKey(
                        blank=True, null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="sinavlar",
                        to="okul.egitimogretimyili",
                        verbose_name="Eğitim-Öğretim Yılı (Bağlantı)",
                    ),
                ),
                migrations.AlterField(
                    model_name="sinavbilgisi",
                    name="donem_fk",
                    field=models.ForeignKey(
                        blank=True, null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="sinavlar",
                        to="okul.okuldonem",
                        verbose_name="Dönem (Bağlantı)",
                    ),
                ),
            ],
        ),
    ]
