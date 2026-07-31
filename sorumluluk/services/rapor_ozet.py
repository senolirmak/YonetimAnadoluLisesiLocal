"""Öğretmen görev özeti ve "Sorumluluk Sınavı Görevlerim" sayfaları için hesaplama.

Bu modül yalnızca okuma yapar (rapor amaçlı); veritabanına yazmaz.
"""
from itertools import groupby

from sorumluluk.models import (
    SALON_CHOICES,
    OncekiDonem,
    OncekiDonemGorev,
    SorumluGozetmen,
    SorumluKomisyonUyesi,
    SorumluTakvim,
)
from sorumluluk.services.gorevlendirme_oneri import komisyon_gorev_sayisi

_SALON_LABEL = dict(SALON_CHOICES)
_AYLAR = [
    "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
    "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
]


def _tr_tarih(d):
    return f"{d.day} {_AYLAR[d.month - 1]} {d.year}"


def ogretmen_gorev_ozeti_hesapla(secili_sinav) -> dict:
    """`ogretmen_gorev_ozeti` view'ı için branşa göre gruplu personel görev
    tablosunu ve toplamları hesaplar. `secili_sinav=None` ise sınav bazlı
    sütunlar sıfır kalır, sıralama kümülatif sayılara göre yapılır."""
    from okul.models import Personel

    personel_listesi = list(Personel.objects.select_related("brans").order_by("brans__ad", "adi_soyadi"))
    pid_set = {p.pk for p in personel_listesi}

    # ── Geçmiş dönem toplamları (tüm OncekiDonem kayıtlarının toplamı) ────────
    onceki_kum: dict = {}   # pid → {"komisyon": n, "gozetmen": n}
    for g in OncekiDonemGorev.objects.filter(personel_id__in=pid_set):
        entry = onceki_kum.setdefault(g.personel_id, {"komisyon": 0, "gozetmen": 0})
        entry["komisyon"] += g.komisyon
        entry["gozetmen"] += g.gozetmen

    gecmis_donemler = list(OncekiDonem.objects.all())

    # ── Kümülatif (tüm sınavlar — sistem kayıtları) ───────────────────────────
    sistem_kum = {p.pk: {"komisyon": 0, "gozetmen": 0} for p in personel_listesi}

    kum_komisyon_kayitlar: dict = {}
    for ku in SorumluKomisyonUyesi.objects.all():
        for pid in (ku.uye1_id, ku.uye2_id):
            if pid and pid in pid_set:
                kum_komisyon_kayitlar.setdefault(pid, []).append(
                    (ku.sinav_id, ku.ders_adi, ku.tarih, ku.oturum_no)
                )
    for pid, kayitlar in kum_komisyon_kayitlar.items():
        sistem_kum[pid]["komisyon"] = komisyon_gorev_sayisi(kayitlar)

    for gz in SorumluGozetmen.objects.all():
        if gz.gozetmen_id and gz.gozetmen_id in pid_set:
            sistem_kum[gz.gozetmen_id]["gozetmen"] += 1

    # ── Seçili sınav sayacı ve detayları ──────────────────────────────────────
    sinav_sayac = {p.pk: {"komisyon": 0, "gozetmen": 0} for p in personel_listesi}
    sinav_detaylar: dict = {}

    if secili_sinav:
        takvim_saatler = {
            (t.tarih, t.oturum_no): (t.saat_baslangic, t.saat_bitis)
            for t in SorumluTakvim.objects.filter(sinav=secili_sinav).order_by("tarih", "oturum_no")
        }

        sinav_komisyon_kayitlar: dict = {}
        for ku in SorumluKomisyonUyesi.objects.filter(sinav=secili_sinav):
            saatler = takvim_saatler.get((ku.tarih, ku.oturum_no))
            for pid in (ku.uye1_id, ku.uye2_id):
                if pid and pid in pid_set:
                    sinav_komisyon_kayitlar.setdefault(pid, []).append(
                        (ku.sinav_id, ku.ders_adi, ku.tarih, ku.oturum_no)
                    )
                    sinav_detaylar.setdefault(pid, []).append({
                        "tarih":          ku.tarih,
                        "tarih_str":      _tr_tarih(ku.tarih),
                        "oturum_no":      ku.oturum_no,
                        "saat_baslangic": saatler[0] if saatler else None,
                        "saat_bitis":     saatler[1] if saatler else None,
                        "tur":            "komisyon",
                        "detay":          ku.ders_adi,
                    })

        for pid, kayitlar in sinav_komisyon_kayitlar.items():
            sinav_sayac[pid]["komisyon"] = komisyon_gorev_sayisi(kayitlar)

        for gz in SorumluGozetmen.objects.filter(sinav=secili_sinav).select_related("gozetmen"):
            if gz.gozetmen_id and gz.gozetmen_id in pid_set:
                sinav_sayac[gz.gozetmen_id]["gozetmen"] += 1
                saatler = takvim_saatler.get((gz.tarih, gz.oturum_no))
                sinav_detaylar.setdefault(gz.gozetmen_id, []).append({
                    "tarih":          gz.tarih,
                    "tarih_str":      _tr_tarih(gz.tarih),
                    "oturum_no":      gz.oturum_no,
                    "saat_baslangic": saatler[0] if saatler else None,
                    "saat_bitis":     saatler[1] if saatler else None,
                    "tur":            "gozetmen",
                    "detay":          _SALON_LABEL.get(gz.salon, gz.salon),
                })

    # ── Tablo satırlarını oluştur ve branşa göre grupla ───────────────────────
    def _row(p):
        sys_k = sistem_kum[p.pk]["komisyon"]
        sys_g = sistem_kum[p.pk]["gozetmen"]
        onc   = onceki_kum.get(p.pk, {"komisyon": 0, "gozetmen": 0})
        onc_k = onc["komisyon"]
        onc_g = onc["gozetmen"]
        kum_k = sys_k + onc_k
        kum_g = sys_g + onc_g
        s_k   = sinav_sayac[p.pk]["komisyon"]
        s_g   = sinav_sayac[p.pk]["gozetmen"]
        return {
            "pk":           p.pk,
            "adi_soyadi":   p.adi_soyadi,
            "brans":        p.brans.ad if p.brans else "—",
            "komisyon":     s_k,
            "gozetmen":     s_g,
            "toplam":       s_k + s_g,
            "sys_komisyon": sys_k,
            "sys_gozetmen": sys_g,
            "onc_komisyon": onc_k,
            "onc_gozetmen": onc_g,
            "kum_komisyon": kum_k,
            "kum_gozetmen": kum_g,
            "kum_toplam":   kum_k + kum_g,
            "detaylar":     sorted(
                sinav_detaylar.get(p.pk, []),
                key=lambda x: (x["tarih"], x["oturum_no"], x["tur"]),
            ),
        }

    tum_satirlar = sorted(
        [_row(p) for p in personel_listesi],
        key=lambda x: (x["brans"], x["adi_soyadi"]),
    )

    gruplu_satirlar = [
        {"brans": brans, "satirlar": list(s_list)}
        for brans, s_list in groupby(tum_satirlar, key=lambda x: x["brans"])
    ]

    toplam_komisyon = sum(s["komisyon"] if secili_sinav else s["kum_komisyon"] for g in gruplu_satirlar for s in g["satirlar"])
    toplam_gozetmen = sum(s["gozetmen"] if secili_sinav else s["kum_gozetmen"] for g in gruplu_satirlar for s in g["satirlar"])

    return {
        "gruplu_satirlar":  gruplu_satirlar,
        "toplam_komisyon":  toplam_komisyon,
        "toplam_gozetmen":  toplam_gozetmen,
        "toplam_personel":  len(personel_listesi),
        "gecmis_donemler":  gecmis_donemler,
    }


def personelin_sorumluluk_gorevlerini_hesapla(personel) -> list[dict]:
    """`ogretmen_sorumluluk_gorevleri` view'ı için bir personelin komisyon/gözetmen
    görevlerini sınav → oturum hiyerarşisinde gruplar."""
    from django.db.models import Q

    komisyonlar = list(
        SorumluKomisyonUyesi.objects
        .filter(Q(uye1=personel) | Q(uye2=personel))
        .select_related("sinav", "sinav__egitim_yili")
        .order_by("sinav__id", "tarih", "oturum_no", "ders_adi")
    )
    gozetmenler = list(
        SorumluGozetmen.objects
        .filter(gozetmen=personel)
        .select_related("sinav", "sinav__egitim_yili")
        .order_by("sinav__id", "tarih", "oturum_no")
    )

    sinav_idler = {k.sinav_id for k in komisyonlar} | {g.sinav_id for g in gozetmenler}

    takvim_saatler = {}
    if sinav_idler:
        for t in SorumluTakvim.objects.filter(sinav_id__in=sinav_idler).order_by("sinav", "tarih", "oturum_no"):
            key = (t.sinav_id, t.tarih, t.oturum_no)
            if key not in takvim_saatler:
                takvim_saatler[key] = (t.saat_baslangic, t.saat_bitis)

    sinav_map: dict = {}

    def _oturum_al(sid, sinav_obj, tarih, oturum_no):
        if sid not in sinav_map:
            sinav_map[sid] = {"sinav": sinav_obj, "oturumlar": {}}
        oturum_key = (tarih, oturum_no)
        if oturum_key not in sinav_map[sid]["oturumlar"]:
            saatler = takvim_saatler.get((sid, tarih, oturum_no))
            sinav_map[sid]["oturumlar"][oturum_key] = {
                "tarih":         tarih,
                "tarih_str":     _tr_tarih(tarih),
                "oturum_no":     oturum_no,
                "saat_baslangic": saatler[0] if saatler else None,
                "saat_bitis":    saatler[1] if saatler else None,
                "komisyonlar":   [],
                "gozetmenler":   [],
            }
        return sinav_map[sid]["oturumlar"][oturum_key]

    for k in komisyonlar:
        ot = _oturum_al(k.sinav_id, k.sinav, k.tarih, k.oturum_no)
        ot["komisyonlar"].append(k.ders_adi)

    for g in gozetmenler:
        ot = _oturum_al(g.sinav_id, g.sinav, g.tarih, g.oturum_no)
        ot["gozetmenler"].append(_SALON_LABEL.get(g.salon, g.salon))

    return [
        {
            "sinav": data["sinav"],
            "oturumlar": sorted(data["oturumlar"].values(), key=lambda x: (x["tarih"], x["oturum_no"])),
        }
        for _, data in sorted(sinav_map.items())
    ]
