from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("secmelidersler", "0002_alan_remove_ogrencisecim_uniq_ogrenci_ders_and_more"),
    ]

    operations = [
        # 1. Eski basit M2M junction tablosunu düşür (DB), state'den field'ı kaldır
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    "DROP TABLE IF EXISTS secmelidersler_alan_dersler;",
                    reverse_sql="",
                ),
            ],
            state_operations=[
                migrations.RemoveField(model_name="alan", name="dersler"),
            ],
        ),
        # 2. AlanDers through model oluştur
        migrations.CreateModel(
            name="AlanDers",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("secilen_saat", models.PositiveSmallIntegerField(verbose_name="Seçilen Saat")),
                ("alan", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="alan_dersler", to="secmelidersler.alan")),
                ("ders", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="alan_dersler", to="secmelidersler.secmeliders")),
            ],
            options={
                "verbose_name": "Alan Dersi",
                "verbose_name_plural": "Alan Dersleri",
            },
        ),
        migrations.AlterUniqueTogether(
            name="alanders",
            unique_together={("alan", "ders")},
        ),
        # 3. Alan.dersler alanını through modeli ile yeniden ekle
        migrations.AddField(
            model_name="alan",
            name="dersler",
            field=models.ManyToManyField(
                blank=True,
                related_name="alanlar",
                through="secmelidersler.AlanDers",
                to="secmelidersler.secmeliders",
                verbose_name="Seçmeli Dersler",
            ),
        ),
    ]
