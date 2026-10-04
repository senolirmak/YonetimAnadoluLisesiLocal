"""FET (https://lalescu.ro/liviu/fet/) ders programı yazılımı ile köprü.

İş akışı (elle): `fet_disa_aktar()` aktif ders programından bir `.fet` dosyası üretir →
kullanıcı FET'te açıp kısıtlarını ekler ve programı üretir → FET'in çıktı klasöründeki
`<ad>_data_and_timetable.fet` dosyası `fet_iceri_aktar()` ile YENİ bir uygulama tarihli
ders programı sürümü olarak içeri alınır. İçe alınan sürüm otomatik aktif yapılmaz.

Etkinliklerin türetilmesi
-------------------------
`DersProgrami` satırları (öğretmen, şube, gün, saat, ders) FET etkinliklerine şöyle çevrilir:

1. Her (gün, saat) diliminde öğretmen–şube ilişkisi bir grafik oluşturur; bağlı her bileşen
   tek bir FET etkinliğidir. Böylece paralel seçmeliler (bir şubeye aynı anda birden fazla
   öğretmen) ve birleştirilmiş dersler (bir öğretmen aynı anda birden fazla şubeye) tek
   etkinlikte birden çok <Teacher>/<Students> olarak kalır ve FET onları birlikte yerleştirir.
2. Aynı içeriğe (öğretmen, şube, ders üçlüleri kümesi) sahip bileşenler bir etkinlik
   grubunda toplanır; gün içinde ardışık saatler tek bir alt etkinlik (blok) olur — örn.
   mevcut programda 2+2+2 işlenen 6 saatlik ders FET'e de 2+2+2 olarak gider.
3. Etkinliğin hangi öğretmenin hangi şubeye hangi dersi verdiği bilgisi `Comments` alanına
   JSON olarak yazılır; içe aktarmada satırlar bu bilgiden birebir geri kurulur. FET'te
   elle eklenen (yorumsuz) etkinlikler öğretmen × şube olarak geri alınır.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass, field

KOPRU_ONEKI = "okul-kopru:"
BLOK_DERS_ONEKI = "Blok: "
FET_SURUMU = "6.0.0"


class FetKopruHatasi(Exception):
    """Kullanıcıya gösterilecek, dosya/veri kaynaklı hata."""


# ---------------------------------------------------------------------------
# Dışa aktarma
# ---------------------------------------------------------------------------

def _sube_adi(sinif_sube) -> str:
    return f"{sinif_sube.sinif}/{sinif_sube.sube}"


def _yil_adi(sinif: int) -> str:
    return f"{sinif}. Sınıf"


def _blok_ders_adi(dersler) -> str:
    dersler = sorted(dersler)
    return dersler[0] if len(dersler) == 1 else BLOK_DERS_ONEKI + " + ".join(dersler)


def _ardisik_bloklar(saat_indeksleri: list[int]) -> list[tuple[int, int]]:
    """[1, 2, 4, 5, 6] → [(1, 2), (4, 3)] — (başlangıç indeksi, süre)."""
    bloklar = []
    for i in sorted(saat_indeksleri):
        if bloklar and bloklar[-1][0] + bloklar[-1][1] == i:
            bloklar[-1] = (bloklar[-1][0], bloklar[-1][1] + 1)
        else:
            bloklar.append((i, 1))
    return bloklar


def _alt(ust, etiket, metin=None):
    el = ET.SubElement(ust, etiket)
    if metin is not None:
        el.text = str(metin)
    return el


def _bilesenler(satirlar):
    """Bir dilimdeki satırları öğretmen–şube bağlılığına göre gruplar (union-find)."""
    ebeveyn: dict = {}

    def bul(x):
        while ebeveyn.setdefault(x, x) != x:
            ebeveyn[x] = ebeveyn[ebeveyn[x]]
            x = ebeveyn[x]
        return x

    for d in satirlar:
        a, b = bul(("o", d.ogretmen_id)), bul(("s", d.sinif_sube_id))
        if a != b:
            ebeveyn[a] = b

    gruplar = defaultdict(list)
    for d in satirlar:
        gruplar[bul(("o", d.ogretmen_id))].append(d)
    return list(gruplar.values())


def fet_disa_aktar(dersler=None, kurum_adi: str = "") -> bytes:
    """Aktif (ya da verilen) ders programını FET `.fet` XML'i olarak döner."""
    from dersprogrami.models import GUNLER, DersProgrami
    from okul.models import DersSaatleri

    if dersler is None:
        dersler = DersProgrami.objects.aktif()
    dersler = list(
        dersler.filter(ders_saati__isnull=False, sinif_sube__isnull=False, ders__isnull=False)
        .select_related("ogretmen", "sinif_sube", "ders", "ders_saati")
    )
    if not dersler:
        raise FetKopruHatasi("Dışa aktarılacak ders programı kaydı bulunamadı.")

    dersli_gunler = {d.gun for d in dersler}
    gunler = [(db, tr) for i, (db, tr) in enumerate(GUNLER) if i < 5 or db in dersli_gunler]
    saatler = list(DersSaatleri.objects.order_by("derssaati_no"))
    saat_indeksi = {ds.pk: i for i, ds in enumerate(saatler)}

    # 1) Dilim bazında bileşenler → içerik imzası → kullanıldığı (gün, saat indeksi) listesi
    dilimler = defaultdict(list)
    for d in dersler:
        dilimler[(d.gun, d.ders_saati_id)].append(d)

    imza_dilimleri = defaultdict(list)
    for (gun, saat_id), satirlar in dilimler.items():
        for bilesen in _bilesenler(satirlar):
            imza = tuple(sorted({
                (d.ogretmen.adi_soyadi, _sube_adi(d.sinif_sube), d.ders.ders_adi) for d in bilesen
            }))
            imza_dilimleri[imza].append((gun, saat_indeksi[saat_id]))

    # 2) XML iskeleti
    kok = ET.Element("fet", version=FET_SURUMU)
    _alt(kok, "Institution_Name", kurum_adi or "Okul")
    _alt(kok, "Comments", "Okul Yönetim Sistemi'nden aktarıldı.")

    gun_listesi = _alt(kok, "Days_List")
    _alt(gun_listesi, "Number_of_Days", len(gunler))
    for _, tr in gunler:
        _alt(_alt(gun_listesi, "Day"), "Name", tr)

    saat_listesi = _alt(kok, "Hours_List")
    _alt(saat_listesi, "Number_of_Hours", len(saatler))
    for ds in saatler:
        _alt(_alt(saat_listesi, "Hour"), "Name", ds.ders_adi)

    tum_dersler = sorted({ders for imza in imza_dilimleri for _, _, ders in imza})
    blok_dersleri = sorted({_blok_ders_adi({d for _, _, d in imza}) for imza in imza_dilimleri})
    ders_listesi = _alt(kok, "Subjects_List")
    for ad in sorted(set(tum_dersler) | set(blok_dersleri)):
        el = _alt(ders_listesi, "Subject")
        _alt(el, "Name", ad)
        _alt(el, "Comments", "")
    _alt(kok, "Activity_Tags_List")

    ogretmen_listesi = _alt(kok, "Teachers_List")
    for ad in sorted({o for imza in imza_dilimleri for o, _, _ in imza}):
        el = _alt(ogretmen_listesi, "Teacher")
        _alt(el, "Name", ad)
        _alt(el, "Target_Number_of_Hours", 0)
        _alt(el, "Qualified_Subjects")
        _alt(el, "Comments", "")

    subeler = sorted({d.sinif_sube for d in dersler}, key=lambda s: (s.sinif, s.sube))
    ogrenci_listesi = _alt(kok, "Students_List")
    yil_el = {}
    for s in subeler:
        if s.sinif not in yil_el:
            y = _alt(ogrenci_listesi, "Year")
            _alt(y, "Name", _yil_adi(s.sinif))
            _alt(y, "Number_of_Students", 0)
            _alt(y, "Comments", "")
            yil_el[s.sinif] = y
        g = _alt(yil_el[s.sinif], "Group")
        _alt(g, "Name", _sube_adi(s))
        _alt(g, "Number_of_Students", 0)
        _alt(g, "Comments", "")

    # 3) Etkinlikler
    gun_sirasi = {db: i for i, (db, _) in enumerate(gunler)}
    etkinlik_listesi = _alt(kok, "Activities_List")
    min_gun_gruplari = []
    etkinlik_id = 0
    for imza in sorted(imza_dilimleri):
        gun_saatleri = defaultdict(list)
        for gun, idx in imza_dilimleri[imza]:
            gun_saatleri[gun].append(idx)
        sureler = sorted(
            (sure for gun in sorted(gun_saatleri, key=gun_sirasi.get)
             for _, sure in _ardisik_bloklar(gun_saatleri[gun])),
            reverse=True,
        )
        ogretmenler = sorted({o for o, _, _ in imza})
        ogrenciler = sorted({s for _, s, _ in imza}, key=lambda a: (int(a.split("/")[0]), a))
        ders_adi = _blok_ders_adi({d for _, _, d in imza})
        yorum = KOPRU_ONEKI + json.dumps([list(u) for u in imza], ensure_ascii=False)

        grup_id = etkinlik_id + 1
        grup = []
        for sure in sureler:
            etkinlik_id += 1
            grup.append(etkinlik_id)
            el = _alt(etkinlik_listesi, "Activity")
            for o in ogretmenler:
                _alt(el, "Teacher", o)
            _alt(el, "Subject", ders_adi)
            for s in ogrenciler:
                _alt(el, "Students", s)
            _alt(el, "Duration", sure)
            _alt(el, "Total_Duration", sum(sureler))
            _alt(el, "Id", etkinlik_id)
            _alt(el, "Activity_Group_Id", grup_id if len(sureler) > 1 else 0)
            _alt(el, "Active", "true")
            _alt(el, "Comments", yorum)
        if 1 < len(grup) <= len(gunler):
            min_gun_gruplari.append(grup)

    _alt(kok, "Buildings_List")
    _alt(kok, "Rooms_List")

    zaman = _alt(kok, "Time_Constraints_List")
    temel = _alt(zaman, "ConstraintBasicCompulsoryTime")
    _alt(temel, "Weight_Percentage", 100)
    _alt(temel, "Active", "true")
    _alt(temel, "Comments", "")
    # FET arayüzünün bölünmüş etkinliklere varsayılan olarak eklediği kısıt: aynı dersin
    # parçaları farklı günlere dağılsın (%95 — zorunlu değil).
    for grup in min_gun_gruplari:
        k = _alt(zaman, "ConstraintMinDaysBetweenActivities")
        _alt(k, "Weight_Percentage", 95)
        _alt(k, "Consecutive_If_Same_Day", "true")
        _alt(k, "Number_of_Activities", len(grup))
        for i in grup:
            _alt(k, "Activity_Id", i)
        _alt(k, "MinDays", 1)
        _alt(k, "Active", "true")
        _alt(k, "Comments", "")

    mekan = _alt(kok, "Space_Constraints_List")
    temel = _alt(mekan, "ConstraintBasicCompulsorySpace")
    _alt(temel, "Weight_Percentage", 100)
    _alt(temel, "Active", "true")
    _alt(temel, "Comments", "")

    ET.indent(kok, space="\t")
    return b'<?xml version="1.0" encoding="UTF-8"?>\n\n' + ET.tostring(kok, encoding="utf-8")


# ---------------------------------------------------------------------------
# İçe aktarma
# ---------------------------------------------------------------------------

@dataclass
class FetSatiri:
    ogretmen: str
    sube: str
    ders: str
    gun: str  # DB değeri (Monday...)
    saat_no: int  # DersSaatleri.derssaati_no


@dataclass
class FetOkumaSonucu:
    satirlar: list[FetSatiri] = field(default_factory=list)
    uyarilar: list[str] = field(default_factory=list)


def _metin(el, etiket, varsayilan=""):
    alt = el.find(etiket)
    return (alt.text or "").strip() if alt is not None and alt.text else varsayilan


def fet_sonuc_oku(icerik: bytes) -> FetOkumaSonucu:
    """FET'in `<ad>_data_and_timetable.fet` çıktısını okuyup ders programı satırlarına çevirir.
    Veritabanına yazmaz."""
    from dersprogrami.models import GUNLER
    from okul.models import DersSaatleri

    try:
        kok = ET.fromstring(icerik)
    except ET.ParseError as e:
        raise FetKopruHatasi(f"Dosya okunamadı (geçerli bir FET XML dosyası değil): {e}") from e
    if kok.tag != "fet":
        raise FetKopruHatasi("Dosya bir FET (.fet) dosyası değil.")

    sonuc = FetOkumaSonucu()
    gun_tr_db = {tr: db for db, tr in GUNLER}
    gunler = [_metin(d, "Name") for d in kok.findall("Days_List/Day")]
    bilinmeyen_gun = [g for g in gunler if g not in gun_tr_db]
    if bilinmeyen_gun:
        raise FetKopruHatasi(f"Tanınmayan gün adları: {', '.join(bilinmeyen_gun)}")

    saat_no = {ds.ders_adi: ds.derssaati_no for ds in DersSaatleri.objects.all()}
    saatler = [_metin(h, "Name") for h in kok.findall("Hours_List/Hour")]
    bilinmeyen_saat = [s for s in saatler if s not in saat_no]
    if bilinmeyen_saat:
        raise FetKopruHatasi(
            f"Tanınmayan ders saati adları: {', '.join(bilinmeyen_saat)} — FET'te saat adlarını "
            "değiştirmeyin ya da Okul → Ders Saatleri tanımlarını kontrol edin."
        )

    # Yıl adı → altındaki şubeler (FET'te bir etkinliğe tüm sınıf seviyesi atanmış olabilir)
    yil_subeleri = {
        _metin(y, "Name"): [_metin(g, "Name") for g in y.findall("Group")]
        for y in kok.findall("Students_List/Year")
    }

    # Etkinlik Id → (gün, saat) — FET sonuç dosyasında her yerleştirilmiş etkinlik için
    # %100 ağırlıklı bir başlangıç zamanı kısıtı yazar.
    zamanlar = {}
    for k in kok.findall("Time_Constraints_List/ConstraintActivityPreferredStartingTime"):
        if _metin(k, "Active", "true") != "true" or _metin(k, "Weight_Percentage") not in ("100", "100.0"):
            continue
        zamanlar[_metin(k, "Activity_Id")] = (_metin(k, "Preferred_Day"), _metin(k, "Preferred_Hour"))

    etkinlikler = [e for e in kok.findall("Activities_List/Activity") if _metin(e, "Active", "true") == "true"]
    if etkinlikler and not zamanlar:
        raise FetKopruHatasi(
            "Dosyada yerleştirilmiş bir program yok. FET'te programı ürettikten sonra çıktı "
            "klasöründeki '..._data_and_timetable.fet' dosyasını yükleyin."
        )

    for e in etkinlikler:
        eid = _metin(e, "Id")
        if eid not in zamanlar:
            sonuc.uyarilar.append(f"Etkinlik {eid} yerleştirilmemiş, atlandı.")
            continue
        gun_tr, saat_adi = zamanlar[eid]
        if gun_tr not in gun_tr_db or saat_adi not in saatler:
            sonuc.uyarilar.append(f"Etkinlik {eid}: geçersiz gün/saat ({gun_tr} {saat_adi}), atlandı.")
            continue
        sure = int(_metin(e, "Duration", "1") or 1)
        bas = saatler.index(saat_adi)
        if bas + sure > len(saatler):
            sonuc.uyarilar.append(f"Etkinlik {eid}: gün sonunu aşıyor, atlandı.")
            continue

        yorum = _metin(e, "Comments")
        if yorum.startswith(KOPRU_ONEKI):
            uclular = [tuple(u) for u in json.loads(yorum[len(KOPRU_ONEKI):])]
        else:
            ders = _metin(e, "Subject")
            if ders.startswith(BLOK_DERS_ONEKI):
                sonuc.uyarilar.append(
                    f"Etkinlik {eid}: '{ders}' blok etkinliğinin köprü bilgisi silinmiş, atlandı."
                )
                continue
            ogretmenler = [t.text.strip() for t in e.findall("Teacher") if t.text]
            subeler = []
            for s in (s.text.strip() for s in e.findall("Students") if s.text):
                subeler.extend(yil_subeleri.get(s, [s]))
            if not ogretmenler:
                sonuc.uyarilar.append(f"Etkinlik {eid} ({ders}): öğretmeni yok, atlandı.")
                continue
            uclular = [(o, s, ders) for o in ogretmenler for s in subeler]

        for i in range(sure):
            no = saat_no[saatler[bas + i]]
            for ogretmen, sube, ders in uclular:
                sonuc.satirlar.append(FetSatiri(ogretmen, sube, ders, gun_tr_db[gun_tr], no))
    return sonuc


def fet_iceri_aktar(dosya, uygulama_tarihi, kullanici=None) -> dict:
    """FET sonucunu `uygulama_tarihi` ile yeni bir ders programı sürümü olarak kaydeder.

    Mevcut sürümlere dokunmaz ve yeni sürümü aktif YAPMAZ (bkz. `programi_aktif_yap`).
    O tarihte zaten program varsa reddeder — sürümler karışmasın.
    """
    from django.db import transaction

    from dersprogrami.models import DersProgrami
    from okul.models import DersHavuzu, DersSaatleri, Personel, SinifSube, VeriAktarimGecmisi
    from okul.utils import donem_tarihe_gore, get_aktif_donem, get_aktif_egitim_yili

    if DersProgrami.objects.filter(uygulama_tarihi=uygulama_tarihi).exists():
        raise FetKopruHatasi(
            f"{uygulama_tarihi:%d.%m.%Y} tarihli bir ders programı zaten var. "
            "FET sonucu için farklı bir uygulama tarihi seçin."
        )

    okunan = fet_sonuc_oku(dosya.read())
    uyarilar = list(okunan.uyarilar)

    personel = {p.adi_soyadi: p for p in Personel.objects.all()}
    subeler = {_sube_adi(s): s for s in SinifSube.objects.all()}
    saatler = {ds.derssaati_no: ds for ds in DersSaatleri.objects.all()}
    havuz = {d.ders_adi: d for d in DersHavuzu.objects.all()}

    donem = donem_tarihe_gore(uygulama_tarihi)
    egitim_yili = donem.egitim_yili if donem else get_aktif_egitim_yili()
    donem = donem or get_aktif_donem()

    eksik = defaultdict(set)
    nesneler = []
    gorulen = set()
    for s in okunan.satirlar:
        anahtar = (s.ogretmen, s.sube, s.ders, s.gun, s.saat_no)
        if anahtar in gorulen:
            continue
        gorulen.add(anahtar)
        if s.ogretmen not in personel:
            eksik["öğretmen"].add(s.ogretmen)
            continue
        if s.sube not in subeler:
            eksik["şube"].add(s.sube)
            continue
        if s.ders not in havuz:
            havuz[s.ders], _ = DersHavuzu.objects.get_or_create(ders_adi=s.ders)
        nesneler.append(DersProgrami(
            ogretmen=personel[s.ogretmen],
            sinif_sube=subeler[s.sube],
            ders=havuz[s.ders],
            gun=s.gun,
            ders_saati=saatler[s.saat_no],
            uygulama_tarihi=uygulama_tarihi,
            egitim_yili=egitim_yili,
            donem=donem,
        ))
    for tur, adlar in eksik.items():
        uyarilar.append(f"Sistemde bulunmayan {tur} atlandı: {', '.join(sorted(adlar))}")

    if not nesneler:
        raise FetKopruHatasi("Dosyadan içe aktarılabilecek ders bulunamadı. " + " ".join(uyarilar))

    with transaction.atomic():
        DersProgrami.objects.bulk_create(nesneler)
        VeriAktarimGecmisi.objects.create(
            dosya_turu="ders_programi",
            dosya_adi=getattr(dosya, "name", "fet_sonuc.fet"),
            uygulama_tarihi=uygulama_tarihi,
            kullanici=kullanici,
            kayit_sayisi=len(nesneler),
            hata_sayisi=0,
            durum="kismi" if uyarilar else "basarili",
            notlar="\n".join(["FET'ten içe aktarıldı (aktif yapılmadı)."] + uyarilar),
        )
    return {"eklenen": len(nesneler), "uyarilar": uyarilar, "uygulama_tarihi": uygulama_tarihi}


def programi_aktif_yap(uygulama_tarihi) -> None:
    """Verilen tarihli (arşivlenmemiş) program sürümünü aktif ders programı yapar.

    `okul.utils.set_aktif_tarih`in aksine daha eski bir tarihe de geçebilir — bu bilinçli
    bir kullanıcı onayıyla çağrılır (FET sonucunu gözden geçirip "aktif yap" demek)."""
    from dersprogrami.models import DersProgrami
    from okul.models import AktifVeriKonfigurasyonu

    if not DersProgrami.objects.filter(uygulama_tarihi=uygulama_tarihi, arsivlendi=False).exists():
        raise FetKopruHatasi(f"{uygulama_tarihi:%d.%m.%Y} tarihli (arşivlenmemiş) bir program yok.")
    AktifVeriKonfigurasyonu.objects.update_or_create(
        veri_turu="ders_programi", defaults={"uygulama_tarihi": uygulama_tarihi}
    )
