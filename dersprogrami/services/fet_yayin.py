"""FET bilgisayarından gelen ders programı + nöbet paketleri (gelen kutusu).

FET okul sunucusunda çalışmaz; programlar bir PC'de (timetableokul projesi) üretilir. Kabul
edilen çözüm oradan bu sunucuya bir **paket** olarak gönderilir (PC'nin sabit IP'si olmadığı
için bağlantıyı PC başlatır). Paket önce `FetYayini` olarak bekler; hiçbir veriyi değiştirmez.
Bir üst yönetici paketi inceleyip "İçeri al" dediğinde:

- ders programı mevcut FET köprüsüyle (`fet_kopru.fet_iceri_aktar`) yeni bir uygulama tarihli
  sürüm olarak,
- nöbet listesi aynı uygulama tarihiyle yeni `NobetGorevi` kayıtları olarak

yazılır. İkisi de aktif yapılmaz; "Aktif yap" ayrı bir onaydır (`aktif_yap`).

Paket biçimi (zip):
    manifest.json  {"surum": 1, "cozum": str, "uygulama_tarihi": "YYYY-MM-DD",
                    "okul_adi": str, "egitim_yili": str, "donem": str, "kaynak": str}
    program.fet    FET çıktısındaki <ad>_data_and_timetable.fet (okul-kopru yorumlarıyla)
    nobet.json     [{"gun": "Pazartesi", "ogretmen": "AD SOYAD", "yer": "NÖBET YERİ"}, ...]
"""

from __future__ import annotations

import datetime
import hashlib
import hmac
import io
import json
import zipfile
from collections import Counter

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .fet_kopru import FetKopruHatasi, fet_iceri_aktar, fet_sonuc_oku, programi_aktif_yap

PAKET_SURUMU = 1
EN_BUYUK_PAKET = 20 * 1024 * 1024
GUN_KODLARI = {"Pazartesi": "Monday", "Salı": "Tuesday", "Çarşamba": "Wednesday",
               "Perşembe": "Thursday", "Cuma": "Friday"}


class FetYayinHatasi(Exception):
    """Kullanıcıya / gönderen PC'ye gösterilecek paket hatası."""


def anahtar_dogru_mu(anahtar) -> bool:
    beklenen = getattr(settings, "FET_YAYIN_ANAHTARI", "")
    if not beklenen or not isinstance(anahtar, str) or not anahtar:
        return False
    return hmac.compare_digest(anahtar.encode(), beklenen.encode())


# ---------------------------------------------------------------------------
# Paket okuma ve kaydetme
# ---------------------------------------------------------------------------

def paket_oku(veri: bytes) -> dict:
    """Paketi açar ve doğrular. Veritabanına dokunmaz."""
    if len(veri) > EN_BUYUK_PAKET:
        raise FetYayinHatasi("Paket çok büyük.")
    try:
        zf = zipfile.ZipFile(io.BytesIO(veri))
        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
        fet = zf.read("program.fet")
        nobet = json.loads(zf.read("nobet.json").decode("utf-8"))
    except (zipfile.BadZipFile, KeyError, ValueError, UnicodeDecodeError) as e:
        raise FetYayinHatasi(f"Paket okunamadı (manifest.json, program.fet, nobet.json gerekli): {e}") from None

    if not isinstance(manifest, dict) or manifest.get("surum") != PAKET_SURUMU:
        raise FetYayinHatasi(f"Desteklenmeyen paket sürümü: {manifest.get('surum') if isinstance(manifest, dict) else '?'}")
    try:
        tarih = datetime.date.fromisoformat(str(manifest.get("uygulama_tarihi", "")))
    except ValueError:
        raise FetYayinHatasi("manifest.json: uygulama_tarihi YYYY-AA-GG biçiminde olmalı.") from None
    cozum = str(manifest.get("cozum") or "").strip()
    if not cozum:
        raise FetYayinHatasi("manifest.json: çözüm adı eksik.")

    if not isinstance(nobet, list):
        raise FetYayinHatasi("nobet.json bir liste olmalı.")
    nobetler = []
    for i, n in enumerate(nobet, 1):
        if not isinstance(n, dict):
            raise FetYayinHatasi(f"nobet.json {i}. kayıt geçersiz.")
        gun, ogretmen, yer = (str(n.get(k) or "").strip() for k in ("gun", "ogretmen", "yer"))
        if gun not in GUN_KODLARI or not ogretmen:
            raise FetYayinHatasi(f"nobet.json {i}. kayıt: gün ya da öğretmen geçersiz ({gun!r}, {ogretmen!r}).")
        nobetler.append({"gun": gun, "ogretmen": " ".join(ogretmen.split()), "yer": yer})

    try:
        okunan = fet_sonuc_oku(fet)
    except FetKopruHatasi as e:
        raise FetYayinHatasi(f"program.fet okunamadı: {e}") from None
    if not okunan.satirlar:
        raise FetYayinHatasi("program.fet içinde yerleşmiş ders yok.")

    sube_saatleri = Counter(s.sube for s in {(s.sube, s.gun, s.saat_no): s for s in okunan.satirlar}.values())
    ozet = {
        "satir": len(okunan.satirlar),
        "ogretmen": len({s.ogretmen for s in okunan.satirlar}),
        "sube": len(sube_saatleri),
        "sube_saat_en_az": min(sube_saatleri.values()),
        "sube_saat_en_cok": max(sube_saatleri.values()),
        "nobet": len(nobetler),
        "uyarilar": list(okunan.uyarilar),
    }
    imza = hashlib.sha256(
        fet + json.dumps(nobetler, ensure_ascii=False, sort_keys=True).encode() + tarih.isoformat().encode()
    ).hexdigest()
    return {
        "cozum": cozum[:300],
        "uygulama_tarihi": tarih,
        "okul_adi": str(manifest.get("okul_adi") or "")[:200],
        "egitim_yili": str(manifest.get("egitim_yili") or "")[:9],
        "donem": str(manifest.get("donem") or "")[:20],
        "kaynak": str(manifest.get("kaynak") or "")[:100],
        "fet": fet,
        "nobet": nobetler,
        "ozet": ozet,
        "imza": imza,
    }


def paket_kaydet(veri: bytes):
    """Paketi gelen kutusuna koyar. Aynı içerik daha önce geldiyse onu döndürür.

    Döner: (FetYayini, yeni_mi)."""
    from dersprogrami.models import FetYayini

    p = paket_oku(veri)
    mevcut = FetYayini.objects.filter(imza=p["imza"]).first()
    if mevcut:
        return mevcut, False
    yayin = FetYayini.objects.create(
        kaynak=p["kaynak"], cozum=p["cozum"], uygulama_tarihi=p["uygulama_tarihi"],
        okul_adi=p["okul_adi"], egitim_yili=p["egitim_yili"], donem=p["donem"],
        fet_icerik=p["fet"], nobet=p["nobet"], ozet=p["ozet"], imza=p["imza"],
    )
    return yayin, True


# ---------------------------------------------------------------------------
# Ön kontrol, içeri alma, aktif yapma
# ---------------------------------------------------------------------------

def on_kontrol(yayin) -> dict:
    """İçeri almadan önce sistemle eşleşmeyi denetler (yalnız okur)."""
    from dersprogrami.models import DersProgrami
    from nobet.models import NobetGorevi, NobetYerleri
    from okul.models import DersSaatleri, Personel, SinifSube

    okunan = fet_sonuc_oku(bytes(yayin.fet_icerik))
    personel = set(Personel.objects.values_list("adi_soyadi", flat=True))
    subeler = {f"{s.sinif}/{s.sube}" for s in SinifSube.objects.all()}
    saatler = set(DersSaatleri.objects.values_list("derssaati_no", flat=True))
    yerler = set(NobetYerleri.objects.values_list("ad", flat=True))

    engeller, uyarilar = [], list(okunan.uyarilar)
    if DersProgrami.objects.filter(uygulama_tarihi=yayin.uygulama_tarihi).exists():
        engeller.append(f"{yayin.uygulama_tarihi:%d.%m.%Y} tarihli bir ders programı zaten var.")
    if NobetGorevi.objects.filter(uygulama_tarihi=yayin.uygulama_tarihi).exists():
        engeller.append(f"{yayin.uygulama_tarihi:%d.%m.%Y} tarihli bir nöbet listesi zaten var.")
    eksik_saat = sorted({s.saat_no for s in okunan.satirlar} - saatler)
    if eksik_saat:
        engeller.append(f"Sistemde tanımlı olmayan ders saatleri: {eksik_saat}")

    return {
        "engeller": engeller,
        "uyarilar": uyarilar,
        "eksik_ogretmen": sorted({s.ogretmen for s in okunan.satirlar} - personel),
        "eksik_sube": sorted({s.sube for s in okunan.satirlar} - subeler),
        "eksik_nobetci": sorted({n["ogretmen"] for n in yayin.nobet} - personel),
        "yeni_nobet_yeri": sorted({n["yer"] for n in yayin.nobet if n["yer"]} - yerler),
    }


def _nobet_ice_al(nobetler, uygulama_tarihi, kullanici=None) -> dict:
    from nobet.models import NobetGorevi, NobetOgretmen, NobetYerleri
    from okul.models import Personel, VeriAktarimGecmisi
    from okul.utils import donem_tarihe_gore, get_aktif_donem, get_aktif_egitim_yili

    if NobetGorevi.objects.filter(uygulama_tarihi=uygulama_tarihi).exists():
        raise FetYayinHatasi(f"{uygulama_tarihi:%d.%m.%Y} tarihli bir nöbet listesi zaten var.")
    donem = donem_tarihe_gore(uygulama_tarihi)
    egitim_yili = donem.egitim_yili if donem else get_aktif_egitim_yili()
    donem = donem or get_aktif_donem()

    personel = {p.adi_soyadi: p for p in Personel.objects.all()}
    eksik, nesneler = set(), []
    for n in nobetler:
        p = personel.get(n["ogretmen"])
        if p is None:
            eksik.add(n["ogretmen"])
            continue
        ogretmen, _ = NobetOgretmen.objects.get_or_create(personel=p)
        yer = NobetYerleri.objects.get_or_create(ad=n["yer"])[0] if n["yer"] else None
        nesneler.append(NobetGorevi(
            nobet_gun=GUN_KODLARI[n["gun"]], nobet_yeri=yer, ogretmen=ogretmen,
            uygulama_tarihi=uygulama_tarihi, egitim_yili=egitim_yili, donem=donem,
        ))
    uyarilar = [f"Sistemde bulunmayan nöbetçi atlandı: {', '.join(sorted(eksik))}"] if eksik else []
    NobetGorevi.objects.bulk_create(nesneler)
    VeriAktarimGecmisi.objects.create(
        dosya_turu="nobet_listesi", dosya_adi="fet_yayini/nobet.json", uygulama_tarihi=uygulama_tarihi,
        kullanici=kullanici, kayit_sayisi=len(nesneler), hata_sayisi=len(eksik),
        durum="kismi" if uyarilar else "basarili",
        notlar="\n".join(["FET yayınından içe aktarıldı (aktif yapılmadı)."] + uyarilar),
    )
    return {"eklenen": len(nesneler), "uyarilar": uyarilar}


def ice_al(yayin, kullanici=None) -> dict:
    """Ders programını ve nöbet listesini `uygulama_tarihi` ile yeni sürüm olarak yazar."""
    from dersprogrami.models import FetYayini

    if yayin.durum != FetYayini.DURUM_BEKLIYOR:
        raise FetYayinHatasi("Bu paket zaten işlenmiş.")
    dosya = io.BytesIO(bytes(yayin.fet_icerik))
    dosya.name = f"{yayin.cozum.split('/')[0]}.fet"
    try:
        with transaction.atomic():
            dp = fet_iceri_aktar(dosya, yayin.uygulama_tarihi, kullanici=kullanici)
            nb = _nobet_ice_al(yayin.nobet, yayin.uygulama_tarihi, kullanici=kullanici)
            yayin.durum = FetYayini.DURUM_ICE_ALINDI
            yayin.isleyen = kullanici
            yayin.islem_zamani = timezone.now()
            yayin.notlar = "\n".join(dp["uyarilar"] + nb["uyarilar"])
            yayin.save(update_fields=["durum", "isleyen", "islem_zamani", "notlar"])
    except FetKopruHatasi as e:
        raise FetYayinHatasi(str(e)) from None
    return {"ders": dp["eklenen"], "nobet": nb["eklenen"], "uyarilar": dp["uyarilar"] + nb["uyarilar"]}


def aktif_yap(yayin) -> None:
    """İçeri alınmış paketin ders programını ve nöbet listesini aktif yapar."""
    from dersprogrami.models import FetYayini
    from okul.models import AktifVeriKonfigurasyonu

    if yayin.durum != FetYayini.DURUM_ICE_ALINDI:
        raise FetYayinHatasi("Önce paketi içeri alın.")
    try:
        with transaction.atomic():
            programi_aktif_yap(yayin.uygulama_tarihi)
            AktifVeriKonfigurasyonu.objects.update_or_create(
                veri_turu="nobet_listesi", defaults={"uygulama_tarihi": yayin.uygulama_tarihi}
            )
    except FetKopruHatasi as e:
        raise FetYayinHatasi(str(e)) from None


def reddet(yayin, kullanici=None) -> None:
    from dersprogrami.models import FetYayini

    if yayin.durum != FetYayini.DURUM_BEKLIYOR:
        raise FetYayinHatasi("Yalnızca bekleyen paket reddedilebilir.")
    yayin.durum = FetYayini.DURUM_REDDEDILDI
    yayin.isleyen = kullanici
    yayin.islem_zamani = timezone.now()
    yayin.save(update_fields=["durum", "isleyen", "islem_zamani"])
