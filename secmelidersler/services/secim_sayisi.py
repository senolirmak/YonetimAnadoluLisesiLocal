"""Bir öğrencinin aynı seçmeli dersi (SecmeliDersHavuzu eşleşmesi üzerinden) mezun
olana kadar en fazla kaç kez seçebileceğini denetler. `SecmeliDersHavuzu.secimsayisi`
alanı bu üst sınırı taşır (varsayılan 1).

Eşleştirme `normalize_ders_adi()` ile YAPILIR (saat eki temizlenerek) — havuzdaki adlar
hiç saat eki taşımazken (bkz. "PEYGAMBERİMİZİN HAYATI"), grup içindeki `SecmeliDers.
ders_adi` çoğunlukla taşır ("PEYGAMBERİMİZİN HAYATI (4)"); `secmeli_grup_ders_listesi`
gibi bazı ekranlarda kullanılan BİREBİR ad eşleştirmesi burada YETERSİZ kalır — saat
ekli dersler hiç eşleşmez ve kontrol sessizce atlanır (yaşandı: bkz. commit geçmişi).

Bu modül HİÇBİR KAYDI DEĞİŞTİRMEZ — yalnızca uyarı metni üretir; çağıran taraf
(form/view) bunu engelleyici bir hataya değil, bilgilendirici bir mesaja çevirir
(bkz. commit geçmişi: kullanıcı açıkça "uyarı", "engel" değil dedi).
"""
from collections import Counter

from ..models import normalize_ders_adi


def secim_sayisi_asim_uyarilari(ogrenci, secimler, haric_egitim_yili=None):
    """`secimler`: [(SecmeliDers, saat), ...] — henüz KAYDEDİLMEMİŞ yeni seçim listesi.

    Öğrencinin bu çağrıdaki `secimler` DIŞINDAKİ (yani `haric_egitim_yili`e ait olanlar
    hariç — o yılın eski kayıtları zaten silinip bu `secimler`le değiştirilecek, ikisini
    birlikte saymak her kaydetmede yanlış uyarı üretir) geçmiş seçimleriyle, şimdi
    seçilmek istenenlerin toplamını `SecmeliDersHavuzu.secimsayisi` ile karşılaştırır.

    Sınıf tekrarı yapılan bir yıl varsa (bkz. `OgrenciSinifTekrari` — OneToOne olduğundan
    yalnızca en güncel tekrar yılı bilinir) o yıla ait seçimler de sayıma dahil edilmez;
    aynı seviyeyi ikinci kez okurken aynı dersi tekrar seçmek yeni bir seçim sayılmaz.

    Döndürdüğü liste boşsa sorun yok demektir.
    """
    from ogrencidersleri.models import OgrenciSecmeliDers

    from ..models import OgrenciSinifTekrari, SecmeliDersHavuzu

    if not ogrenci or not secimler:
        return []

    havuz_map = {normalize_ders_adi(h.ders_adi): h for h in SecmeliDersHavuzu.objects.all()}

    tekrar_yili_id = (
        OgrenciSinifTekrari.objects.filter(ogrenci=ogrenci)
        .values_list("egitim_yili_id", flat=True)
        .first()
    )

    gecmis_qs = OgrenciSecmeliDers.objects.filter(ogrenci=ogrenci).select_related("ders")
    if haric_egitim_yili:
        gecmis_qs = gecmis_qs.exclude(ders__grup__egitim_yili=haric_egitim_yili)
    if tekrar_yili_id:
        gecmis_qs = gecmis_qs.exclude(ders__grup__egitim_yili_id=tekrar_yili_id)

    gecmis_sayim = Counter(normalize_ders_adi(secim.ders.ders_adi) for secim in gecmis_qs)
    yeni_sayim = Counter(normalize_ders_adi(ders.ders_adi) for ders, _saat in secimler)

    uyarilar = []
    for ders_adi, yeni_adet in yeni_sayim.items():
        havuz = havuz_map.get(ders_adi)
        if not havuz:
            continue
        onceki = gecmis_sayim.get(ders_adi, 0)
        toplam = onceki + yeni_adet
        if toplam > havuz.secimsayisi:
            uyarilar.append(
                f"{ogrenci} — \"{ders_adi}\" dersini bu, {toplam}. seçimi olacak; "
                f"izin verilen en fazla seçim sayısı {havuz.secimsayisi}."
            )
    return uyarilar
