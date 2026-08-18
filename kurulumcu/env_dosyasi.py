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
