"""
Adım 3/3: Eski giris_saat, cikis_saat, ders_saati (int), ders_saati_adi alanlarını kaldır.
ders_saati_fk → ders_saati olarak yeniden adlandır.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("dersprogrami", "0006_data_ders_saati_fk"),
    ]

    operations = [
        migrations.RemoveField(model_name="dersprogrami", name="giris_saat"),
        migrations.RemoveField(model_name="dersprogrami", name="cikis_saat"),
        migrations.RemoveField(model_name="dersprogrami", name="ders_saati_adi"),
        migrations.RemoveField(model_name="dersprogrami", name="ders_saati"),
        migrations.RenameField(
            model_name="dersprogrami",
            old_name="ders_saati_fk",
            new_name="ders_saati",
        ),
    ]
