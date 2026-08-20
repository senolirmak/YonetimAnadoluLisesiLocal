"""Kurulum sihirbazı için ortak yardımcılar: renkli çıktı, soru sorma, komut çalıştırma."""

from __future__ import annotations

import shutil
import subprocess
import sys
from getpass import getpass

KIRMIZI = "\033[0;31m"
YESIL = "\033[0;32m"
SARI = "\033[1;33m"
MAVI = "\033[0;34m"
SIFIRLA = "\033[0m"


def bilgi(mesaj: str) -> None:
    print(f"{MAVI}[BİLGİ]{SIFIRLA}  {mesaj}")


def basari(mesaj: str) -> None:
    print(f"{YESIL}[TAMAM]{SIFIRLA}  {mesaj}")


def uyari(mesaj: str) -> None:
    print(f"{SARI}[UYARI]{SIFIRLA}  {mesaj}")


def hata(mesaj: str) -> None:
    print(f"{KIRMIZI}[HATA]{SIFIRLA}   {mesaj}", file=sys.stderr)
    raise SystemExit(1)


def sor(soru: str, varsayilan: str = "") -> str:
    if varsayilan:
        cevap = input(f"{soru} [{varsayilan}]: ").strip()
        return cevap or varsayilan
    return input(f"{soru}: ").strip()


def sor_sifre(soru: str) -> str:
    return getpass(f"{soru}: ")


def komut_var_mi(ad: str) -> bool:
    return shutil.which(ad) is not None


def calistir(
    komut: list[str],
    *,
    sudo: bool = False,
    sessiz: bool = False,
    kontrol: bool = True,
    ortam: dict[str, str] | None = None,
    girdi: str | None = None,
) -> subprocess.CompletedProcess:
    """Bir komutu çalıştırır. sudo=True ise başına 'sudo' eklenir, girdi verilirse stdin'e yazılır.

    sessiz=True stdout'u bastırır ama stderr'i her zaman yakalar: komut
    kontrol=True (varsayılan) ile başarısız olursa, yakalanan stderr `hata()`
    ile ekrana basılıp çıkılır — aksi halde sebep hiç görünmeden yalnızca bir
    CalledProcessError traceback'i kalırdı. kontrol=False ile çağrılan (hatası
    beklenen/önemsiz) komutlar bu davranışa girmez, sessizce devam eder.
    """
    if sudo:
        komut = ["sudo", *komut]
    sonuc = subprocess.run(
        komut,
        text=True,
        input=girdi,
        stdout=subprocess.DEVNULL if sessiz else None,
        stderr=subprocess.PIPE if sessiz else None,
        env=ortam,
    )
    if kontrol and sonuc.returncode != 0:
        if sessiz:
            detay = sonuc.stderr.strip() if sonuc.stderr else "(stderr boş)"
            hata(f"Komut başarısız oldu: {' '.join(komut)}\n{detay}")
        sonuc.check_returncode()
    return sonuc


def cikti(komut: list[str], *, sudo: bool = False, ortam: dict[str, str] | None = None) -> str:
    """Bir komutu çalıştırır ve stdout'unu (baştaki/sondaki boşluklar kırpılmış) döner."""
    if sudo:
        komut = ["sudo", *komut]
    sonuc = subprocess.run(komut, text=True, capture_output=True, env=ortam)
    return sonuc.stdout.strip()


def basarili_mi(komut: list[str], *, sudo: bool = False, ortam: dict[str, str] | None = None) -> bool:
    if sudo:
        komut = ["sudo", *komut]
    sonuc = subprocess.run(komut, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=ortam)
    return sonuc.returncode == 0
