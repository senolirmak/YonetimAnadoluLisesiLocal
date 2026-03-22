from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("sinav", "0004_ciftoturumluders_sinav_sinavyapilmayacakders_sinav_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="SabitSinav",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("ders_adi", models.CharField(max_length=200)),
                ("tarih", models.DateField()),
                ("saat", models.CharField(max_length=8)),
                (
                    "sinav",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sabit_sinavlar",
                        to="sinav.sinavbilgisi",
                    ),
                ),
            ],
            options={
                "ordering": ["tarih", "saat", "ders_adi"],
                "unique_together": {("sinav", "ders_adi")},
            },
        ),
    ]
