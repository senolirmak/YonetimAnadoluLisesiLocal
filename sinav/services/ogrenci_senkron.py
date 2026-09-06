"""Bir sınavın `SinavOgrenci` anlık görüntüsüne, ilk üretimden SONRA canlı
`ogrenci.Ogrenci`'ye eklenmiş (nakil gelen, yeni kayıt olan) öğrencileri
KATMADAN (ekleme yapmadan) EKLER — var olan hiçbir kayda dokunmaz/değiştirmez.

`ortaksinav_engine.services.oturma.anlik_goruntu_garanti_et` bir sınav için
ilk "Oturma Üret" çalıştığında öğrenci listesini bilinçli olarak DONDURUYOR
(bkz. sinav.models.SinavOgrenci docstring'i — 2025-2026'ya ait bir sınavda
2026-2027'nin yeni öğrencilerinin görünmesi olayı). Bu doğru davranış AMA bir
yan etkisi var: sınav dönemi HÂLÂ DEVAM EDERKEN gelen bir nakil öğrenci artık
otomatik olarak dahil olmuyor. Bu modül o boşluğu, güvenli (yalnızca ekleme
yapan, geçmiş bir sınav için reddeden) bir "senkronize et" adımıyla kapatır.
"""

from __future__ import annotations

from dataclasses import dataclass


class SenkronHatasi(Exception):
    """Senkronizasyon reddedildiğinde (ör. geçmiş bir sınav) kullanıcıya
    gösterilebilir hata için."""


@dataclass
class SenkronSonucu:
    eklenen_ogrenci: list[str]  # "okulno adı soyadı" biçiminde, bilgilendirme için
    eklenen_muaf_sayisi: int


def nakil_ogrenci_senkronize_et(sinav) -> SenkronSonucu:
    """`sinav`ın `SinavOgrenci` anlık görüntüsüne, henüz orada olmayan (canlı
    `Ogrenci`'de var ama snapshot'ta yok) öğrencileri ekler.

    Güvenlik kontrolü: `sinav.egitim_ogretim_yili`, sistemin O ANKİ aktif
    eğitim-öğretim yılıyla eşleşmiyorsa reddedilir — aksi halde bu fonksiyon,
    tam olarak düzeltilen orijinal hatayı (geçmiş bir sınava güncel yılın
    TÜM yeni öğrencilerinin toplu eklenmesi) yeniden üretebilirdi. Bu yüzden
    yalnızca "hâlâ içinde bulunduğumuz" bir sınav için, gerçek birkaç nakil
    öğrenciyi eklemek amacıyla kullanılmalıdır.
    """
    from ogrenci.models import Ogrenci as OgrenciModel
    from ogrenci.models import OgrenciMuaf
    from okul.utils import get_aktif_egitim_yili
    from sinav.models import SinavOgrenci, SinavOgrenciMuaf

    aktif_yil = get_aktif_egitim_yili()
    if aktif_yil is not None and sinav.egitim_ogretim_yili != aktif_yil.egitim_yili:
        raise SenkronHatasi(
            f"'{sinav}' {sinav.egitim_ogretim_yili} eğitim-öğretim yılına ait, ancak "
            f"sistemin aktif eğitim yılı {aktif_yil.egitim_yili} — geçmişte kalmış bir "
            f"sınavın öğrenci listesini güncel kayıtlarla senkronize etmek, o dönemde "
            f"olmayan öğrencilerin karışmasına yol açar, bu yüzden engellendi."
        )

    if not SinavOgrenci.objects.filter(sinav=sinav).exists():
        raise SenkronHatasi(
            f"'{sinav}' için henüz hiç öğrenci anlık görüntüsü alınmamış — önce "
            f"Takvim/Oturma Üret çalıştırın, senkronizasyon ondan sonra anlamlıdır."
        )

    mevcut_okulnolar = set(
        SinavOgrenci.objects.filter(sinav=sinav).values_list("okulno", flat=True)
    )
    yeni_ogrenciler = list(OgrenciModel.objects.exclude(okulno__in=mevcut_okulnolar))

    SinavOgrenci.objects.bulk_create([
        SinavOgrenci(
            sinav=sinav, okulno=o.okulno, adi=o.adi, soyadi=o.soyadi,
            cinsiyet=o.cinsiyet, sinif=o.sinif, sube=o.sube,
            sureksiz_devamsiz=o.sureksiz_devamsiz,
        )
        for o in yeni_ogrenciler
    ], ignore_conflicts=True)

    yeni_okulnolar = {o.okulno for o in yeni_ogrenciler}
    eklenen_muaf = SinavOgrenciMuaf.objects.bulk_create([
        SinavOgrenciMuaf(sinav=sinav, okulno=okulno, ders_adi=ders_adi)
        for okulno, ders_adi in OgrenciMuaf.objects.filter(
            egitim_yili=aktif_yil, ogrenci__okulno__in=yeni_okulnolar,
        ).values_list("ogrenci__okulno", "ders__ders_adi")
    ], ignore_conflicts=True)

    return SenkronSonucu(
        eklenen_ogrenci=[f"{o.okulno} {o.adi} {o.soyadi}" for o in yeni_ogrenciler],
        eklenen_muaf_sayisi=len(eklenen_muaf),
    )
