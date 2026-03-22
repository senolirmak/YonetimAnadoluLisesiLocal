from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("sinav", "0006_sabitsinav_seviyeler"),
    ]

    operations = [
        migrations.CreateModel(
            name="SeviyeCatismaGrubu",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("grup_adi", models.CharField(max_length=100)),
                ("dersler", models.TextField(help_text="Virgülle ayrılmış ders adları")),
                (
                    "sinav",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="catisma_gruplari",
                        to="sinav.sinavbilgisi",
                    ),
                ),
            ],
            options={
                "ordering": ["grup_adi"],
            },
        ),
    ]
