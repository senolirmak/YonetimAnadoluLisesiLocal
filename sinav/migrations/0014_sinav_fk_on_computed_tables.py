from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("sinav", "0013_disveri"),
    ]

    operations = [
        migrations.AddField(
            model_name="subeders",
            name="sinav",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="sube_dersler",
                to="sinav.sinavbilgisi",
            ),
        ),
        migrations.AddField(
            model_name="takvim",
            name="sinav",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="takvimler",
                to="sinav.sinavbilgisi",
            ),
        ),
        migrations.AddField(
            model_name="oturmaplani",
            name="sinav",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="oturma_planlari",
                to="sinav.sinavbilgisi",
            ),
        ),
    ]
