"""Yedek dosyalarını Google Drive'a (bir servis hesabı ile) yükleme servisi.

Felaket kurtarma amaçlıdır: `backups/` dizini sunucunun kendisiyle birlikte
kaybolabileceği için, yedeklerin bir kopyasının site-dışında (Drive'da)
tutulması hedeflenir.

Yapılandırma (`.env`):
    YEDEKLEME_GDRIVE_SA_ANAHTARI=/yol/servis-hesabi.json
    YEDEKLEME_GDRIVE_KLASOR_ID=<paylaşılan Drive klasörünün ID'si>

İkisi de tanımlı değilse özellik sessizce devre dışıdır (`aktif_mi()` False
döner) — hata fırlatmaz, var olan yedekleme akışını etkilemez. Servis hesabı,
hedef klasörle en az "İçerik Yöneticisi/Düzenleyen" olarak paylaşılmış
olmalıdır; aksi halde yükleme 403 ile başarısız olur.

Aynı ada sahip bir dosya klasörde zaten varsa üzerine yazılır (yeni bir
kopya oluşturulmaz) — böylece tekrar tekrar yüklemek (otomatik + manuel)
Drive'da çoğalmaya yol açmaz.
"""

from __future__ import annotations

import os
from pathlib import Path

from .yedek_servisi import YedekHatasi

_SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def aktif_mi() -> bool:
    """Google Drive yüklemesi için gereken iki .env değişkeni de tanımlı mı."""
    return bool(_sa_anahtar_yolu() and _klasor_id())


def _sa_anahtar_yolu() -> str | None:
    return os.getenv("YEDEKLEME_GDRIVE_SA_ANAHTARI") or None


def _klasor_id() -> str | None:
    return os.getenv("YEDEKLEME_GDRIVE_KLASOR_ID") or None


def _servis_olustur():
    """Drive API v3 istemcisini servis hesabı kimlik bilgileriyle oluşturur."""
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise YedekHatasi(
            "Google Drive entegrasyonu için gerekli paketler kurulu değil "
            "(google-api-python-client, google-auth, google-auth-httplib2). "
            "'pip install -r requirements.txt' ile kurun."
        ) from exc

    anahtar_yolu = _sa_anahtar_yolu()
    if not anahtar_yolu or not Path(anahtar_yolu).is_file():
        raise YedekHatasi(f"Google Drive servis hesabı anahtar dosyası bulunamadı: {anahtar_yolu}")

    try:
        kimlik_bilgileri = service_account.Credentials.from_service_account_file(
            anahtar_yolu, scopes=_SCOPES
        )
    except Exception as exc:
        raise YedekHatasi(f"Servis hesabı anahtar dosyası okunamadı/geçersiz: {exc}") from exc

    return build("drive", "v3", credentials=kimlik_bilgileri, cache_discovery=False)


def _var_olan_dosya_id(servis, ad: str, klasor_id: str) -> str | None:
    ad_kacisli = ad.replace("'", "\\'")
    sorgu = f"name = '{ad_kacisli}' and '{klasor_id}' in parents and trashed = false"
    sonuc = servis.files().list(q=sorgu, fields="files(id)", pageSize=1).execute()
    dosyalar = sonuc.get("files", [])
    return dosyalar[0]["id"] if dosyalar else None


def yedek_yukle(yol: Path) -> str:
    """`yol`'daki dosyayı yapılandırılmış Drive klasörüne yükler (varsa
    üzerine yazar). Başarılı olursa Drive dosya ID'sini döner. `resumable=True`
    ile büyük dosyalarda parça parça (chunk chunk) yüklenir."""
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    if not aktif_mi():
        raise YedekHatasi(
            "Google Drive yüklemesi yapılandırılmamış. .env dosyasına "
            "YEDEKLEME_GDRIVE_SA_ANAHTARI ve YEDEKLEME_GDRIVE_KLASOR_ID ekleyin."
        )
    if not yol.is_file():
        raise YedekHatasi(f"Yüklenecek dosya bulunamadı: {yol}")

    servis = _servis_olustur()
    klasor_id = _klasor_id()
    medya = MediaFileUpload(str(yol), mimetype="application/octet-stream", resumable=True)

    try:
        mevcut_id = _var_olan_dosya_id(servis, yol.name, klasor_id)
        if mevcut_id:
            sonuc = servis.files().update(fileId=mevcut_id, media_body=medya).execute()
        else:
            meta = {"name": yol.name, "parents": [klasor_id]}
            sonuc = servis.files().create(body=meta, media_body=medya, fields="id").execute()
    except HttpError as exc:
        raise YedekHatasi(f"Google Drive'a yükleme başarısız oldu: {exc}") from exc

    return sonuc["id"]
