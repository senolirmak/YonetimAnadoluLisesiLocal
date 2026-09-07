"""'.env' dosyasını okuma/yazma yardımcıları."""

from __future__ import annotations

from pathlib import Path

SATIR_SIRASI = ["SECRET_KEY", "DEBUG", None, "DB_NAME", "DB_USER", "DB_PASSWORD", "DB_HOST", "DB_PORT"]


def oku(yol: Path) -> dict[str, str]:
    """Var olan bir .env dosyasını basit KEY=VALUE satırları olarak okur; yoksa boş dict döner."""
    degerler: dict[str, str] = {}
    if not yol.is_file():
        return degerler
    for satir in yol.read_text().splitlines():
        satir = satir.strip()
        if not satir or satir.startswith("#") or "=" not in satir:
            continue
        anahtar, _, deger = satir.partition("=")
        degerler[anahtar.strip()] = deger.strip()
    return degerler


def yaz(yol: Path, degerler: dict[str, str]) -> None:
    """SECRET_KEY/DEBUG/DB_*'i sabit sırayla, varsa ALLOWED_HOSTS'u sonuna ekleyerek yazar."""
    satirlar: list[str] = []
    for anahtar in SATIR_SIRASI:
        if anahtar is None:
            satirlar.append("")
        else:
            satirlar.append(f"{anahtar}={degerler[anahtar]}")
    if degerler.get("ALLOWED_HOSTS"):
        satirlar.append(f"ALLOWED_HOSTS={degerler['ALLOWED_HOSTS']}")

    yol.write_text("\n".join(satirlar) + "\n")
    yol.chmod(0o600)


def anahtar_ayarla(yol: Path, anahtar: str, deger: str, *, sudo: bool = False) -> None:
    """Var olan bir .env dosyasında tek bir anahtarı günceller ya da (yoksa)
    sona ekler; diğer satırları ve sırayı korur. `yaz()`'ın aksine sabit bir
    şema varsaymaz — SATIR_SIRASI'nda olmayan anahtarlar (örn.
    YEDEKLEME_POSTGRES_KONTEYNER, HTTPS_ETKIN) için kullanılır. Dosya yoksa
    hiçbir şey yapmaz.

    `sudo=True`: `.env`, servis kullanıcısına devredildikten SONRA (bkz.
    servis_kullanicisi.calisma_zamani_dosyalarini_devret — mod 640, yalnızca
    sahibi `akalsite` yazabilir) çağrılan yerler için ŞARTTIR — kurulumu
    çalıştıran kullanıcı o gruba üye olsa bile bu mod yalnızca OKUMA izni
    verir, yazma denemesi `PermissionError` ile başarısız olur (üretimde
    gerçekten yaşandı: `okulyonetim-kur` adım 6.5'te HTTPS_ETKIN yazarken).
    `sudo tee`, var olan dosyanın sahiplik/izin bitlerine dokunmadan yalnızca
    içeriğini değiştirdiğinden ek bir chmod/chown gerekmez."""
    if not yol.is_file():
        return

    if sudo:
        from . import yardimci as y
        mevcut_icerik = y.cikti(["cat", str(yol)], sudo=True)
    else:
        mevcut_icerik = yol.read_text()

    satirlar = mevcut_icerik.splitlines()
    on_ek = f"{anahtar}="
    for i, satir in enumerate(satirlar):
        if satir.strip().startswith(on_ek):
            satirlar[i] = f"{anahtar}={deger}"
            break
    else:
        satirlar.append(f"{anahtar}={deger}")
    yeni_icerik = "\n".join(satirlar) + "\n"

    if sudo:
        y.calistir(["tee", str(yol)], sudo=True, sessiz=True, girdi=yeni_icerik)
    else:
        yol.write_text(yeni_icerik)
        yol.chmod(0o600)
