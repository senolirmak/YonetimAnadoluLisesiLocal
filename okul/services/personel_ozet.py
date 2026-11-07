"""Ana sayfadaki "Aktif Personel" kartı için personel özeti."""

from django.db.models import Count, Q

from okul.models import Personel


def aktif_personel_ozeti(tarih) -> dict:
    """Görevdeki personelin görev türüne göre kadın/erkek dağılımı, geçici olarak
    görev dışında olanların sayısı ve `tarih` günü devamsız personel sayısı."""
    from nobet.views.ders_doldurma._queries import aktif_devamsizliklar

    sayimlar = {
        r["gorev_tipi"]: r
        for r in Personel.objects.gorevde()
        .values("gorev_tipi")
        .annotate(kadin=Count("id", filter=Q(cinsiyet=False)), erkek=Count("id", filter=Q(cinsiyet=True)))
    }
    gorevler = []
    for kod, ad in [*Personel.GOREVI_CHOICES, (None, "Belirtilmemiş")]:
        r = sayimlar.get(kod)
        if r:
            gorevler.append({"gorev": ad, "kadin": r["kadin"], "erkek": r["erkek"],
                             "toplam": r["kadin"] + r["erkek"]})
    kadin = sum(g["kadin"] for g in gorevler)
    erkek = sum(g["erkek"] for g in gorevler)
    return {
        "gorevler": gorevler,
        "toplam": {"kadin": kadin, "erkek": erkek, "toplam": kadin + erkek},
        "gecici_gorev_disi": Personel.objects.aktif().exclude(durum="Görevde").count(),
        "bugun_devamsiz": len({d.ogretmen_id for d in aktif_devamsizliklar(tarih)}),
    }
