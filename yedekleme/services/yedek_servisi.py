"""Veritabanı yedeklerini oluşturma, listeleme, indirme, silme ve geri yükleme servisleri.

`backups/` dizinindeki `*.dump` dosyaları tek kaynak kabul edilir — ayrı bir Django
modeli tutulmaz; böylece `deploy.sh`'in otomatik aldığı yedekler de bu listede
görünür. CLAUDE.md'de belirtildiği gibi bu dosyalar gerçek veritabanı yedekleridir.

PostgreSQL istemci araçları (pg_dump/pg_restore) host'ta kurulu değilse — örn.
PostgreSQL bir Podman/Docker konteynerinde çalışıyorsa (bkz. `kurulumcu/veritabani.py`
konteyner modu, ya da `deploy.sh`'in `podman exec` kullanımı) — `.env` dosyasına
`YEDEKLEME_POSTGRES_KONTEYNER=<konteyner-adı>` eklenerek işlemler doğrudan konteyner
içinde çalıştırılabilir (host'ta pg_dump/pg_restore kurulu olması gerekmez).

Tüm view'lar bu modülü çağırmadan önce yetki kontrolünü (mudur_yardimcisi_required)
yapmış olmalıdır — burada ek bir yetki kontrolü yoktur.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from django.conf import settings

BACKUP_DIR: Path = settings.BASE_DIR / "backups"
ZAMAN_ASIMI_SANIYE = 600  # pg_dump/pg_restore için üst sınır


class YedekHatasi(Exception):
    """Yedekleme/geri yükleme sırasında oluşan, kullanıcıya gösterilebilir hatalar için."""


@dataclass
class YedekDosyasi:
    ad: str
    boyut_mb: float
    olusturma_tarihi: datetime


def _db_ayarlari() -> dict[str, str]:
    db = settings.DATABASES["default"]
    return {
        "ad": db["NAME"],
        "kullanici": db["USER"],
        "sifre": db["PASSWORD"] or "",
        "host": db["HOST"] or "localhost",
        "port": str(db["PORT"] or "5432"),
    }


def _konteyner_adi() -> str | None:
    return os.getenv("YEDEKLEME_POSTGRES_KONTEYNER") or None


def _konteyner_araci() -> str | None:
    zorla = os.getenv("YEDEKLEME_KONTEYNER_ARACI")
    if zorla:
        return zorla
    if shutil.which("podman"):
        return "podman"
    if shutil.which("docker"):
        return "docker"
    # YEDEKLEME_KOMUT_ONEKI tanımlıysa (örn. sandbox'tan host'a çıkmak için
    # 'flatpak-spawn --host'), gerçek podman/docker sandbox'ın PATH'inde hiç
    # görünmeyebilir; bu durumda en yaygın araç olan podman'ı varsayıyoruz —
    # farklıysa YEDEKLEME_KONTEYNER_ARACI ile açıkça belirtilebilir.
    if os.getenv("YEDEKLEME_KOMUT_ONEKI"):
        return "podman"
    return None


def _komut_hazirla(temel_komut: list[str]) -> list[str]:
    """Sandbox'lanmış geliştirme ortamlarında host'a çıkmak için gerekebilecek bir
    komut önekini (örn. 'flatpak-spawn --host') .env'den okuyup öne ekler."""
    onek = os.getenv("YEDEKLEME_KOMUT_ONEKI", "").strip()
    if not onek:
        return temel_komut
    return [*shlex.split(onek), *temel_komut]


def _arac_bulunamadi_mesaji(konteyner: str | None) -> str:
    if konteyner:
        return (
            f"YEDEKLEME_POSTGRES_KONTEYNER='{konteyner}' ayarlanmış ama podman/docker "
            "bulunamadı ya da konteynere erişilemedi. Konteynerin çalıştığından ve "
            "adının doğru olduğundan emin olun."
        )
    return (
        "'pg_dump'/'pg_restore' bulunamadı. PostgreSQL istemci araçlarının kurulu olduğundan "
        "emin olun; PostgreSQL bir konteynerde çalışıyorsa .env dosyasına "
        "YEDEKLEME_POSTGRES_KONTEYNER=<konteyner-adı> ekleyerek doğrudan konteyner içinde "
        "çalıştırılmasını sağlayabilirsiniz."
    )


def guvenli_yol(dosya_adi: str) -> Path:
    """Dosya adını yalnızca backups/ içindeki gerçek bir .dump dosyasına çözer;
    path traversal veya dizin dışına çıkma girişimlerini reddeder."""
    ad = Path(dosya_adi).name  # herhangi bir dizin bileşenini at (../ dahil)
    if not ad.endswith(".dump"):
        raise YedekHatasi("Geçersiz dosya adı.")
    yol = (BACKUP_DIR / ad).resolve()
    if yol.parent != BACKUP_DIR.resolve() or not yol.is_file():
        raise YedekHatasi("Yedek dosyası bulunamadı.")
    return yol


def yedekleri_listele() -> list[YedekDosyasi]:
    BACKUP_DIR.mkdir(exist_ok=True)
    sonuc = []
    for yol in BACKUP_DIR.glob("*.dump"):
        istat = yol.stat()
        sonuc.append(
            YedekDosyasi(
                ad=yol.name,
                boyut_mb=round(istat.st_size / (1024 * 1024), 2),
                olusturma_tarihi=datetime.fromtimestamp(istat.st_mtime),
            )
        )
    return sorted(sonuc, key=lambda y: y.olusturma_tarihi, reverse=True)


def _pg_dump_calistir(hedef: Path, ayar: dict[str, str]) -> None:
    """pg_dump'ı çalıştırıp çıktısını (stdout) hedef dosyaya yazar.

    Konteyner modunda `podman/docker exec` ile konteyner içindeki yerel unix socket
    üzerinden bağlanılır (host/port/şifre gerekmez — deploy.sh'teki çalışan
    yöntemle aynı); native modda TCP + PGPASSWORD kullanılır.
    """
    konteyner = _konteyner_adi()
    if konteyner:
        arac = _konteyner_araci()
        if not arac:
            raise YedekHatasi(_arac_bulunamadi_mesaji(konteyner))
        komut = [arac, "exec", konteyner, "pg_dump", "-U", ayar["kullanici"], "-d", ayar["ad"], "-Fc"]
        ortam = None
    else:
        komut = [
            "pg_dump", "-h", ayar["host"], "-p", ayar["port"],
            "-U", ayar["kullanici"], "-d", ayar["ad"], "-Fc",
        ]
        ortam = {**os.environ, "PGPASSWORD": ayar["sifre"]}

    komut = _komut_hazirla(komut)

    try:
        with open(hedef, "wb") as f:
            sonuc = subprocess.run(
                komut, stdout=f, stderr=subprocess.PIPE, env=ortam, timeout=ZAMAN_ASIMI_SANIYE
            )
    except subprocess.TimeoutExpired as exc:
        raise YedekHatasi(
            f"Yedekleme {ZAMAN_ASIMI_SANIYE} saniyede tamamlanamadı (zaman aşımı)."
        ) from exc
    except FileNotFoundError as exc:
        raise YedekHatasi(_arac_bulunamadi_mesaji(konteyner)) from exc

    if sonuc.returncode != 0:
        hata_metni = sonuc.stderr.decode(errors="replace").strip()
        raise YedekHatasi(f"Yedekleme başarısız oldu: {hata_metni or 'bilinmeyen hata'}")


def yedek_olustur(etiket: str = "web") -> Path:
    """pg_dump ile yeni bir yedek oluşturur ve dosya yolunu döner."""
    BACKUP_DIR.mkdir(exist_ok=True)
    ayar = _db_ayarlari()
    zaman = datetime.now().strftime("%Y%m%d_%H%M%S")
    hedef = BACKUP_DIR / f"{ayar['ad']}_{etiket}_{zaman}.dump"

    try:
        _pg_dump_calistir(hedef, ayar)
    except YedekHatasi:
        hedef.unlink(missing_ok=True)
        raise

    if not hedef.exists() or hedef.stat().st_size == 0:
        hedef.unlink(missing_ok=True)
        raise YedekHatasi("Yedekleme başarısız oldu: çıktı dosyası boş.")

    return hedef


def yedek_sil(dosya_adi: str) -> None:
    yol = guvenli_yol(dosya_adi)
    yol.unlink()


def yedek_geri_yukle(dosya_adi: str) -> None:
    """Seçilen yedeği geri yükler.

    Çağıran view, geri yükleme öncesi doğrulama metnini (DB adı) kontrol etmiş ve
    ayrıca bir güvenlik yedeği (yedek_olustur) almış olmalıdır — bu fonksiyon
    yalnızca fiziksel pg_restore işlemini yapar, ek bir onay/güvenlik adımı içermez.
    """
    yol = guvenli_yol(dosya_adi)
    ayar = _db_ayarlari()

    konteyner = _konteyner_adi()
    if konteyner:
        arac = _konteyner_araci()
        if not arac:
            raise YedekHatasi(_arac_bulunamadi_mesaji(konteyner))
        komut = [
            arac, "exec", "-i", konteyner, "pg_restore",
            "-U", ayar["kullanici"], "-d", ayar["ad"], "--clean", "--if-exists",
        ]
        ortam = None
    else:
        komut = [
            "pg_restore", "-h", ayar["host"], "-p", ayar["port"],
            "-U", ayar["kullanici"], "-d", ayar["ad"], "--clean", "--if-exists",
        ]
        ortam = {**os.environ, "PGPASSWORD": ayar["sifre"]}

    komut = _komut_hazirla(komut)

    try:
        with open(yol, "rb") as f:
            sonuc = subprocess.run(
                komut, stdin=f, stderr=subprocess.PIPE, env=ortam, timeout=ZAMAN_ASIMI_SANIYE
            )
    except subprocess.TimeoutExpired as exc:
        raise YedekHatasi(
            f"Geri yükleme {ZAMAN_ASIMI_SANIYE} saniyede tamamlanamadı (zaman aşımı)."
        ) from exc
    except FileNotFoundError as exc:
        raise YedekHatasi(_arac_bulunamadi_mesaji(konteyner)) from exc

    # pg_restore, --clean ile var olmayan nesneler için zararsız uyarılar da
    # basabilir; yine de dönüş kodu != 0 olduğunda işlemi başarısız kabul ediyoruz.
    if sonuc.returncode != 0:
        hata_metni = sonuc.stderr.decode(errors="replace").strip()
        raise YedekHatasi(f"Geri yükleme hata(lar)la tamamlandı: {hata_metni[-2000:]}")
