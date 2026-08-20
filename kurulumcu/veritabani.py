"""PostgreSQL veritabanı/kullanıcısı kurulumu — native (sistemde kurulu) veya konteyner (podman/docker)."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

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


def compose_calisir_mi(arac: str) -> bool:
    """`<arac> compose` bir compose sağlayıcı (podman-compose ya da docker'ın
    kendi compose eklentisi) bulup çalışabiliyor mu kontrol eder. Podman'ın
    kendisi kurulu olsa bile compose sağlayıcısı ayrı bir paket olabilir."""
    return y.basarili_mi([arac, "compose", "version"])


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


def _compose_icerik(ayar: DBAyarlari, konteyner_adi: str, volume_adi: str, imaj: str) -> str:
    # DB adı/kullanıcı/şifre gibi kullanıcı girdisi değerler YAML'da özel anlam
    # taşıyan karakterler (:, #, başta *&! vb.) içerebilir. json.dumps'ın ürettiği
    # çift tırnaklı JSON string'i aynı zamanda geçerli bir YAML çift tırnaklı
    # skalerdir (YAML bunu JSON'ın üst kümesi olarak tanımlar) — PyYAML gibi ek
    # bir bağımlılık gerekmeden güvenli kaçışlama sağlar.
    db_adi = json.dumps(ayar.ad)
    kullanici = json.dumps(ayar.kullanici)
    sifre = json.dumps(ayar.sifre)
    saglik_komutu = json.dumps(f"pg_isready -U {ayar.kullanici}")
    return f"""services:
  {konteyner_adi}:
    image: {imaj}
    container_name: {konteyner_adi}
    environment:
      POSTGRES_DB: {db_adi}
      POSTGRES_USER: {kullanici}
      POSTGRES_PASSWORD: {sifre}
    volumes:
      # Resmi postgres imajı 18'den itibaren veriyi doğrudan
      # /var/lib/postgresql/data'ya değil, /var/lib/postgresql altına (sürüm
      # numaralı alt dizinde, pg_ctlcluster tarzı) yazıyor; eski mount noktası
      # "unused mount/volume" hatasıyla reddediliyor.
      # bkz. https://github.com/docker-library/postgres/pull/1259
      - {volume_adi}:/var/lib/postgresql
    ports:
      # Yalnızca localhost'a bağla — sunucuda public IP varsa DB portunun
      # dışarıdan erişilebilir kalmasını önler (uygulama zaten aynı makinede
      # localhost/127.0.0.1 üzerinden bağlanıyor).
      - "127.0.0.1:{ayar.port}:5432"
    restart: always
    healthcheck:
      test: ["CMD-SHELL", {saglik_komutu}]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  {volume_adi}:
    driver: local
"""


def _mevcut_konteyneri_compose_icin_hazirla(arac: str, konteyner_adi: str) -> None:
    """`konteyner_adi` daha önce düz `<arac> run` ile (compose dışında)
    oluşturulmuşsa, compose'un devralabilmesi için kaldırır — veri adlı
    volume'de kaldığından kaybolmaz, yalnızca konteyner nesnesi yeniden
    oluşturulur. compose zaten yönettiği bir konteynere dokunmaz."""
    var_mi = y.cikti([arac, "ps", "-a", "--filter", f"name=^{konteyner_adi}$", "-q"])
    if not var_mi:
        return
    etiket = y.cikti(
        [arac, "inspect", konteyner_adi, "--format", '{{index .Config.Labels "com.docker.compose.project"}}']
    )
    if etiket.strip():
        return  # zaten compose tarafından yönetiliyor, dokunma
    y.uyari(
        f"'{konteyner_adi}' compose dışında (eski 'run' akışıyla) oluşturulmuş; "
        "compose'un devralabilmesi için kaldırılıp yeniden oluşturulacak (veri kalıcı, kaybolmaz)."
    )
    y.calistir([arac, "rm", "-f", konteyner_adi], sessiz=True)


def konteyner_ile_kur(
    arac: str,
    ayar: DBAyarlari,
    proje_dizin: Path,
    paket_yon: str | None,
    imaj: str = VARSAYILAN_IMAJ,
) -> str:
    """Proje köküne bir `docker-compose.yaml` yazıp `<arac> compose up -d` ile
    konteyneri oluşturur/günceller, hazır olmasını bekler ve konteyner adını
    döner. `compose up -d` idempotenttir — zaten var ve güncelse hiçbir şey
    yapmaz, yoksa oluşturur, yapılandırma değiştiyse yeniden oluşturur."""
    konteyner_adi = f"{ayar.ad}_pg"
    volume_adi = f"{ayar.ad}_pg_data"

    if not compose_calisir_mi(arac):
        if not paket_yon:
            y.hata(
                f"'{arac} compose' çalışmıyor (bir compose sağlayıcı kurulu değil) ve otomatik "
                "kurulum için bir paket yöneticisi (apt/dnf) bulunamadı. Elle kurun: "
                "'sudo apt install podman-compose' ya da 'sudo dnf install podman-compose'."
            )
        from . import paket_yoneticisi

        paket_yoneticisi.podman_compose_kur(paket_yon)

    _mevcut_konteyneri_compose_icin_hazirla(arac, konteyner_adi)

    compose_yolu = proje_dizin / "docker-compose.yaml"
    y.bilgi(f"Docker Compose yapılandırması yazılıyor: {compose_yolu}")
    compose_yolu.write_text(_compose_icerik(ayar, konteyner_adi, volume_adi, imaj), encoding="utf-8")
    compose_yolu.chmod(0o600)  # DB şifresini düz metin taşır, .env gibi kısıtlı izinli olmalı

    y.bilgi(f"PostgreSQL konteyneri başlatılıyor: {konteyner_adi} (imaj: {imaj})")
    y.calistir([arac, "compose", "-f", str(compose_yolu), "up", "-d"], sessiz=True)
    y.basari("Konteyner başlatıldı (compose up -d).")

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
        f"Kalıcılık notu: restart: always, {arac} servisi açık olduğu sürece "
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
