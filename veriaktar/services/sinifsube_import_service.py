from okul.models import SinifSube, SinifSubeYil


def sinif_sube_kaydet(sinif_bilgileri):
    """Sınıf/Şube listesini içe aktarır.

    Mevcut kayıtları SİLİP YENİDEN OLUŞTURMAZ — bunu yapmak SinifSube'a FK ile bağlı
    diğer kayıtları kalıcı olarak koparır/siler: CASCADE olanlar (ogrenci.SinifOturmaDuzeni,
    sinav.SubeDers) tamamen silinir, SET_NULL olanlar (dersprogrami.DersProgrami,
    dersdefteri kayıtları, sınav salon/gözetmen planı) sınıf/şube bilgisini kaybeder
    (yaşandı — bkz. commit geçmişi). Bunun yerine mevcut (sinif, sube) çiftleri PK'ları
    korunarak yerinde bırakılır; içe aktarılan listede artık bulunmayanlar silinmez,
    var olan 'kapalı şube' kavramıyla (bkz. senesonu/services.py) pasife alınır.

    Açık/kapalı durumu artık SinifSube üzerinde tekil bir bayrak değil, yıla göre
    değişebilen SinifSubeYil kayıtlarıdır (bkz. commit geçmişi — aynı şube bir yıl
    açık, ertesi yıl kapalı olabilir). Bu içe aktarma formunda ayrı bir yıl seçimi
    olmadığından (bkz. SinifSubeImportForm), açılan/kapatılan durum AKTİF eğitim-
    öğretim yılına yazılır; aktif yıl tanımlı değilse (OkulBilgi kurulmamışsa) açık/
    kapalı durumu güncellenmez — yalnızca eksik sınıf/şube kayıtları eklenir.
    """
    from okul.utils import get_aktif_egitim_yili

    mevcut = {(ss.sinif, ss.sube): ss for ss in SinifSube.objects.all()}
    yeni_kume = {
        (sinif, sube) for sinif, subeler in sinif_bilgileri.items() for sube in subeler
    }

    eklenecekler = [
        SinifSube(sinif=sinif, sube=sube)
        for (sinif, sube) in yeni_kume
        if (sinif, sube) not in mevcut
    ]
    if eklenecekler:
        SinifSube.objects.bulk_create(eklenecekler, ignore_conflicts=True)

    aktif_yil = get_aktif_egitim_yili()
    if aktif_yil is None:
        return

    # Eklenen yeni kayıtlar da dahil, güncel şube listesini tazele.
    mevcut = {(ss.sinif, ss.sube): ss for ss in SinifSube.objects.all()}

    kapatilacaklar = [ss for key, ss in mevcut.items() if key not in yeni_kume]
    for ss in kapatilacaklar:
        SinifSubeYil.objects.update_or_create(
            sinif_sube=ss, egitim_yili=aktif_yil, defaults={"acik": False}
        )

    acilacaklar = [ss for key, ss in mevcut.items() if key in yeni_kume]
    for ss in acilacaklar:
        SinifSubeYil.objects.update_or_create(
            sinif_sube=ss, egitim_yili=aktif_yil, defaults={"acik": True}
        )
