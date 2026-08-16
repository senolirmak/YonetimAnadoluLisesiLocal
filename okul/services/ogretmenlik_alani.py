"""
Personel.brans / Personel.mezunokul alanlarını OgretmenlikAlanCizelgesi (TTKB)
çizelgesiyle eşleştirip bir personelin okutmaya yetkili olduğu dersleri belirleyen servis.

Branş adları (Personel.brans.ad ↔ OgretmenlikAlanCizelgesi.brans) genelde birebir eşleşir —
ikisi de aynı resmi taksonomiden gelir. Ama mezunokul serbest metindir (Personel tarafı Excel
içe aktarımından elle girilir, çizelge tarafı TTKB PDF'inden `ttkb_cizelge_yukle` komutuyla
içe aktarılır) — aynı branş için birden fazla mezuniyet programı satırı olabildiğinden (örn.
Matematik branşında "Matematik Bölümü" / "Matematik Mühendisliği" / "Matematik Öğretmenliği"
gibi ayrı satırlar var, her biri farklı ders yetkisine sahip olabilir) otomatik eşleştirme
yalnızca normalize edilmiş metin BİREBİR aynıysa güvenilir kabul edilir. Aksi hâlde (birden
fazla aday veya hiç eşleşme yoksa) kullanıcı `Personel.ogretmenlik_alani` alanını
`okul/yonetim/personel/<pk>/duzenle/` sayfasından elle seçmelidir.
"""
from __future__ import annotations

import re


def _normalize(metin: str) -> str:
    """Karşılaştırma için: küçük harfe çevir, noktalama/fazla boşlukları sadeleştir."""
    if not metin:
        return ""
    metin = metin.strip().lower()
    metin = re.sub(r"[.,/]", " ", metin)
    metin = re.sub(r"\s+", " ", metin)
    return metin.strip()


def brans_adaylari(personel):
    """Personelin branşıyla eşleşen tüm OgretmenlikAlanCizelgesi satırlarını döner
    (mezunokul ayrımı yapılmadan) — elle seçim ekranındaki aday listesi budur."""
    from okul.models import OgretmenlikAlanCizelgesi

    if not personel.brans_id:
        return OgretmenlikAlanCizelgesi.objects.none()
    return OgretmenlikAlanCizelgesi.objects.filter(
        brans__iexact=personel.brans.ad
    ).order_by("mezunokul")


def onerilen_alan(personel):
    """Branş + mezunokul normalize edilmiş metni BİREBİR aynıysa o tek satırı döner;
    hiç eşleşme yoksa veya birden fazla aday varsa (belirsiz) None döner — bu durumda
    kullanıcı elle seçim yapmalıdır."""
    hedef = _normalize(personel.mezunokul)
    if not hedef:
        return None

    eslesenler = [a for a in brans_adaylari(personel) if _normalize(a.mezunokul) == hedef]
    if len(eslesenler) == 1:
        return eslesenler[0]
    return None


def okuttugu_dersler(personel) -> str:
    """Personelin okutmaya yetkili olduğu dersleri döner.

    Öncelik sırası: elle atanmış `personel.ogretmenlik_alani`; yoksa otomatik birebir
    eşleşme (`onerilen_alan`); o da yoksa boş string (eşleşme belirsiz).
    """
    alan = personel.ogretmenlik_alani or onerilen_alan(personel)
    return alan.dersler if alan else ""
