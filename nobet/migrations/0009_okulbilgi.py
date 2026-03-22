from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("nobet", "0008_nobetdersprogrami_sinif_sube_fk"),
    ]

    operations = [
        migrations.CreateModel(
            name="OkulBilgi",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "okul_kodu",
                    models.CharField(blank=True, max_length=20, verbose_name="Okul Kodu"),
                ),
                ("okul_adi", models.CharField(blank=True, max_length=200, verbose_name="Okul Adı")),
                (
                    "okul_muduru",
                    models.CharField(blank=True, max_length=100, verbose_name="Okul Müdürü"),
                ),
            ],
            options={
                "verbose_name": "Okul Bilgisi",
                "verbose_name_plural": "Okul Bilgileri",
                "db_table": "okul_bilgi",
            },
        ),
    ]
