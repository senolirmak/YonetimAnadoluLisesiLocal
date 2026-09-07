from django.db import migrations
from django.db.models import Q


def gecmis_gecisleri_pasife_al(apps, schema_editor):
    """Daha önce uygulanmış Sene Sonu Geçişlerine göre geriye dönük olarak, eski
    eğitim-öğretim yılına ait ve hâlâ "aktif" işaretli kalmış SinavBilgisi
    kayıtlarını pasife alır.

    Bkz. senesonu/services.py: gecis_uygula — aynı mantık. Bu migration'ın
    uygulandığı sırada gerçek veride zaten yeni yıl için bir SinavBilgisi
    oluşturulup aktif yapılmış olabilir (bu durumda no-op'tur); amaç, bu adımın
    daha önce elle yapılmamış olduğu ortamlarda tutarlılığı sağlamaktır.
    """
    SeneSonuGecisi = apps.get_model("senesonu", "SeneSonuGecisi")
    SinavBilgisi = apps.get_model("sinav", "SinavBilgisi")

    for gecis in (
        SeneSonuGecisi.objects.filter(uygulandi=True)
        .select_related("eski_egitim_yili")
        .order_by("uygulama_zamani")
    ):
        SinavBilgisi.objects.filter(aktif=True).filter(
            Q(egitim_yili_fk=gecis.eski_egitim_yili_id)
            | Q(
                egitim_yili_fk__isnull=True,
                egitim_ogretim_yili=gecis.eski_egitim_yili.egitim_yili,
            )
        ).update(aktif=False)


def geri_al(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("sinav", "0062_sinavogrenci_sinavogrencimuaf"),
        ("senesonu", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(gecmis_gecisleri_pasife_al, geri_al),
    ]
