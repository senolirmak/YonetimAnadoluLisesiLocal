from django.db import migrations


def gecmis_gecisleri_arsivle(apps, schema_editor):
    """Daha önce uygulanmış Sene Sonu Geçişlerine göre geriye dönük arşivleme yapar.

    `arsivlendi` alanı bu migration'la birlikte eklendiği için, alan eklenmeden önce
    zaten uygulanmış geçişlerin (bkz. senesonu.SeneSonuGecisi) etkilediği geçmiş
    eğitim-öğretim yıllarına ait nöbet görevleri henüz arşivlenmemiş durumda kalır.
    Bu fonksiyon her uygulanmış geçiş için, geçişin eski eğitim-öğretim yılının bitiş
    tarihine kadar olan (ve henüz arşivlenmemiş) görevleri arşivler — böylece davranış,
    bundan sonra `senesonu.services.gecis_uygula` tarafından yapılacak arşivlemeyle
    tutarlı hâle gelir.
    """
    SeneSonuGecisi = apps.get_model("senesonu", "SeneSonuGecisi")
    OgrenciNobetGorevi = apps.get_model("ogrencinobet", "OgrenciNobetGorevi")

    for gecis in (
        SeneSonuGecisi.objects.filter(uygulandi=True)
        .select_related("eski_egitim_yili")
        .order_by("uygulama_zamani")
    ):
        OgrenciNobetGorevi.objects.filter(
            arsivlendi=False, tarih__lte=gecis.eski_egitim_yili.egitim_bitis
        ).update(arsivlendi=True)


def geri_al(apps, schema_editor):
    # Hangi kayıtların bu migration tarafından arşivlendiği izlenmediğinden, geri alma
    # işlemi (rollback) yapılmaz — arşivlenmiş kayıtlar arşivli kalır.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("ogrencinobet", "0002_ogrencinobetgorevi_arsivlendi"),
        ("senesonu", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(gecmis_gecisleri_arsivle, geri_al),
    ]
