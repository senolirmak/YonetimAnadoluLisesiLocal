"""Öğretmenin sorumluluk sınavı komisyon üyeliği / gözetmenlik görevlerini hazırlar."""
from django.db.models import Q

from sorumluluk.models import SorumluGozetmen, SorumluKomisyonUyesi, SorumluTakvim, salon_choices


def gorevlerimi_hazirla(personel) -> list[dict]:
    """Verilen personelin tüm sorumluluk sınavlarındaki görevlerini (komisyon üyesi +
    gözetmen), sınav bazında gruplayıp tarih/oturum sırasına göre hazırlar."""
    if not personel:
        return []

    salon_label = dict(salon_choices())

    takvim_saatler = {
        (t.sinav_id, t.tarih, t.oturum_no): (t.saat_baslangic, t.saat_bitis)
        for t in SorumluTakvim.objects.order_by("sinav_id", "tarih", "oturum_no")
    }

    sinav_map: dict = {}

    for ku in (SorumluKomisyonUyesi.objects
               .filter(Q(uye1=personel) | Q(uye2=personel))
               .select_related("sinav", "sinav__egitim_yili")
               .order_by("sinav__olusturma_tarihi", "tarih", "oturum_no")):
        sid = ku.sinav_id
        if sid not in sinav_map:
            sinav_map[sid] = {"sinav": ku.sinav, "gorevler": []}
        saatler = takvim_saatler.get((sid, ku.tarih, ku.oturum_no))
        sinav_map[sid]["gorevler"].append({
            "tarih":          ku.tarih,
            "oturum_no":      ku.oturum_no,
            "saat_baslangic": saatler[0] if saatler else None,
            "saat_bitis":     saatler[1] if saatler else None,
            "tur":            "Komisyon Üyesi",
            "detay":          ku.ders_adi,
        })

    for gz in (SorumluGozetmen.objects
               .filter(gozetmen=personel)
               .select_related("sinav", "sinav__egitim_yili")
               .order_by("sinav__olusturma_tarihi", "tarih", "oturum_no")):
        sid = gz.sinav_id
        if sid not in sinav_map:
            sinav_map[sid] = {"sinav": gz.sinav, "gorevler": []}
        saatler = takvim_saatler.get((sid, gz.tarih, gz.oturum_no))
        sinav_map[sid]["gorevler"].append({
            "tarih":          gz.tarih,
            "oturum_no":      gz.oturum_no,
            "saat_baslangic": saatler[0] if saatler else None,
            "saat_bitis":     saatler[1] if saatler else None,
            "tur":            "Gözetmen",
            "detay":          salon_label.get(gz.salon, gz.salon),
        })

    for data in sinav_map.values():
        data["gorevler"].sort(key=lambda x: (x["tarih"], x["oturum_no"], x["tur"]))
        data["komisyon_sayi"] = sum(1 for g in data["gorevler"] if g["tur"] == "Komisyon Üyesi")
        data["gozetmen_sayi"] = sum(1 for g in data["gorevler"] if g["tur"] == "Gözetmen")

    return sorted(
        sinav_map.values(),
        key=lambda d: d["sinav"].olusturma_tarihi or d["sinav"].pk,
    )
