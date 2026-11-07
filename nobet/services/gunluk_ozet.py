"""Devamsızlık ve Nöbet İşlemleri sayfası için günün kısa özeti.

Sayılar Ders Doldurma ekranıyla aynı kaynaktan gelir: aynı gün birden fazla
kez kaydedilmişse yalnızca en son kayıt sayılır (bkz. `en_son_kayit_dt`).
"""

from nobet.views.ders_doldurma._queries import (
    aktif_devamsizliklar,
    en_son_kayit_dt,
    kayitli_atamalar_ve_atamayanlar,
)


def gunluk_ozet(tarih) -> dict:
    """`tarih` günü için devamsız personel, atanan ve atanamayan ders sayıları."""
    devamsiz = {d.ogretmen_id for d in aktif_devamsizliklar(tarih)}

    atanan, atanamayan = [], []
    son_kayit = en_son_kayit_dt(tarih)
    if son_kayit:
        atanan, atanamayan = kayitli_atamalar_ve_atamayanlar(
            son_kayit.replace(microsecond=0), son_kayit.replace(microsecond=999999)
        )

    return {
        "tarih": tarih,
        "devamsiz_personel": len(devamsiz),
        "atanan_ders": len(atanan),
        "atanamayan_ders": len(atanamayan),
    }
