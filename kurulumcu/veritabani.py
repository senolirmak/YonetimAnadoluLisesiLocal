"""PostgreSQL veritabanı/kullanıcısı kurulumu — native (sistemde kurulu) veya konteyner (podman/docker)."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

from . import yardimci as y

# Tam nitelikli (registry önekli) imaj adı kullanılıyor — kısa isimler
# (örn. yalnızca "postgres:18-alpine"), bazı sunucularda /etc/containers/registries.conf
# içinde unqualified-search-registries tanımlı olmadığında podman tarafından
# reddedilir ("short-name did not resolve to an alias" hatası). Tam nitelikli
# ad bu duruma bağlı olmadan her zaman çalışır.
VARSAYILAN_IMAJ = "docker.io/library/postgres:18-alpine"


@dataclass
class DBAyarlari:
    ad: str
    kullanici: str
    sifre: str
    host: str
    port: str


def baglanabiliyor_mu(ayar: DBAyarlari) -> bool:
    """venv'e requirements.txt ile kurulan psycopg2-binary üzerinden bağlantı dener;
    hem native hem konteyner PostgreSQL için aynı şekilde çalışır (port host'a açık olduğu sürece)."""
    try:
        import psycopg2
    except ImportError:
        return False
    try:
        baglanti = psycopg2.connect(
            dbname=ayar.ad,
            user=ayar.kullanici,
            password=ayar.sifre,
            host=ayar.host,
            port=ayar.port,
            connect_timeout=3,
        )
        baglanti.close()
        return True
    except Exception:
        return False


def konteyner_araci_tespit_et() -> str | None:
    if y.komut_var_mi("podman"):
        return "podman"
    if y.komut_var_mi("docker"):
        return "docker"
    return None


def sunucu_surumu(ayar: DBAyarlari) -> str | None:
    """Bağlı PostgreSQL sunucusunun kısa sürüm bilgisini döner (örn. 'PostgreSQL 18.3');
    bağlanılamıyorsa ya da psycopg2 yoksa None. Yalnızca bilgilendirme amaçlıdır."""
    try:
        import psycopg2
    except ImportError:
        return None
    try:
        baglanti = psycopg2.connect(
            dbname=ayar.ad,
            user=ayar.kullanici,
            password=ayar.sifre,
            host=ayar.host,
            port=ayar.port,
            connect_timeout=3,
        )
        try:
            with baglanti.cursor() as imlec:
                imlec.execute("SHOW server_version;")
                surum = imlec.fetchone()[0]
        finally:
            baglanti.close()
        return f"PostgreSQL {surum}"
    except Exception:
        return None


def konteyner_calisiyor_mu(arac: str, ayar: DBAyarlari) -> str | None:
    """`<db_adı>_pg` adında, `konteyner_ile_kur`'un oluşturduğu kalıpta çalışan bir
    konteyner varsa adını döner — zaten bağlanılabilen bir DB'nin konteynerde mi
    yoksa native mi çalıştığını bilgilendirmek için kullanılır."""
    konteyner_adi = f"{ayar.ad}_pg"
    var_mi = y.cikti(
        [arac, "ps", "--filter", f"name=^{konteyner_adi}$", "--filter", "status=running", "-q"]
    )
    return konteyner_adi if var_mi else None


def konteyner_ile_kur(arac: str, ayar: DBAyarlari, imaj: str = VARSAYILAN_IMAJ) -> str:
    """Konteyneri oluşturur/başlatır, hazır olmasını bekler ve konteyner adını döner."""
    konteyner_adi = f"{ayar.ad}_pg"
    volume_adi = f"{ayar.ad}_pg_data"

    var_mi = y.cikti([arac, "ps", "-a", "--filter", f"name=^{konteyner_adi}$", "-q"])
    if var_mi:
        y.uyari(f"Konteyner '{konteyner_adi}' zaten var, (yeniden) başlatılıyor...")
        y.calistir([arac, "start", konteyner_adi], sessiz=True)
    else:
        y.bilgi(f"PostgreSQL konteyneri oluşturuluyor: {konteyner_adi} (imaj: {imaj})")
        y.calistir(
            [
                arac,
                "run",
                "-d",
                "--name",
                konteyner_adi,
                "--restart=always",
                "-e",
                f"POSTGRES_DB={ayar.ad}",
                "-e",
                f"POSTGRES_USER={ayar.kullanici}",
                "-e",
                f"POSTGRES_PASSWORD={ayar.sifre}",
                # Yalnızca localhost'a bağla — sunucuda public IP varsa DB portunun
                # dışarıdan erişilebilir kalmasını önler (uygulama zaten aynı
                # makinede localhost/127.0.0.1 üzerinden bağlanıyor).
                "-p",
                f"127.0.0.1:{ayar.port}:5432",
                "-v",
                f"{volume_adi}:/var/lib/postgresql/data",
                imaj,
            ],
            sessiz=True,
        )
        y.basari("Konteyner oluşturuldu (DB ve kullanıcı imaj tarafından ilk açılışta otomatik oluşturulur).")

    y.bilgi("PostgreSQL'in hazır olması bekleniyor...")
    for _ in range(30):
        if y.basarili_mi([arac, "exec", konteyner_adi, "pg_isready", "-U", ayar.kullanici, "-d", ayar.ad]):
            break
        time.sleep(1)
    else:
        y.hata(
            f"PostgreSQL konteyneri 30 saniye içinde hazır olmadı. "
            f"'{arac} logs {konteyner_adi}' ile kontrol edin."
        )
    y.basari("PostgreSQL konteyneri hazır.")

    y.uyari(
        f"Kalıcılık notu: --restart=always, {arac} servisi açık olduğu sürece "
        "reboot sonrası konteyneri yeniden başlatır."
    )
    if arac == "podman":
        y.uyari("  Rootless Podman'da oturum kapatıldığında da ayakta kalması için: 'loginctl enable-linger $USER'")

    return konteyner_adi


def native_ile_kur(ayar: DBAyarlari, paket_yon: str | None, sunucu_modu: bool) -> None:
    if not y.komut_var_mi("psql"):
        if sunucu_modu and paket_yon:
            from . import paket_yoneticisi

            paket_yoneticisi.postgresql_kur(paket_yon)
        else:
            y.hata("psql bulunamadı. PostgreSQL istemcisini kurun (örn. 'sudo dnf install postgresql').")

    y.bilgi("Bu adım için PostgreSQL'e bağlanabilecek bir superuser (genelde 'postgres') gerekir.")
    superuser = y.sor("PostgreSQL superuser", "postgres")

    # Taze kurulan/yerel PostgreSQL'de 'postgres' rolünün genelde TCP şifresi yoktur
    # (yalnızca unix socket üzerinden peer auth çalışır) — mümkünse önce onu dener.
    peer_mode = False
    sifre = ""
    if superuser == "postgres" and ayar.host in ("localhost", "127.0.0.1") and y.komut_var_mi("sudo"):
        if y.basarili_mi(["sudo", "-u", "postgres", "psql", "-tAc", r"\q"]):
            peer_mode = True
            y.bilgi("PostgreSQL'e 'sudo -u postgres psql' (yerel peer auth) ile bağlanılacak, şifre gerekmiyor.")

    if not peer_mode:
        ortam = {**os.environ, "PGPASSWORD": sifre}
        if not y.basarili_mi(
            ["psql", "-h", ayar.host, "-p", ayar.port, "-U", superuser, "-d", "postgres", "-tAc", r"\q"],
            ortam=ortam,
        ):
            sifre = y.sor_sifre("PostgreSQL superuser şifresi (gerekmiyorsa boş bırakın)")

    def psql_calistir(sql: str) -> str:
        if peer_mode:
            return y.cikti(["sudo", "-u", "postgres", "psql", "-tAc", sql])
        ortam = {**os.environ, "PGPASSWORD": sifre}
        return y.cikti(
            ["psql", "-h", ayar.host, "-p", ayar.port, "-U", superuser, "-d", "postgres", "-tAc", sql],
            ortam=ortam,
        )

    if psql_calistir(f"SELECT 1 FROM pg_roles WHERE rolname='{ayar.kullanici}';") == "1":
        y.uyari(f"PostgreSQL kullanıcısı '{ayar.kullanici}' zaten var, atlanıyor.")
    else:
        y.bilgi(f"PostgreSQL kullanıcısı oluşturuluyor: {ayar.kullanici}")
        psql_calistir(f"CREATE USER {ayar.kullanici} WITH PASSWORD '{ayar.sifre}';")
        y.basari("Kullanıcı oluşturuldu.")

    if psql_calistir(f"SELECT 1 FROM pg_database WHERE datname='{ayar.ad}';") == "1":
        y.uyari(f"Veritabanı '{ayar.ad}' zaten var, atlanıyor.")
    else:
        y.bilgi(f"Veritabanı oluşturuluyor: {ayar.ad}")
        psql_calistir(f"CREATE DATABASE {ayar.ad};")
        psql_calistir(f"GRANT ALL PRIVILEGES ON DATABASE {ayar.ad} TO {ayar.kullanici};")
        psql_calistir(f"ALTER DATABASE {ayar.ad} OWNER TO {ayar.kullanici};")
        y.basari("Veritabanı oluşturuldu ve yetkilendirildi.")
