# Generated manually for disiplin app

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("nobet", "0010_nobetpersonel_user"),
        ("ogrenci", "0003_ogrencidevamsizlik"),
    ]

    operations = [
        migrations.CreateModel(
            name="DisiplinGorusme",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "veli_adi",
                    models.CharField(blank=True, max_length=200, verbose_name="Veli Adı Soyadı"),
                ),
                (
                    "veli_telefon",
                    models.CharField(blank=True, max_length=30, verbose_name="Veli Telefonu"),
                ),
                ("tarih", models.DateField(verbose_name="Tarih")),
                (
                    "tur",
                    models.CharField(
                        choices=[
                            ("bireysel", "Bireysel Öğrenci"),
                            ("veli", "Veli Görüşmesi"),
                            ("grup", "Grup Görüşmesi"),
                        ],
                        max_length=20,
                        verbose_name="Görüşme Türü",
                    ),
                ),
                ("konu", models.CharField(max_length=300, verbose_name="Konu")),
                ("aciklama", models.TextField(blank=True, verbose_name="Açıklama")),
                ("sonuc", models.TextField(blank=True, verbose_name="Alınan Karar / Sonuç")),
                (
                    "takip_tarihi",
                    models.DateField(blank=True, null=True, verbose_name="Takip Tarihi"),
                ),
                ("gizli", models.BooleanField(default=False, verbose_name="Gizli Kayıt")),
                ("olusturma_zamani", models.DateTimeField(auto_now_add=True)),
                ("guncelleme_zamani", models.DateTimeField(auto_now=True)),
                (
                    "kayit_eden",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="disiplin_gorusmeleri",
                        to="nobet.nobetpersonel",
                        verbose_name="Kaydeden",
                    ),
                ),
                (
                    "ogrenci",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="disiplin_gorusmeleri",
                        to="ogrenci.ogrenci",
                        verbose_name="Öğrenci",
                    ),
                ),
                (
                    "grup_ogrencileri",
                    models.ManyToManyField(
                        blank=True,
                        related_name="disiplin_grup_gorusmeleri",
                        to="ogrenci.ogrenci",
                        verbose_name="Grup Öğrencileri",
                    ),
                ),
            ],
            options={
                "verbose_name": "Disiplin Görüşmesi",
                "verbose_name_plural": "Disiplin Görüşmeleri",
                "db_table": "disiplin_gorusme",
                "ordering": ["-tarih", "-olusturma_zamani"],
            },
        ),
        migrations.CreateModel(
            name="DisiplinCagri",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("tarih", models.DateField(verbose_name="Tarih")),
                (
                    "ders_saati",
                    models.IntegerField(blank=True, null=True, verbose_name="Ders Saati"),
                ),
                ("ders_adi", models.CharField(blank=True, max_length=100, verbose_name="Ders Adı")),
                (
                    "ogretmen_adi",
                    models.CharField(blank=True, max_length=100, verbose_name="Dersin Öğretmeni"),
                ),
                ("cagri_metni", models.TextField(blank=True, verbose_name="Çağrı Metni")),
                ("olusturma_zamani", models.DateTimeField(auto_now_add=True)),
                (
                    "gorusme",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="cagrilar",
                        to="disiplin.disiplingorusme",
                        verbose_name="Bağlı Görüşme",
                    ),
                ),
                (
                    "kayit_eden",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="disiplin_cagrilari",
                        to="nobet.nobetpersonel",
                        verbose_name="Kaydeden",
                    ),
                ),
                (
                    "ogrenci",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="disiplin_cagrilari",
                        to="ogrenci.ogrenci",
                        verbose_name="Öğrenci",
                    ),
                ),
            ],
            options={
                "verbose_name": "Disiplin Çağrısı",
                "verbose_name_plural": "Disiplin Çağrıları",
                "db_table": "disiplin_cagri",
                "ordering": ["-tarih", "ders_saati"],
            },
        ),
    ]
