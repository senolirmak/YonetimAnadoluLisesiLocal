import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sinav", "0028_takvim_uretim_fk"),
    ]

    operations = [
        migrations.AddField(
            model_name="oturmaplani",
            name="uretim",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="oturma_planlari",
                to="sinav.takvimuretim",
            ),
        ),
    ]
