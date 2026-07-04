import django.db.models.deletion
from django.db import migrations, models


def populate_brans_and_link(apps, schema_editor):
    """Mevcut Personel.brans (serbest metin) değerlerinden Brans kayıtları
    oluşturur ve her Personel'i doğru Brans'a bağlar. Bu noktada Personel
    hâlâ hem eski `brans` (CharField) hem yeni `brans_yeni` (FK) alanına
    sahiptir — veri kaybı olmadan geçiş yapılır."""
    Brans = apps.get_model("okul", "Brans")
    Personel = apps.get_model("okul", "Personel")

    brans_cache = {}
    for personel in Personel.objects.all():
        ad = (personel.brans or "").strip()
        if not ad:
            continue
        if ad not in brans_cache:
            brans_obj, _ = Brans.objects.get_or_create(ad=ad)
            brans_cache[ad] = brans_obj
        personel.brans_yeni_id = brans_cache[ad].id
        personel.save(update_fields=["brans_yeni"])


def reverse_populate(apps, schema_editor):
    """Geri alma: Brans adlarını tekrar Personel.brans metin alanına yazar."""
    Personel = apps.get_model("okul", "Personel")
    for personel in Personel.objects.select_related("brans_yeni").all():
        personel.brans = personel.brans_yeni.ad if personel.brans_yeni_id else ""
        personel.save(update_fields=["brans"])


class Migration(migrations.Migration):

    dependencies = [
        ("okul", "0012_add_aktif_veri_konfigurasyonu"),
    ]

    operations = [
        migrations.CreateModel(
            name="Brans",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("ad", models.CharField(max_length=50, unique=True, verbose_name="Branş Adı")),
            ],
            options={
                "verbose_name": "Branş",
                "verbose_name_plural": "Branşlar",
                "db_table": "okul_brans",
                "ordering": ["ad"],
            },
        ),
        migrations.AddField(
            model_name="personel",
            name="brans_yeni",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="personeller",
                to="okul.brans",
                verbose_name="Branş",
            ),
        ),
        migrations.RunPython(populate_brans_and_link, reverse_populate),
        migrations.RemoveField(
            model_name="personel",
            name="brans",
        ),
        migrations.RenameField(
            model_name="personel",
            old_name="brans_yeni",
            new_name="brans",
        ),
    ]
