from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("ogrenci", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="OrtakDers",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sinif_seviyesi", models.IntegerField(choices=[(9, "9. Sınıf"), (10, "10. Sınıf"), (11, "11. Sınıf"), (12, "12. Sınıf")], verbose_name="Sınıf Seviyesi")),
                ("ders_adi", models.CharField(max_length=150, verbose_name="Ders Adı")),
                ("haftalik_saat", models.PositiveSmallIntegerField(verbose_name="Haftalık Saat")),
                ("sira", models.PositiveSmallIntegerField(default=0, verbose_name="Sıra")),
            ],
            options={"verbose_name": "Ortak Ders", "verbose_name_plural": "Ortak Dersler", "ordering": ["sinif_seviyesi", "sira"]},
        ),
        migrations.CreateModel(
            name="SecmeliDersGrubu",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sinif_seviyesi", models.IntegerField(choices=[(9, "9. Sınıf"), (10, "10. Sınıf"), (11, "11. Sınıf"), (12, "12. Sınıf")], verbose_name="Sınıf Seviyesi")),
                ("adi", models.CharField(max_length=100, verbose_name="Grup Adı")),
                ("zorunlu_grup", models.BooleanField(default=False, help_text="9-10. sınıf: zorunlu grupların tamamından en az 1 ders seçilmeli. 11-12. sınıf: zorunlu grupların en az ikisinden 1 ders seçilmeli.", verbose_name="Zorunlu Grup")),
                ("sira", models.PositiveSmallIntegerField(default=0, verbose_name="Sıra")),
            ],
            options={"verbose_name": "Seçmeli Ders Grubu", "verbose_name_plural": "Seçmeli Ders Grupları", "ordering": ["sinif_seviyesi", "sira"]},
        ),
        migrations.CreateModel(
            name="SecmeliDers",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("grup", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="dersler", to="secmelidersler.secmelidersgrubu", verbose_name="Grup")),
                ("ders_adi", models.CharField(max_length=200, verbose_name="Ders Adı")),
                ("saat_secenekleri", models.CharField(help_text="Virgülle ayrılmış saat seçenekleri. Tek değer sabit saati gösterir. Örn: '4' veya '2,4' veya '1,2,3'", max_length=50, verbose_name="Saat Seçenekleri")),
                ("sira", models.PositiveSmallIntegerField(default=0, verbose_name="Sıra")),
                ("aktif", models.BooleanField(default=True, verbose_name="Aktif")),
            ],
            options={"verbose_name": "Seçmeli Ders", "verbose_name_plural": "Seçmeli Dersler", "ordering": ["sira"]},
        ),
        migrations.CreateModel(
            name="OgrenciSecim",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("ogrenci", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="secmeli_dersler", to="ogrenci.ogrenci", verbose_name="Öğrenci")),
                ("ders", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="secimler", to="secmelidersler.secmeliders", verbose_name="Seçmeli Ders")),
                ("secilen_saat", models.PositiveSmallIntegerField(verbose_name="Seçilen Saat")),
                ("olusturma_tarihi", models.DateTimeField(auto_now_add=True)),
                ("guncelleme_tarihi", models.DateTimeField(auto_now=True)),
            ],
            options={"verbose_name": "Öğrenci Seçmeli Ders Seçimi", "verbose_name_plural": "Öğrenci Seçmeli Ders Seçimleri"},
        ),
        migrations.AddConstraint(
            model_name="ogrencisecim",
            constraint=models.UniqueConstraint(fields=("ogrenci", "ders"), name="uniq_ogrenci_ders"),
        ),
    ]
