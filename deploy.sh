#!/usr/bin/env bash
# =============================================================================
# Sunucu Güncelleme Scripti
# =============================================================================
# Sunucuda : bash /srv/akalyonetim/deploy.sh
# Uzaktan  : ssh kullanici@sunucu "bash /srv/akalyonetim/deploy.sh"
# =============================================================================

set -euo pipefail

PROJE_DIZIN="/srv/akalyonetim"
VENV="$PROJE_DIZIN/.venv"
YEDEK_DIZIN="$PROJE_DIZIN/backups"

SERVIS="akalyonetim.service"
POSTGRES_CONTAINER="postgresql"

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

# ─────────────────────────────────────────────────────────────
# .env'den DB bilgilerini oku
# ─────────────────────────────────────────────────────────────

DB_NAME=$(grep "^DB_NAME=" .env | cut -d= -f2- | xargs)
DB_USER=$(grep "^DB_USER=" .env | cut -d= -f2- | xargs)

echo ""
echo -e "${MAVI}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${SIFIRLA}"
echo -e "${MAVI}  Akal Yönetim — Sunucu Güncelleme${SIFIRLA}"
echo -e "${MAVI}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${SIFIRLA}"
echo ""

# ─────────────────────────────────────────────────────────────
# 1. Ön kontroller
# ─────────────────────────────────────────────────────────────

bilgi "Sunucu bileşenleri kontrol ediliyor..."

[[ -d "$PROJE_DIZIN" ]] || hata "Proje dizini bulunamadı: $PROJE_DIZIN"
[[ -d "$VENV" ]] || hata "Python sanal ortamı bulunamadı: $VENV"
[[ -f "$PROJE_DIZIN/.env" ]] || hata ".env dosyası bulunamadı"

command -v podman >/dev/null 2>&1 \
    || hata "Podman bulunamadı."

podman container exists "$POSTGRES_CONTAINER" \
    || hata "PostgreSQL container bulunamadı: $POSTGRES_CONTAINER"

[[ -n "$(podman ps --filter "name=^${POSTGRES_CONTAINER}$" --filter status=running -q)" ]] \
    || hata "PostgreSQL container çalışmıyor: $POSTGRES_CONTAINER"

basari "Ön kontroller tamamlandı."

# ─────────────────────────────────────────────────────────────
# 2. Veritabanı yedeği
# ─────────────────────────────────────────────────────────────

bilgi "Veritabanı yedeği alınıyor..."

mkdir -p "$YEDEK_DIZIN"

YEDEK_DOSYA="$YEDEK_DIZIN/${DB_NAME}_deploy_$(date +%Y%m%d_%H%M%S).dump"

podman exec "$POSTGRES_CONTAINER" \
    pg_dump \
    -U "$DB_USER" \
    -d "$DB_NAME" \
    -Fc \
    > "$YEDEK_DOSYA"

if [[ ! -s "$YEDEK_DOSYA" ]]; then
    rm -f "$YEDEK_DOSYA"
    hata "Veritabanı yedeği oluşturulamadı."
fi

basari "Veritabanı yedeği oluşturuldu:"
echo "        $YEDEK_DOSYA"
echo "        Boyut: $(du -h "$YEDEK_DOSYA" | cut -f1)"

# ── 3. Servisi durdur ─────────────────────────────────────────
bilgi "Servis durduruluyor..."
sudo systemctl stop "$SERVIS" || uyari "Servis zaten durmuş olabilir."

# ── 4. Kodu güncelle ─────────────────────────────────────────
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
        hata "Stash pop çakışmayla karşılaştı, repo tutarsız durumda. Manuel kontrol: git status / git stash list"
    fi
fi

# ── 5. Paketleri güncelle ─────────────────────────────────────
bilgi "Paketler güncelleniyor..."
source "$VENV/bin/activate"
pip install -r requirements.txt --quiet
basari "Paketler güncellendi."

# ── 6. Migration ──────────────────────────────────────────────
bilgi "Migration çalıştırılıyor..."
python manage.py migrate --run-syncdb --settings=config.settings.production
basari "Migration tamamlandı."

# ── 7. Kullanıcı gruplarını güncelle ─────────────────────────
bilgi "Kullanıcı grupları güncelleniyor..."
python manage.py kullanici_gruplari_olustur --settings=config.settings.production
basari "Kullanıcı grupları güncellendi."

# ── 8. Static dosyalar ────────────────────────────────────────
bilgi "Static dosyalar toplanıyor..."
python manage.py collectstatic --noinput --clear -v 0 --settings=config.settings.production
basari "Static dosyalar güncellendi."

# ── 9. Nginx reload ──────────────────────────────────────────
bilgi "Nginx yeniden yükleniyor..."
sudo systemctl reload nginx || uyari "Nginx reload atlandı."
basari "Nginx yeniden yüklendi."

# ── 10. İzinleri düzelt ───────────────────────────────────────

bilgi "Dosya izinleri düzenleniyor..."

# .env yalnızca uygulama kullanıcısı tarafından okunabilsin
sudo chmod 600 "$PROJE_DIZIN/.env"
sudo chown senolirmak:senolirmak "$PROJE_DIZIN/.env"

# Static ve media dosyalarının sahibi uygulama kullanıcısı
sudo chown -R senolirmak:senolirmak "$PROJE_DIZIN/staticfiles" 2>/dev/null || true
sudo chown -R senolirmak:senolirmak "$PROJE_DIZIN/media" 2>/dev/null || true

# Nginx'in okuyabilmesi için dizinleri erişilebilir yap
sudo find "$PROJE_DIZIN/staticfiles" -type d -exec chmod 755 {} \; 2>/dev/null || true
sudo find "$PROJE_DIZIN/staticfiles" -type f -exec chmod 644 {} \; 2>/dev/null || true

sudo find "$PROJE_DIZIN/media" -type d -exec chmod 755 {} \; 2>/dev/null || true
sudo find "$PROJE_DIZIN/media" -type f -exec chmod 644 {} \; 2>/dev/null || true

basari "Dosya izinleri düzenlendi."

# ── 11. Servisi başlat ────────────────────────────────────────
bilgi "Servis başlatılıyor..."
sudo systemctl start "$SERVIS"
sleep 3

if systemctl is-active --quiet "$SERVIS"; then
    basari "Servis çalışıyor."
else
    hata "Servis başlatılamadı! Loglar: sudo journalctl -u $SERVIS -n 30"
fi

# ── 12. Kritik tablo özeti ────────────────────────────────────
echo ""
bilgi "Kritik tablo kayıt sayıları:"
python - <<'PYEOF'
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')
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
    "sorumluluk_sorumlusinav":      "Sorumlu Sınav",
    "sorumluluk_sorumluogrenci":    "Sorumlu Öğrenci",
    "sorumluluk_sorumlutakvim":     "Sorumlu Takvim",
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

# ── 13. Eski yedekleri temizle (30 günden eski) ───────────────
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
