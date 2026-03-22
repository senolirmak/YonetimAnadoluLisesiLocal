from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sinav", "0030_takvimuretim_oturma_sifirla"),
    ]

    operations = [
        migrations.AddField(
            model_name="takvimuretim",
            name="degisiklik_logu",
            field=models.TextField(blank=True, default=""),
        ),
    ]
