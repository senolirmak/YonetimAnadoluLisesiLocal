from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("sinav", "0014_sinav_fk_on_computed_tables"),
    ]

    operations = [
        migrations.CreateModel(
            name="AlgoritmaParametreleri",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("baslangic_tarih",   models.DateField(blank=True, null=True)),
                ("oturum_saatleri",   models.CharField(default="08:50,10:30,12:10,13:35,14:25", max_length=200)),
                ("tatil_gunleri",     models.TextField(blank=True, default="")),
                ("time_limit_phase1", models.IntegerField(default=300)),
                ("time_limit_phase2", models.IntegerField(default=120)),
                ("max_extra_days",    models.IntegerField(default=10)),
                (
                    "sinav",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="parametreler",
                        to="sinav.sinavbilgisi",
                    ),
                ),
            ],
            options={
                "verbose_name": "Algoritma Parametreleri",
                "verbose_name_plural": "Algoritma Parametreleri",
            },
        ),
    ]
