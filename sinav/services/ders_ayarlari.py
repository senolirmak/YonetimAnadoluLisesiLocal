from sinav.models import DersAyarlariJSON

_VARSAYILAN_SINAV_YAPILMAYACAK = [
    "GÖRSEL SANATLAR/MÜZİK",
    "BEDEN EĞİTİMİ VE SPOR/GÖRSEL SANATLAR/MÜZİK",
    "BEDEN EĞİTİMİ VE SPOR",
    "SEÇMELİ SANAT EĞİTİMİ",
    "REHBERLİK VE YÖNLENDİRME",
    "SEÇMELİ SPOR EĞİTİMİ",
    "SEÇMELİ HEDEF TEMELLİ DESTEK EĞİTİMİ",
    "SEÇMELİ YABANCI DİL",
]

_VARSAYILAN_CIFT_OTURUMLU = [
    "SEÇMELİ İKİNCİ YABANCI DİL",
    "SEÇMELİ TÜRK DİLİ VE EDEBİYATI",
    "TÜRK DİLİ VE EDEBİYATI",
    "YABANCI DİL",
]

_VARSAYILAN_CATISMA_GRUBU = {
    "grup_adi": "Fen-Matematik Grubu",
    "dersler":  "BİYOLOJİ,FİZİK,KİMYA,MATEMATİK,"
                "SEÇMELİ BİYOLOJİ,SEÇMELİ FİZİK,SEÇMELİ KİMYA,SEÇMELİ MATEMATİK",
}


def get_ayarlar(sinav) -> dict:
    """Aktif sinava ait ders ayarlari JSON verisini döndürür."""
    if sinav is None:
        return {}
    obj, _ = DersAyarlariJSON.objects.get_or_create(sinav=sinav)
    return dict(obj.veri) if obj.veri else {}


def save_ayarlar(sinav, veri: dict) -> None:
    """Ders ayarlari JSON verisini kaydeder."""
    obj, _ = DersAyarlariJSON.objects.get_or_create(sinav=sinav)
    obj.veri = veri
    obj.save()


def mutate_ayar_listesi(aktif, key: str, mutate_fn):
    """`key` altındaki listeyi okuyup `mutate_fn(liste)`'e verir. `mutate_fn`
    listeyi yerinde değiştirir (append/pop/slice-assign) ve bir sonuç döner:
    sonuç `None` ise (ör. verilen index bulunamadı, ya da kayıt zaten var)
    hiçbir şey kaydedilmez; aksi halde değişiklik DersAyarlariJSON'a yazılır.
    Dönen değer view'a olduğu gibi geçirilir (mesaj oluşturmak için)."""
    veri = get_ayarlar(aktif)
    liste = veri.get(key, [])
    sonuc = mutate_fn(liste)
    if sonuc is not None:
        veri[key] = liste
        save_ayarlar(aktif, veri)
    return sonuc


def parse_ders_ayarlari_post(post_data) -> dict:
    """POST verisindeki JSON alanlarını (sabit_json/catisma_json/esleme_json/
    ortak_seviyeler_json) ayrıştırıp mevcut `veri` sözlüğüne uygulanacak
    güncellemeleri döner. Geçersiz JSON'lar ya da boş alanlar sessizce
    atlanır (mevcut davranış korunur)."""
    import json

    guncellemeler = {}
    for key, field in [("sabit_sinavlar", "sabit_json"),
                        ("catisma_gruplari", "catisma_json"),
                        ("ayni_slot_esleme", "esleme_json")]:
        raw = post_data.get(field, "").strip()
        if raw:
            try:
                guncellemeler[key] = json.loads(raw)
            except Exception:
                pass

    raw_seviyeler = post_data.get("ortak_seviyeler_json", "").strip()
    if raw_seviyeler:
        try:
            parsed = json.loads(raw_seviyeler)
            seviyeler = sorted({int(s) for s in parsed if str(s).isdigit() or isinstance(s, int)})
            if seviyeler:
                guncellemeler["ortak_sinav_seviyeleri"] = seviyeler
        except Exception:
            pass

    return guncellemeler


TUM_SEVIYELER = (9, 10, 11, 12)


class SabitSinavCakismasi(ValueError):
    """Aynı ders için seviyeleri örtüşen iki sabit sınav tanımlanamaz."""


def sabit_sinav_ekle_veya_guncelle(liste: list, yeni: dict) -> bool:
    """`yeni` sabit sınavı listeye ekler; True → mevcut kayıt güncellendi.

    Aynı ders, sınıf seviyeleri örtüşmediği sürece birden çok kez eklenebilir
    (örn. 10. sınıf TDE bir gün, 9/11/12 TDE başka gün). Seviyeleri birebir aynı
    olan kayıt güncellenir; kısmen örtüşen kayıt `SabitSinavCakismasi` fırlatır.
    Boş seviye listesi "tüm sınıflar" demektir.
    """
    yeni_sev = set(yeni.get("seviyeler") or TUM_SEVIYELER)
    for i, ss in enumerate(liste):
        if ss["ders_adi"] != yeni["ders_adi"]:
            continue
        mevcut_sev = set(ss.get("seviyeler") or TUM_SEVIYELER)
        if mevcut_sev == yeni_sev:
            liste[i] = yeni
            return True
        ortak = mevcut_sev & yeni_sev
        if ortak:
            sev = ", ".join(str(s) for s in sorted(ortak))
            raise SabitSinavCakismasi(
                f'"{yeni["ders_adi"]}" için {sev}. sınıf seviyesinde zaten bir sabit sınav var '
                f'({ss["tarih"]} {ss["saat"]}). Önce onu silin ya da farklı seviyeler seçin.'
            )
    liste.append(yeni)
    return False
