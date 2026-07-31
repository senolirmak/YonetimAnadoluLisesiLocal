from datetime import datetime

from ortaksinav_engine import CONFIG
from sinav.models import AlgoritmaParametreleri, DersAyarlariJSON, SinavBilgisi


def config_uygula(session_cfg: dict) -> None:
    """Session'daki ve DB'deki (AlgoritmaParametreleri, DersAyarlariJSON) ayarları
    okuyup `ortaksinav_engine.CONFIG`'e uygular."""
    if session_cfg.get("eokul_ogrenci_dosya"):
        CONFIG["eokul_ogrenci_dosya"] = session_cfg["eokul_ogrenci_dosya"]
    if session_cfg.get("eokul_haftalik_program_dosya"):
        CONFIG["eokul_haftalik_program_dosya"] = session_cfg["eokul_haftalik_program_dosya"]
    if session_cfg.get("uygulama_tarihi"):
        CONFIG["uygulama_tarihi"] = session_cfg["uygulama_tarihi"]

    # Algoritma parametreleri: DB birincil kaynak, yoksa session'a bak
    aktif_sinav_cfg = SinavBilgisi.objects.filter(aktif=True).first()
    prm = AlgoritmaParametreleri.objects.filter(sinav=aktif_sinav_cfg).first() if aktif_sinav_cfg else None
    alg = prm.to_session_dict() if prm else session_cfg

    if alg.get("baslangic_tarih"):
        CONFIG["BASLANGIC_TARIH"] = datetime.fromisoformat(str(alg["baslangic_tarih"]))

    if alg.get("oturum_saatleri"):
        saatler = [s.strip() for s in alg["oturum_saatleri"].split(",") if s.strip()]
        CONFIG["OTURUM_SAATLERI"] = saatler
        CONFIG["OTURUM_SAYISI_GUN"] = len(saatler)

    if "time_limit_phase1" in alg:
        CONFIG["TIME_LIMIT_PHASE1"] = int(alg["time_limit_phase1"])
    if "time_limit_phase2" in alg:
        CONFIG["TIME_LIMIT_PHASE2"] = int(alg["time_limit_phase2"])
    if "max_extra_days" in alg:
        CONFIG["MAX_EXTRA_DAYS"] = int(alg["max_extra_days"])

    if alg.get("tatil_gunleri"):
        holidays = set()
        for line in alg["tatil_gunleri"].splitlines():
            line = line.strip()
            if line:
                try:
                    holidays.add(datetime.fromisoformat(line).date())
                except ValueError:
                    pass
        CONFIG["HOLIDAYS"] = holidays

    # Ders ayarlarini aktif sinava gore JSON'dan yukle
    aktif_sinav = aktif_sinav_cfg
    try:
        _daj = DersAyarlariJSON.objects.get(sinav=aktif_sinav)
        _veri = _daj.veri or {}
    except DersAyarlariJSON.DoesNotExist:
        _veri = {}

    yapilmayacak = _veri.get("yapilmayacak", [])
    if yapilmayacak:
        CONFIG["SINAV_YAPILMAYACAK_DERSLER"] = yapilmayacak
    cift_oturumlu = _veri.get("cift_oturumlu", [])
    if cift_oturumlu:
        CONFIG["CIFT_OTURUMLU_DERSLER"] = cift_oturumlu
    CONFIG["SABIT_SINAVLAR"] = [
        {
            "ders":      s["ders_adi"],
            "tarih":     s["tarih"],
            "saat":      s["saat"],
            "seviyeler": [int(v) for v in (s.get("seviyeler") or []) if str(v).isdigit()],
        }
        for s in _veri.get("sabit_sinavlar", [])
    ]
    CONFIG["SEVIYE_CATISMA_GRUPLARI"] = [
        g["dersler"] if isinstance(g.get("dersler"), list)
        else [d.strip() for d in g.get("dersler", "").split(",") if d.strip()]
        for g in _veri.get("catisma_gruplari", [])
    ]
    CONFIG["AYNI_SLOT_ESLEME"] = [
        [e["ders1"], e["ders2"]]
        for e in _veri.get("ayni_slot_esleme", [])
    ]
    ortak_seviyeleri = _veri.get("ortak_sinav_seviyeleri", [])
    CONFIG["ORTAK_SINAV_SEVIYELERI"] = [int(s) for s in ortak_seviyeleri] if ortak_seviyeleri else []

    # Kelebek dağılımı ayarı DB'den gelir; yoksa True (mevcut davranış)
    kelebek = True
    if prm is not None:
        kelebek = bool(prm.kelebek_dagitim)
    elif alg.get("kelebek_dagitim") is not None:
        kelebek = bool(alg["kelebek_dagitim"])
    CONFIG["KELEBEK_DAGITIM"] = kelebek

    # Günde maks. sınav sayısı
    if prm is not None:
        CONFIG["MAX_SINAV_PER_GUN"] = int(prm.max_sinav_per_gun)
    elif alg.get("max_sinav_per_gun") is not None:
        CONFIG["MAX_SINAV_PER_GUN"] = int(alg["max_sinav_per_gun"])
    else:
        CONFIG["MAX_SINAV_PER_GUN"] = 2
