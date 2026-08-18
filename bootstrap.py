#!/usr/bin/env python3
"""
Kurulum önyüklemesi (Okul Yönetim Sistemi)
===========================================
Bu script yalnızca standart kütüphaneyi kullanır — proje henüz kurulmadığı için
üçüncü parti paketlere (Django, psycopg2 vb.) güvenemez. Yaptığı tek şey:

  1. Sanal ortam oluşturmak (yoksa),
  2. Projeyi 'pip install -e .' ile kurmak (pyproject.toml / setuptools üzerinden;
     bağımlılıklar dynamic olarak requirements.txt'ten okunur),
  3. Asıl interaktif kurulum akışını (kurulumcu.cli:main → 'okulyonetim-kur' konsol
     komutu) sanal ortam içinden devralmak.

Kullanım : python3 bootstrap.py
Tekrar çalıştırma güvenlidir: sanal ortam zaten varsa yeniden oluşturulmaz.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PROJE_DIZIN = Path(__file__).resolve().parent
VENV = PROJE_DIZIN / "venv"


def _calistir(komut: list[str]) -> None:
    subprocess.run(komut, cwd=PROJE_DIZIN, check=True)


def main() -> None:
    if sys.version_info < (3, 12):
        surum = f"{sys.version_info.major}.{sys.version_info.minor}"
        print(f"[UYARI]  Python 3.12+ önerilir, tespit edilen: {surum}. Devam ediliyor...")

    if VENV.is_dir():
        print(f"[BİLGİ]  Sanal ortam zaten var: {VENV} (atlanıyor)")
    else:
        print(f"[BİLGİ]  Sanal ortam oluşturuluyor: {VENV}")
        _calistir([sys.executable, "-m", "venv", str(VENV)])
        print("[TAMAM]  Sanal ortam oluşturuldu.")

    venv_python = VENV / "bin" / "python"
    venv_kurulum_komutu = VENV / "bin" / "okulyonetim-kur"

    print("[BİLGİ]  Proje ve bağımlılıklar kuruluyor (pip install -e .)...")
    _calistir([str(venv_python), "-m", "pip", "install", "--upgrade", "pip", "--quiet"])
    _calistir([str(venv_python), "-m", "pip", "install", "-e", ".", "--quiet"])
    print("[TAMAM]  Bağımlılıklar kuruldu.")

    if not venv_kurulum_komutu.is_file():
        print(
            f"[HATA]   Kurulum komutu bulunamadı: {venv_kurulum_komutu}\n"
            "         'pip install -e .' başarılı oldu mu kontrol edin.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    print("[BİLGİ]  Kurulum sihirbazına devrediliyor...\n")
    os.execv(str(venv_kurulum_komutu), [str(venv_kurulum_komutu), *sys.argv[1:]])


if __name__ == "__main__":
    main()
