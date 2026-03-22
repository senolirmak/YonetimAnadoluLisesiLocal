# -*- coding: utf-8 -*-
from datetime import datetime

CONFIG = {
    # Yuklenen ham dosya yollari (view tarafindan set edilir)
    "eokul_ogrenci_dosya": "",
    "eokul_haftalik_program_dosya": "",
    "uygulama_tarihi": "2026-02-23",
    # Cikti klasoru (view tarafindan MEDIA_ROOT/cikti olarak set edilir)
    "cikti_klasor": "",
    # ILP / takvim parametreleri
    "HOLIDAYS": set(),
    "BASLANGIC_TARIH": datetime(2025, 1, 6),
    "OTURUM_SAYISI_GUN": 5,
    "OTURUM_SAATLERI": ["08:50", "10:30", "12:10", "13:35", "14:25"],
    "TIME_LIMIT_PHASE1": 300,
    "TIME_LIMIT_PHASE2": 120,
    "MAX_EXTRA_DAYS": 10,
}

CIFT_OTURUMLU_DERSLER = [
    "SEÇMELİ İKİNCİ YABANCI DİL",
    "SEÇMELİ TÜRK DİLİ VE EDEBİYATI",
    "TÜRK DİLİ VE EDEBİYATI",
    "YABANCI DİL",
]

SINAV_YAPILMAYACAK_DERSLER = [
    "GÖRSEL SANATLAR/MÜZİK",
    "BEDEN EĞİTİMİ VE SPOR/GÖRSEL SANATLAR/MÜZİK",
    "BEDEN EĞİTİMİ VE SPOR",
    "SEÇMELİ SANAT EĞİTİMİ",
    "REHBERLİK VE YÖNLENDİRME",
    "SEÇMELİ SPOR EĞİTİMİ",
    "SEÇMELİ HEDEF TEMELLİ DESTEK EĞİTİMİ",
    "SEÇMELİ YABANCI DİL",
]
