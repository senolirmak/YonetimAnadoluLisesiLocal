"""Sistem paket yöneticisi (apt/dnf) tespiti ve sunucu paketlerinin kurulumu."""

from __future__ import annotations

from pathlib import Path

from . import yardimci as y


def tespit_et() -> str | None:
    if y.komut_var_mi("apt-get"):
        return "apt"
    if y.komut_var_mi("dnf"):
        return "dnf"
    return None


def sunucu_paketlerini_kur(paket_yoneticisi: str) -> None:
    y.bilgi("Sunucu paketleri kuruluyor (nginx, poppler-utils)...")
    if paket_yoneticisi == "apt":
        y.calistir(["apt-get", "update", "-qq"], sudo=True)
        y.calistir(
            ["apt-get", "install", "-y", "python3-venv", "nginx", "poppler-utils"],
            sudo=True,
            sessiz=True,
        )
    else:
        y.calistir(["dnf", "install", "-y", "nginx", "poppler-utils"], sudo=True, sessiz=True)
    y.basari("Sunucu paketleri hazır.")


def konteyner_araci_kur(paket_yoneticisi: str) -> str:
    """PostgreSQL'i konteynerle çalıştırmak için podman kurar (Docker'a göre bu
    projede tercih edilen araç — rootless çalışabilir, ayrı bir daemon
    gerektirmez) ve kurulan aracın adını döner."""
    y.bilgi("Konteyner aracı (podman) kuruluyor...")
    if paket_yoneticisi == "apt":
        y.calistir(["apt-get", "update", "-qq"], sudo=True)
        y.calistir(["apt-get", "install", "-y", "podman"], sudo=True, sessiz=True)
    else:
        y.calistir(["dnf", "install", "-y", "podman"], sudo=True, sessiz=True)
    y.basari("Podman kuruldu.")
    return "podman"


def postgresql_kur(paket_yoneticisi: str) -> None:
    y.bilgi("PostgreSQL sunucusu kuruluyor...")
    if paket_yoneticisi == "apt":
        y.calistir(
            ["apt-get", "install", "-y", "postgresql", "postgresql-contrib"], sudo=True, sessiz=True
        )
        y.calistir(["systemctl", "enable", "--now", "postgresql"], sudo=True)
    else:
        y.calistir(
            ["dnf", "install", "-y", "postgresql-server", "postgresql-contrib"],
            sudo=True,
            sessiz=True,
        )
        if not Path("/var/lib/pgsql/data/base").is_dir():
            y.calistir(["postgresql-setup", "--initdb"], sudo=True)
        y.calistir(["systemctl", "enable", "--now", "postgresql"], sudo=True)
    y.basari("PostgreSQL kuruldu ve başlatıldı.")
