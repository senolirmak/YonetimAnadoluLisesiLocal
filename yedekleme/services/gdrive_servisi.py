"""Yedek dosyalarını Google Drive'a (OAuth ile, kişisel Drive hesabına) yükleme servisi.

Felaket kurtarma amaçlıdır: `backups/` dizini sunucunun kendisiyle birlikte
kaybolabileceği için, yedeklerin bir kopyasının site-dışında (Drive'da)
tutulması hedeflenir.

Servis hesapları (service account) KİŞİSEL Google Drive'da depolama kotasına
sahip değildir — bir klasör paylaşılsa bile yükleme "storageQuotaExceeded"
ile başarısız olur (Google Workspace'in Paylaşılan Drive'ları ya da
domain-wide delegation dışında bir yolu yoktur, ikisi de kurumsal/ücretli
hesap gerektirir). Bu yüzden burada OAuth 2.0 "installed app" akışı
kullanılır: yedekler doğrudan SİZİN Drive hesabınıza yüklenir.

Yapılandırma (`.env`):
    YEDEKLEME_GDRIVE_OAUTH_ISTEMCI=/yol/client_secret_....json
        (Google Cloud Console → Credentials → OAuth Client ID → "Masaüstü
        uygulaması" tipinde indirilen dosya)
    YEDEKLEME_GDRIVE_TOKEN=/yol/gdrive-token.json
        (ilk yetkilendirmede otomatik oluşturulur/güncellenir — elle
        oluşturulmaz)
    YEDEKLEME_GDRIVE_KLASOR_ID=<hedef Drive klasörünün ID'si>

Üçü de tanımlı DEĞİLSE ya da token dosyası henüz oluşmadıysa özellik
sessizce devre dışıdır (`aktif_mi()` False döner). İlk kurulumda, tarayıcısı
olan bir makineden BİR KEZ:

    python manage.py gdrive_yetkilendir

çalıştırılıp Google hesabıyla giriş yapılıp izin verilmesi gerekir (bkz.
`oauth_yetkilendir()`); sonrasında token otomatik yenilenir, tekrar tarayıcı
gerekmez — sunucuda headless çalışır. Token sunucuda oluşturulamıyorsa
(tarayıcı yoksa), yerelde oluşturulup `YEDEKLEME_GDRIVE_TOKEN` dosyası
sunucuya kopyalanabilir.

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
    """Yapılandırma tamamsa VE ilk (tarayıcı tabanlı) yetkilendirme daha önce
    yapılıp token dosyası oluşmuşsa True döner."""
    token_yolu = _token_yolu()
    return bool(_oauth_istemci_yolu() and token_yolu and _klasor_id() and Path(token_yolu).is_file())


def _oauth_istemci_yolu() -> str | None:
    return os.getenv("YEDEKLEME_GDRIVE_OAUTH_ISTEMCI") or None


def _token_yolu() -> str | None:
    return os.getenv("YEDEKLEME_GDRIVE_TOKEN") or None


def _klasor_id() -> str | None:
    return os.getenv("YEDEKLEME_GDRIVE_KLASOR_ID") or None


def oauth_yetkilendir() -> Path:
    """Tarayıcı tabanlı, bir kerelik interaktif OAuth akışını başlatır (yerel
    bir geçici sunucu açıp Google'ın izin sayfasına yönlendirir), sonucu
    token dosyasına kaydedip yolunu döner.

    Yalnızca tarayıcısı olan bir makineden çalıştırılabilir — bkz.
    `yedekleme/management/commands/gdrive_yetkilendir.py`.
    """
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as exc:
        raise YedekHatasi(
            "google-auth-oauthlib kurulu değil. 'pip install -r requirements.txt' ile kurun."
        ) from exc

    istemci_yolu = _oauth_istemci_yolu()
    if not istemci_yolu or not Path(istemci_yolu).is_file():
        raise YedekHatasi(
            "YEDEKLEME_GDRIVE_OAUTH_ISTEMCI tanımlı değil ya da dosya bulunamadı. .env dosyasına "
            "Google Cloud Console'dan indirilen client_secret_*.json dosyasının yolunu ekleyin."
        )
    token_yolu = _token_yolu()
    if not token_yolu:
        raise YedekHatasi(
            "YEDEKLEME_GDRIVE_TOKEN tanımlı değil (.env'de token'ın kaydedileceği dosya yolu)."
        )

    akis = InstalledAppFlow.from_client_secrets_file(istemci_yolu, _SCOPES)
    kimlik_bilgileri = akis.run_local_server(port=0)

    hedef = Path(token_yolu)
    hedef.write_text(kimlik_bilgileri.to_json(), encoding="utf-8")
    hedef.chmod(0o600)
    return hedef


def _kimlik_bilgileri_al():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
    except ImportError as exc:
        raise YedekHatasi(
            "Google Drive entegrasyonu için gerekli paketler kurulu değil "
            "(google-auth, google-auth-oauthlib). 'pip install -r requirements.txt' ile kurun."
        ) from exc

    token_yolu = _token_yolu()
    if not token_yolu or not Path(token_yolu).is_file():
        raise YedekHatasi(
            "Google Drive için henüz yetkilendirme yapılmamış. Önce (tarayıcısı olan bir "
            "makineden) 'python manage.py gdrive_yetkilendir' çalıştırın."
        )

    kimlik_bilgileri = Credentials.from_authorized_user_file(token_yolu, _SCOPES)

    if kimlik_bilgileri.expired and kimlik_bilgileri.refresh_token:
        kimlik_bilgileri.refresh(Request())
        Path(token_yolu).write_text(kimlik_bilgileri.to_json(), encoding="utf-8")
        Path(token_yolu).chmod(0o600)

    if not kimlik_bilgileri.valid:
        raise YedekHatasi(
            "Google Drive token'ı geçersiz/süresi dolmuş ve yenilenemedi. "
            "'python manage.py gdrive_yetkilendir' ile yeniden yetkilendirin."
        )
    return kimlik_bilgileri


def _servis_olustur():
    """Drive API v3 istemcisini OAuth kullanıcı kimlik bilgileriyle oluşturur."""
    try:
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise YedekHatasi(
            "Google Drive entegrasyonu için gerekli paketler kurulu değil "
            "(google-api-python-client, google-auth-httplib2). "
            "'pip install -r requirements.txt' ile kurun."
        ) from exc

    return build("drive", "v3", credentials=_kimlik_bilgileri_al(), cache_discovery=False)


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
            "Google Drive yüklemesi yapılandırılmamış ya da henüz yetkilendirilmemiş. "
            ".env dosyasına YEDEKLEME_GDRIVE_OAUTH_ISTEMCI/YEDEKLEME_GDRIVE_TOKEN/"
            "YEDEKLEME_GDRIVE_KLASOR_ID ekleyip 'python manage.py gdrive_yetkilendir' çalıştırın."
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
