from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("ogrenci", "0010_okulno_charfield_to_positiveinteger"),
        ("secmelidersler", "0008_remove_ogrencisecim"),
    ]

    operations = [
        # OgrenciSecmeliDers mevcut tabloyu (secmelidersler_ogrencisecim) yeniden kullanır
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="OgrenciSecmeliDers",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("secilen_saat", models.PositiveSmallIntegerField(verbose_name="Seçilen Saat")),
                        ("olusturma_tarihi", models.DateTimeField(auto_now_add=True)),
                        ("guncelleme_tarihi", models.DateTimeField(auto_now=True)),
                        ("ogrenci", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="secmeli_dersler", to="ogrenci.ogrenci", verbose_name="Öğrenci")),
                        ("ders", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="secimler", to="secmelidersler.secmeliDers", verbose_name="Seçmeli Ders")),
                    ],
                    options={
                        "verbose_name": "Öğrenci Seçmeli Ders Seçimi",
                        "verbose_name_plural": "Öğrenci Seçmeli Ders Seçimleri",
                        "db_table": "secmelidersler_ogrencisecim",
                        "unique_together": {("ogrenci", "ders")},
                    },
                ),
            ],
            database_operations=[],  # Tablo zaten mevcut
        ),
        # OgrenciZorunluDers yeni tablo
        migrations.CreateModel(
            name="OgrenciZorunluDers",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("ogrenci", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="zorunlu_dersler", to="ogrenci.ogrenci", verbose_name="Öğrenci")),
                ("ortak_ders", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="ogrenci_atamalari", to="secmelidersler.ortakders", verbose_name="Zorunlu Ders")),
            ],
            options={
                "verbose_name": "Öğrenci Zorunlu Ders Ataması",
                "verbose_name_plural": "Öğrenci Zorunlu Ders Atamaları",
                "ordering": ["ogrenci", "ortak_ders__sira"],
                "unique_together": {("ogrenci", "ortak_ders")},
            },
        ),
    ]
