from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sinav", "0034_kaldir_ogrenci_dersprogram"),
    ]

    operations = [
        migrations.AddField(
            model_name="takvimuretim",
            name="onizleme_verisi",
            field=models.JSONField(blank=True, default=None, null=True),
        ),
    ]
