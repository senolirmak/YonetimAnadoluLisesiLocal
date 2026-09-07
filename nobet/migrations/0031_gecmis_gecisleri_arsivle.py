from django.db import migrations


def gecmis_gecisleri_arsivle(apps, schema_editor):
    """Daha önce uygulanmış Sene Sonu Geçişlerine göre geriye dönük arşivleme yapar.

    `arsivlendi` alanı bu migration'la birlikte eklendiği için, alan eklenmeden önce
    zaten uygulanmış geçişlerin (bkz. senesonu.SeneSonuGecisi) etkilediği geçmiş
    eğitim-öğretim yıllarına ait ders doldurma/atanamayan kayıtları henüz arşivlenmemiş
    durumda kalır. Bu fonksiyon her uygulanmış geçiş için, geçişin eski eğitim-öğretim
    yılının bitiş tarihine kadar olan (ve henüz arşivlenmemiş) kayıtları arşivler —
    böylece davranış, bundan sonra `senesonu.services.gecis_uygula` tarafından
    yapılacak arşivlemeyle tutarlı hâle gelir.

    NobetIstatistik ayrı bir arşiv alanı taşımaz — tamamen NobetGecmisi/NobetAtanamayan
    üzerinden türetilen bir önbellektir (bkz. IstatistikService.hesapla_ve_kaydet).
    Arşivlemeden sonra geriye arşivlenmemiş hiç kayıt kalmadığı için (bu geçişten önce
    oluşturulmuş tüm kayıtlar eski yıla ait), istatistikleri doğrudan sıfırlamak
    yeniden hesaplamayla aynı sonucu verir.
    """
    SeneSonuGecisi = apps.get_model("senesonu", "SeneSonuGecisi")
    NobetGecmisi = apps.get_model("nobet", "NobetGecmisi")
    NobetAtanamayan = apps.get_model("nobet", "NobetAtanamayan")
    NobetIstatistik = apps.get_model("nobet", "NobetIstatistik")

    herhangi_arsivlendi = False
    for gecis in (
        SeneSonuGecisi.objects.filter(uygulandi=True)
        .select_related("eski_egitim_yili")
        .order_by("uygulama_zamani")
    ):
        eski_bitis = gecis.eski_egitim_yili.egitim_bitis
        n1 = NobetGecmisi.objects.filter(arsivlendi=False, tarih__date__lte=eski_bitis).update(
            arsivlendi=True
        )
        n2 = NobetAtanamayan.objects.filter(
            arsivlendi=False, tarih__date__lte=eski_bitis
        ).update(arsivlendi=True)
        herhangi_arsivlendi = herhangi_arsivlendi or n1 or n2

    if herhangi_arsivlendi:
        # Arşivlemeden sonra hâlâ arşivlenmemiş (cari yıla ait) kaydı olan öğretmenler
        # varsa dokunulmaz; kalan tüm öğretmenler için istatistik sıfırlanır.
        etkilenmeyen_ogretmen_ids = set(
            NobetGecmisi.objects.filter(arsivlendi=False).values_list("ogretmen_id", flat=True)
        ) | set(
            NobetAtanamayan.objects.filter(arsivlendi=False).values_list("ogretmen_id", flat=True)
        )
        NobetIstatistik.objects.exclude(ogretmen_id__in=etkilenmeyen_ogretmen_ids).update(
            toplam_nobet=0,
            atanmayan_nobet=0,
            haftalik_ortalama=0.0,
            hafta_sayisi=0,
            son_nobet_tarihi=None,
            son_nobet_yeri=None,
            agirlikli_puan=0.0,
        )


def geri_al(apps, schema_editor):
    # Hangi kayıtların bu migration tarafından arşivlendiği/sıfırlandığı izlenmediğinden,
    # geri alma işlemi (rollback) yapılmaz.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("nobet", "0030_nobetatanamayan_arsivlendi_nobetgecmisi_arsivlendi"),
        ("senesonu", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(gecmis_gecisleri_arsivle, geri_al),
    ]
