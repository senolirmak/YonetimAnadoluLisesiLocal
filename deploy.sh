#!/usr/bin/env bash
# =============================================================================
# Sunucu Güncelleme Scripti
# =============================================================================
# Sunucuda : bash /opt/akalyonetim/deploy.sh
# Uzaktan  : ssh kullanici@sunucu "bash /opt/akalyonetim/deploy.sh"
# =============================================================================

set -euo pipefail

PROJE_DIZIN="/opt/akalyonetim"
VENV="$PROJE_DIZIN/venv"
YEDEK_DIZIN="$PROJE_DIZIN/backups"
SERVIS="gunicorn"

KIRMIZI='\033[0;31m'
YESIL='\033[0;32m'
SARI='\033[1;33m'
MAVI='\033[0;34m'
SIFIRLA='\033[0m'

bilgi()  { echo -e "${MAVI}[BİLGİ]${SIFIRLA}  $*"; }
basari() { echo -e "${YESIL}[TAMAM]${SIFIRLA}  $*"; }
uyari()  { echo -e "${SARI}[UYARI]${SIFIRLA}  $*"; }
hata()   { echo -e "${KIRMIZI}[HATA]${SIFIRLA}   $*" >&2; exit 1; }

cd "$PROJE_DIZIN"

# .env'den DB bilgilerini oku
DB_NAME=$(grep  "^DB_NAME="     .env | cut -d= -f2 | xargs)
DB_USER=$(grep  "^DB_USER="     .env | cut -d= -f2 | xargs)
DB_PASS=$(grep  "^DB_PASSWORD=" .env | cut -d= -f2 | xargs)
DB_HOST=$(grep  "^DB_HOST="     .env | cut -d= -f2 | xargs)
DB_PORT=$(grep  "^DB_PORT="     .env | cut -d= -f2 | xargs)

echo ""
echo -e "${MAVI}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${SIFIRLA}"
echo -e "${MAVI}  Akal Yönetim — Sunucu Güncelleme${SIFIRLA}"
echo -e "${MAVI}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${SIFIRLA}"
echo ""

# ── 1. Veritabanı yedeği (önce al) ───────────────────────────
bilgi "Veritabanı yedeği alınıyor..."
mkdir -p "$YEDEK_DIZIN"
YEDEK_DOSYA="$YEDEK_DIZIN/${DB_NAME}_deploy_$(date +%Y%m%d_%H%M%S).dump"

PGPASSWORD="$DB_PASS" pg_dump -Fc \
    -U "$DB_USER" -h "$DB_HOST" -p "$DB_PORT" "$DB_NAME" \
    > "$YEDEK_DOSYA"

basari "Yedek alındı → $YEDEK_DOSYA"

# ── 2. Servisi durdur ─────────────────────────────────────────
bilgi "Servis durduruluyor..."
sudo systemctl stop "$SERVIS" || uyari "Servis zaten durmuş olabilir."

# ── 3. Kodu güncelle ─────────────────────────────────────────
bilgi "Kod çekiliyor (git pull)..."

if ! git diff --quiet HEAD; then
    bilgi "Yerel değişiklikler stash'leniyor..."
    git stash push -m "deploy-$(date +%Y%m%d_%H%M%S)"
    GIT_STASH_YAPILDI=1
else
    GIT_STASH_YAPILDI=0
fi

git pull origin main
basari "Kod güncellendi."

if [[ "$GIT_STASH_YAPILDI" -eq 1 ]]; then
    if git stash pop 2>/dev/null; then
        bilgi "Yerel değişiklikler geri yüklendi."
    else
        uyari "Stash pop çakışmayla karşılaştı. Manuel kontrol: git stash list"
    fi
fi

# ── 4. Paketleri güncelle ─────────────────────────────────────
bilgi "Paketler güncelleniyor..."
source "$VENV/bin/activate"
pip install -r requirements.txt --quiet
basari "Paketler güncellendi."

# ── 5. Migration ──────────────────────────────────────────────
bilgi "Migration çalıştırılıyor..."
python manage.py migrate --run-syncdb
basari "Migration tamamlandı."

# ── 6. Kullanıcı gruplarını güncelle ─────────────────────────
bilgi "Kullanıcı grupları güncelleniyor..."
python manage.py kullanici_gruplari_olustur
basari "Kullanıcı grupları güncellendi."

# ── 7. Static dosyalar ────────────────────────────────────────
bilgi "Static dosyalar toplanıyor..."
python manage.py collectstatic --noinput --clear -v 0
basari "Static dosyalar güncellendi."

# ── 8. İzinleri düzelt ───────────────────────────────────────
sudo chmod 600 "$PROJE_DIZIN/.env"
sudo chown -R www-data:www-data "$PROJE_DIZIN/staticfiles" 2>/dev/null || true
sudo chown -R www-data:www-data "$PROJE_DIZIN/media"       2>/dev/null || true

# ── 9. Servisi başlat ─────────────────────────────────────────
bilgi "Servis başlatılıyor..."
sudo systemctl start "$SERVIS"
sleep 3

if systemctl is-active --quiet "$SERVIS"; then
    basari "Servis çalışıyor."
else
    hata "Servis başlatılamadı! Loglar: sudo journalctl -u $SERVIS -n 30"
fi

# ── 10. Kritik tablo özeti ────────────────────────────────────
echo ""
bilgi "Kritik tablo kayıt sayıları:"
python - <<'PYEOF'
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from django.db import connection

tablolar = {
    "sinav_sinavbilgisi":           "Sınav Bilgisi",
    "sinav_takvim":                 "Takvim",
    "sinav_takvimuretim":           "Takvim Üretimi",
    "sinav_oturmaplani":            "Oturma Planı",
    "sinav_oturmauretim":           "Oturma Üretimi",
    "sinav_sinavsalonyoklama":      "Salon Yoklama",
    "nobet_mazeret_salon_gorevi":   "Mazeret Salon Görevi",
    "nobet_gorevi":                 "Nöbet Görevi",
    "nobet_gecmis":                 "Nöbet Geçmişi",
}
with connection.cursor() as cur:
    for tablo, ad in tablolar.items():
        try:
            cur.execute(f'SELECT COUNT(*) FROM "{tablo}"')
            sayi = cur.fetchone()[0]
            print(f"  {ad:<26} : {sayi} kayıt")
        except Exception:
            print(f"  {ad:<26} : tablo bulunamadı")
PYEOF

# ── 11. Eski yedekleri temizle (30 günden eski) ───────────────
bilgi "30 günden eski yedekler temizleniyor..."
find "$YEDEK_DIZIN" -name "*.dump" -mtime +30 -delete 2>/dev/null && \
    basari "Eski yedekler temizlendi." || \
    uyari "Yedek temizleme atlandı (dizin boş olabilir)."

echo ""
echo -e "${YESIL}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${SIFIRLA}"
echo -e "${YESIL}  Güncelleme tamamlandı!${SIFIRLA}"
echo -e "${YESIL}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${SIFIRLA}"
echo ""
echo -e "  Yedek dosyası : ${SARI}$YEDEK_DOSYA${SIFIRLA}"
echo -e "  Servis durumu : sudo systemctl status $SERVIS"
echo -e "  Canlı loglar  : sudo journalctl -u $SERVIS -f"
echo ""
