from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("okul", "0011_add_dershavuzu_sinav_alanlari"),
        ("sinav", "0047_add_takvim_sinav_turu"),
    ]

    operations = [
        migrations.AddField(
            model_name="oturmaplani",
            name="gozetmen_fk",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="gozetmen_planlari",
                to="okul.personel",
            ),
        ),
    ]
