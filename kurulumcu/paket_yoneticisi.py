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


def podman_compose_kur(paket_yoneticisi: str) -> None:
    """Podman kurulu olsa bile 'podman compose' bir compose sağlayıcı (bu paket)
    olmadan çalışmaz — apt/dnf ile podman-compose kurar."""
    y.bilgi("Compose sağlayıcısı (podman-compose) kuruluyor...")
    if paket_yoneticisi == "apt":
        y.calistir(["apt-get", "update", "-qq"], sudo=True)
        y.calistir(["apt-get", "install", "-y", "podman-compose"], sudo=True, sessiz=True)
    else:
        y.calistir(["dnf", "install", "-y", "podman-compose"], sudo=True, sessiz=True)
    y.basari("podman-compose kuruldu.")


def postgresql_istemci_kur(paket_yoneticisi: str, hedef_surum: str | None = None) -> None:
    """Yalnızca PostgreSQL istemci araçlarını (`psql`, `pg_dump`, `pg_restore`) kurar
    — sunucu bileşeni YOK. PostgreSQL konteyner modunda çalıştırıldığında (bkz.
    `veritabani.konteyner_ile_kur`) `yedekleme` app'inin bu araçları host'ta, TCP
    üzerinden (podman/docker exec'e hiç ihtiyaç duymadan) kullanabilmesi içindir —
    bkz. `yedekleme/services/yedek_servisi.py` modül docstring'i.

    `hedef_surum` (örn. "18") verilirse TAM o majör sürüme özel istemci paketi
    kurulmaya çalışılır — pg_dump kendisinden daha yeni bir sunucuyu yedekleyemez
    ("sunucu sürümü uyuşmazlığı" hatasıyla iptal eder), bu yüzden konteynerdeki
    (bkz. `VARSAYILAN_IMAJ`) PostgreSQL sürümüyle eşleşmesi gerekir. Debian/Ubuntu'nun
    kendi deposu tek, dondurulmuş bir sürüm taşır (örn. Debian 13 → 17) ve bu genelde
    konteynerden eskidir; eşleşen paket depoda yoksa resmi PostgreSQL deposu
    (apt.postgresql.org / PGDG) `postgresql-common` paketinin getirdiği resmi betikle
    otomatik eklenir."""
    y.bilgi("PostgreSQL istemci araçları kuruluyor (psql, pg_dump, pg_restore)...")
    if paket_yoneticisi == "apt":
        y.calistir(["apt-get", "update", "-qq"], sudo=True)
        if hedef_surum:
            paket = f"postgresql-client-{hedef_surum}"
            if not y.basarili_mi(["apt-cache", "show", paket]):
                y.bilgi(
                    f"'{paket}' Debian/Ubuntu'nun kendi deposunda yok; resmi PostgreSQL "
                    "deposu (PGDG) ekleniyor..."
                )
                y.calistir(["apt-get", "install", "-y", "postgresql-common"], sudo=True, sessiz=True)
                # '-y' onay istemini atlar; stdin'i de kapalı (boş girdi) geçiyoruz ki
                # eski bir postgresql-common sürümünde '-y' desteklenmese bile betik
                # interaktif bir yanıt bekleyip komutu sonsuza dek askıda bırakmasın.
                y.calistir(
                    ["/usr/share/postgresql-common/pgdg/apt.postgresql.org.sh", "-y"],
                    sudo=True,
                    sessiz=True,
                    girdi="",
                )
                y.calistir(["apt-get", "update", "-qq"], sudo=True)
            y.calistir(["apt-get", "install", "-y", paket], sudo=True, sessiz=True)
        else:
            y.calistir(["apt-get", "install", "-y", "postgresql-client"], sudo=True, sessiz=True)
    else:
        # Fedora/RHEL'de 'postgresql' paketi yalnızca istemci araçlarını taşır;
        # sunucu ayrı bir paket olan 'postgresql-server'dadır. Sürüme özel paketler
        # (PGDG'nin yum deposu) burada denenmiyor — Debian/Ubuntu'nun aksine dağıtım
        # sürümüne göre değişen ayrı bir repo-rpm kurulumu gerektirir; eşleşmezse
        # `veritabani.istemci_araclarini_dogrula` kurulum sonrası ayrıca uyarır.
        y.calistir(["dnf", "install", "-y", "postgresql"], sudo=True, sessiz=True)
    y.basari("PostgreSQL istemci araçları hazır.")


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
