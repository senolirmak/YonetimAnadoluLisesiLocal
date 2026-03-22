from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("rehberlik", "0003_ogrenci_cagri"),
    ]

    operations = [
        migrations.AddField(
            model_name="ogrencicagri",
            name="gorusme",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="cagrilar",
                to="rehberlik.gorusme",
                verbose_name="Bağlı Görüşme",
            ),
        ),
    ]
