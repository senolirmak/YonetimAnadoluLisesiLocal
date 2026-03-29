"""
Adım 1/3: DersProgrami'ne DersSaatleri FK kolonu ekle.
Mevcut giris_saat/cikis_saat/ders_saati/ders_saati_adi alanlarına dokunulmaz.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dersprogrami", "0004_rename_nobetdersprogrami_to_dersprogrami"),
        ("okul", "0004_add_ders_models"),
    ]

    operations = [
        migrations.AddField(
            model_name="dersprogrami",
            name="ders_saati_fk",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="dersprogrami",
                to="okul.derssaatleri",
                verbose_name="Ders Saati",
            ),
        ),
    ]
