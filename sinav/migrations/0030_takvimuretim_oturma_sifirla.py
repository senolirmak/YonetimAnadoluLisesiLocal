from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sinav", "0029_oturmaplani_uretim_fk"),
    ]

    operations = [
        migrations.AddField(
            model_name="takvimuretim",
            name="oturma_sifirla",
            field=models.BooleanField(default=False),
        ),
    ]
