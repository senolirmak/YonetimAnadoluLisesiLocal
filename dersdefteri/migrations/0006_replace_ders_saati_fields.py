"""
Adım 3/3: Eski ders_saati (int), giris_saat, cikis_saat alanlarını kaldır;
ders_saati_fk → ders_saati olarak yeniden adlandır.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("dersdefteri", "0005_data_ders_saati_fk"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="dersdefteri",
            name="ders_saati",
        ),
        migrations.RemoveField(
            model_name="dersdefteri",
            name="giris_saat",
        ),
        migrations.RemoveField(
            model_name="dersdefteri",
            name="cikis_saat",
        ),
        migrations.RenameField(
            model_name="dersdefteri",
            old_name="ders_saati_fk",
            new_name="ders_saati",
        ),
    ]
