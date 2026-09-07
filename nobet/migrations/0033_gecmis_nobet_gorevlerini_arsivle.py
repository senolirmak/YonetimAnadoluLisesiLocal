from django.db import migrations
from django.db.models import Q


def gecmis_gecisleri_arsivle(apps, schema_editor):
    """Daha önce uygulanmış Sene Sonu Geçişlerine göre yüklenmiş nöbet listelerini
    (NobetGorevi) geriye dönük arşivler.

    Bkz. nobet/migrations/0031_gecmis_gecisleri_arsivle.py — aynı mantık,
    `arsivlendi` alanı bu migration'la eklendiği için daha önce uygulanmış geçişlerin
    etkilediği eski eğitim-öğretim yılına ait nöbet görevleri henüz arşivlenmemiş
    durumda kalır.
    """
    SeneSonuGecisi = apps.get_model("senesonu", "SeneSonuGecisi")
    NobetGorevi = apps.get_model("nobet", "NobetGorevi")

    for gecis in (
        SeneSonuGecisi.objects.filter(uygulandi=True)
        .select_related("eski_egitim_yili")
        .order_by("uygulama_zamani")
    ):
        NobetGorevi.objects.filter(arsivlendi=False).filter(
            Q(egitim_yili=gecis.eski_egitim_yili_id)
            | Q(egitim_yili__isnull=True, uygulama_tarihi__lte=gecis.eski_egitim_yili.egitim_bitis)
        ).update(arsivlendi=True)


def geri_al(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("nobet", "0032_nobetgorevi_arsivlendi"),
        ("senesonu", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(gecmis_gecisleri_arsivle, geri_al),
    ]
