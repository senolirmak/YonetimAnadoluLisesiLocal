import django.db.models.deletion
from django.db import migrations, models


def populate_sinif_sube(apps, schema_editor):
    NobetDersProgrami = apps.get_model("nobet", "NobetDersProgrami")
    SinifSube = apps.get_model("nobet", "SinifSube")
    sinif_sube_map = {(ss.sinif, ss.sube): ss for ss in SinifSube.objects.all()}
    for dp in NobetDersProgrami.objects.all():
        try:
            ss = sinif_sube_map.get((int(dp.sinif), str(dp.sube)))
            if ss:
                dp.sinif_sube = ss
                dp.save(update_fields=["sinif_sube"])
        except (ValueError, TypeError):
            pass


class Migration(migrations.Migration):
    dependencies = [
        ("nobet", "0007_alter_devamsizlik_baslangic_tarihi_and_more"),
    ]

    operations = [
        # 1. Nullable FK ekle
        migrations.AddField(
            model_name="nobetdersprogrami",
            name="sinif_sube",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="dersprogrami",
                to="nobet.sinifsube",
                verbose_name="Sınıf/Şube",
            ),
        ),
        # 2. Mevcut verileri FK ile eşleştir
        migrations.RunPython(populate_sinif_sube, migrations.RunPython.noop),
        # 3. Eski alanları sil
        migrations.RemoveField(model_name="nobetdersprogrami", name="sinif"),
        migrations.RemoveField(model_name="nobetdersprogrami", name="sube"),
        migrations.RemoveField(model_name="nobetdersprogrami", name="subeadi"),
    ]
