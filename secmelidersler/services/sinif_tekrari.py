"""Sınıf tekrarı kayıtlarına ilişkin iş mantığı.

`OgrenciSinifTekrari.ogrenci` OneToOneField olduğundan bir öğrencinin aynı anda
yalnızca TEK bir tekrar kaydı olabilir — yeni bir tekrar kaydı FARKLI bir eğitim-
öğretim yılı için oluşturulduğunda bu, önceki kaydın üzerine yazılır. Böyle bir
üzerine yazma, öğrencinin İKİNCİ (farklı bir yılda) sınıf tekrarı yaptığı anlamına
gelir; Türk eğitim sistemindeki öğrenim hakkı kuralına göre bu durumda öğrenim hakkı
sona erer. Bu modül bu kuralı uygular: öğrenciye otomatik Tasdikname + Ayrılma
("Öğrenim Hakkını Tamamladı") kaydı açar ve `Ogrenci.aktif`i False yapar.
"""
from django.utils import timezone


def ikinci_tekrar_ise_ogrenim_hakkini_sonlandir(ogrenci, mevcut_tekrar, yeni_egitim_yili):
    """`mevcut_tekrar` — öğrencinin GÜNCELLEMEDEN ÖNCEKİ (varsa) tek `OgrenciSinifTekrari`
    kaydı. `mevcut_tekrar.egitim_yili`, yeni oluşturulan/güncellenen kaydın
    `yeni_egitim_yili`sinden FARKLIysa bu ikinci bir tekrar olayıdır — cascade
    tetiklenir ve True döner. Aynı yıl için güncelleme (aciklama düzeltmesi vb.) ya da
    öğrencinin ilk tekrar kaydıysa (mevcut_tekrar None) hiçbir şey yapılmaz, False döner.
    """
    ikinci_mi = bool(
        mevcut_tekrar
        and mevcut_tekrar.egitim_yili_id
        and yeni_egitim_yili
        and mevcut_tekrar.egitim_yili_id != yeni_egitim_yili.pk
    )
    if not ikinci_mi:
        return False

    from ogrenci.models import OgrenciAyrilma

    from ..models import OgrenciTasdikname

    bugun = timezone.now().date()
    aciklama = (
        f"İkinci sınıf tekrarı ({mevcut_tekrar.egitim_yili} → {yeni_egitim_yili}) "
        "nedeniyle öğrenim hakkı tamamlandı (otomatik oluşturuldu)."
    )

    OgrenciTasdikname.objects.update_or_create(
        ogrenci=ogrenci,
        defaults={"egitim_yili": yeni_egitim_yili, "tarih": bugun, "aciklama": aciklama},
    )
    OgrenciAyrilma.objects.update_or_create(
        ogrenci=ogrenci,
        defaults={
            "sebep": "ogrenim_hakki",
            "egitim_yili": yeni_egitim_yili,
            "tarih": bugun,
            "aciklama": aciklama,
        },
    )
    if ogrenci.aktif:
        ogrenci.aktif = False
        ogrenci.save(update_fields=["aktif"])

    return True
