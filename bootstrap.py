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
Tekrar çalıştırma güvenlidir: sanal ortam zaten varsa yeniden oluşturulmaz — ancak
pip'siz (bozuk) bir sanal ortam tespit edilirse otomatik olarak yeniden kurulur
(bkz. `_pip_calisir_mi` / `_sistem_paketlerini_kurmayi_dene`).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJE_DIZIN = Path(__file__).resolve().parent
VENV = PROJE_DIZIN / "venv"


def _calistir(komut: list[str]) -> None:
    subprocess.run(komut, cwd=PROJE_DIZIN, check=True)


def _yonetici_komutu(komut: list[str]) -> list[str]:
    """root değilsek başına 'sudo' ekler (root'ta sudo hiç kurulu olmayabilir)."""
    return komut if os.geteuid() == 0 else ["sudo", *komut]


def _pip_calisir_mi(venv_python: Path) -> bool:
    sonuc = subprocess.run(
        [str(venv_python), "-m", "pip", "--version"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return sonuc.returncode == 0


def _sistem_paketlerini_kurmayi_dene() -> bool:
    """`python3 -m venv` bazı Debian/Ubuntu sunucularında (python3-venv paketi
    kurulu değilse) ensurepip'i sessizce atlayıp pip'siz bir sanal ortam
    bırakabiliyor. Bu durumda gereken sistem paketini kurmayı dener.
    Başarılı olursa True döner (çağıran, sanal ortamı yeniden oluşturmalı)."""
    if shutil.which("apt-get"):
        print("[BİLGİ]  'python3-venv' paketi eksik görünüyor, kuruluyor (sudo gerekebilir)...")
        try:
            subprocess.run(_yonetici_komutu(["apt-get", "update", "-qq"]), check=True)
            subprocess.run(_yonetici_komutu(["apt-get", "install", "-y", "python3-venv"]), check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False
        return True
    if shutil.which("dnf"):
        print("[BİLGİ]  'python3-pip' paketi eksik görünüyor, kuruluyor (sudo gerekebilir)...")
        try:
            subprocess.run(_yonetici_komutu(["dnf", "install", "-y", "python3-pip"]), check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False
        return True
    return False


def _pipsiz_hata_ve_cik() -> None:
    print(
        "[HATA]   Sanal ortamda pip bulunamadı ve otomatik onarım başarısız oldu.\n"
        "         Elle kurup tekrar deneyin:\n"
        "           sudo apt install python3-venv   (Debian/Ubuntu)\n"
        "           sudo dnf install python3-pip    (Fedora/RHEL)\n"
        "         Sonra:\n"
        f"           rm -rf {VENV} && python3 bootstrap.py",
        file=sys.stderr,
    )
    raise SystemExit(1)


def main() -> None:
    if sys.version_info < (3, 12):
        surum = f"{sys.version_info.major}.{sys.version_info.minor}"
        print(f"[UYARI]  Python 3.12+ önerilir, tespit edilen: {surum}. Devam ediliyor...")

    venv_python = VENV / "bin" / "python"

    # Önceki bir çalıştırmadan pip'siz (bozuk) bir sanal ortam kalmış olabilir —
    # bu durumda "zaten var" diyip atlamak yerine yeniden oluşturuyoruz.
    if VENV.is_dir() and not _pip_calisir_mi(venv_python):
        print(f"[UYARI]  Mevcut sanal ortamda pip bulunamadı, yeniden oluşturulacak: {VENV}")
        shutil.rmtree(VENV)

    if VENV.is_dir():
        print(f"[BİLGİ]  Sanal ortam zaten var: {VENV} (atlanıyor)")
    else:
        print(f"[BİLGİ]  Sanal ortam oluşturuluyor: {VENV}")
        try:
            _calistir([sys.executable, "-m", "venv", str(VENV)])
        except subprocess.CalledProcessError:
            # 'venv' modülünün kendisi bile eksik olabilir (örn. python3-venv hiç
            # kurulu değilse Debian/Ubuntu'da bu adım doğrudan başarısız olur).
            print("[UYARI]  Sanal ortam oluşturulamadı (venv modülü eksik olabilir).")
            if not _sistem_paketlerini_kurmayi_dene():
                _pipsiz_hata_ve_cik()
            shutil.rmtree(VENV, ignore_errors=True)
            _calistir([sys.executable, "-m", "venv", str(VENV)])

        if not _pip_calisir_mi(venv_python):
            print("[UYARI]  Yeni oluşturulan sanal ortamda pip bulunamadı (ensurepip eksik).")
            if not _sistem_paketlerini_kurmayi_dene():
                _pipsiz_hata_ve_cik()
            print("[BİLGİ]  Sanal ortam pip ile yeniden oluşturuluyor...")
            shutil.rmtree(VENV)
            _calistir([sys.executable, "-m", "venv", str(VENV)])
            if not _pip_calisir_mi(venv_python):
                _pipsiz_hata_ve_cik()

        print("[TAMAM]  Sanal ortam oluşturuldu.")

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
