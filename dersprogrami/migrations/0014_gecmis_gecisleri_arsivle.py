from django.db import migrations
from django.db.models import Q


def gecmis_gecisleri_arsivle(apps, schema_editor):
    """Daha önce uygulanmış Sene Sonu Geçişlerine göre yüklenmiş ders programlarını
    (DersProgrami) geriye dönük arşivler.

    Bkz. nobet/migrations/0033_gecmis_nobet_gorevlerini_arsivle.py — aynı mantık.
    """
    SeneSonuGecisi = apps.get_model("senesonu", "SeneSonuGecisi")
    DersProgrami = apps.get_model("dersprogrami", "DersProgrami")

    for gecis in (
        SeneSonuGecisi.objects.filter(uygulandi=True)
        .select_related("eski_egitim_yili")
        .order_by("uygulama_zamani")
    ):
        DersProgrami.objects.filter(arsivlendi=False).filter(
            Q(egitim_yili=gecis.eski_egitim_yili_id)
            | Q(egitim_yili__isnull=True, uygulama_tarihi__lte=gecis.eski_egitim_yili.egitim_bitis)
        ).update(arsivlendi=True)


def geri_al(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("dersprogrami", "0013_dersprogrami_arsivlendi"),
        ("senesonu", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(gecmis_gecisleri_arsivle, geri_al),
    ]
