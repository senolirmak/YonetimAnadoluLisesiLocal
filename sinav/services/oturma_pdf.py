import re

from sinav.models import OturmaUretim, TakvimUretim


def resolve_aktif_uretim(uretim_pk, tarih, saat, oturum, aktif_sinav):
    """OturmaUretim üzerinden doğru TakvimUretim'i çözer.

    `uretim_pk` verilmişse önce o üretime ait OturmaUretim kaydı aranır;
    bulunamazsa (aktif üretim değişmiş olabilir) aynı (tarih, saat, oturum)
    için herhangi bir OturmaUretim kaydı aranır. `uretim_pk` verilmemişse
    `aktif_sinav`ın aktif TakvimUretim'i döner. Hiçbiri bulunamazsa None."""
    if uretim_pk:
        ou = OturmaUretim.objects.filter(
            takvim_uretim_id=int(uretim_pk), tarih=tarih, saat=saat, oturum=oturum
        ).select_related("takvim_uretim").first()
        if not ou:
            ou = OturmaUretim.objects.filter(
                tarih=tarih, saat=saat, oturum=oturum
            ).select_related("takvim_uretim").first()
        return ou.takvim_uretim if ou else None
    return TakvimUretim.objects.filter(sinav=aktif_sinav, aktif=True).first()


def build_salon_grids(oturma_plani_qs) -> dict:
    """Bir oturuma ait OturmaPlani kayıtlarını salon → 3x6x2 ızgara yapısına
    (blok/satır/sütun) dönüştürür — Oturma Planı PDF'inin şablonu bu yapıyı
    bekler."""
    salon_grids: dict = {}
    for op in oturma_plani_qs:
        if op.salon not in salon_grids:
            salon_grids[op.salon] = [[[None] * 2 for _ in range(6)] for _ in range(3)]
        sira  = op.sira_no - 1
        block = sira // 12
        rem   = sira % 12
        row   = rem // 2
        col   = rem % 2
        if block < 3 and row < 6 and col < 2:
            sinifsube = str(op.sinifsube or "")
            m = re.search(r"(\d+)", sinifsube)
            parts = (op.adi_soyadi or "").split(" ", 1)
            salon_grids[op.salon][block][row][col] = {
                "okulno":    op.okulno,
                "sinifsube": sinifsube,
                "adi":       parts[0] if parts else "",
                "soyadi":    parts[1] if len(parts) > 1 else "",
                "ders":      op.ders_adi or "",
                "sinif":     m.group(1) if m else "",
            }
    return salon_grids
