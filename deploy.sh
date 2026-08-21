#!/usr/bin/env bash
# =============================================================================
# Sunucu Güncelleme Scripti
# =============================================================================
# Sunucuda : bash /srv/akalyonetim/deploy.sh
# Uzaktan  : ssh kullanici@sunucu "bash /srv/akalyonetim/deploy.sh"
# =============================================================================
# git pull doğrulama notu: bu satır yalnızca sunucuda 'git pull'un yeni commit'i
# çektiğini teyit etmek için eklendi (2026-08-21).

set -euo pipefail

PROJE_DIZIN="/srv/akalyonetim"
VENV="$PROJE_DIZIN/venv"
YEDEK_DIZIN="$PROJE_DIZIN/backups"

SERVIS="akalyonetim.service"

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
# .env, servis kullanıcısına (akalsite, mod 640) sahiptir — bu betiği çalıştıran
# kullanıcı (senolirmak) akalsite grubunun üyesi olsa da, aşağıdaki tek satırlık
# alt-kabuk çağrılarında grup üyeliğinin oturuma yansımış olduğuna güvenmemek
# için burada da sudo kullanılıyor — bkz.
# kurulumcu/servis_kullanicisi.py: calisma_zamani_dosyalarini_devret().

DB_NAME=$(sudo grep "^DB_NAME=" .env | cut -d= -f2- | xargs)
DB_USER=$(sudo grep "^DB_USER=" .env | cut -d= -f2- | xargs)
DB_PASSWORD=$(sudo grep "^DB_PASSWORD=" .env | cut -d= -f2- | xargs)
DB_HOST=$(sudo grep "^DB_HOST=" .env | cut -d= -f2- | xargs)
DB_PORT=$(sudo grep "^DB_PORT=" .env | cut -d= -f2- | xargs)

# kurulumcu, PostgreSQL konteynerini "<DB_NAME>_pg" adıyla oluşturur (bkz.
# kurulumcu/veritabani.py). .env'de YEDEKLEME_POSTGRES_KONTEYNER tanımlıysa
# (yedekleme app'inin de kullandığı aynı override) o değer önceliklidir.
POSTGRES_CONTAINER=$(sudo grep "^YEDEKLEME_POSTGRES_KONTEYNER=" .env 2>/dev/null | cut -d= -f2- | xargs || true)
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-${DB_NAME}_pg}"

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

# backups/, bu betiği çalıştıran kullanıcı (senolirmak) İLE servis kullanıcısının
# (akalsite, web üzerinden yedek al/geri yükle) İKİSİNİN de yazması gereken
# PAYLAŞILAN bir dizindir. Hangi taraf önce oluşturursa oluştursun diğeri de
# yazabilsin diye setgid + ortak grup (akalsite) burada garanti ediliyor — bkz.
# kurulumcu/servis_kullanicisi.py: paylasilan_yedek_dizinini_hazirla() (kurulumcu
# normalde bunu zaten yapar; burada tekrarlanması yalnızca eski bir kurulumdan
# kalan yanlış izinlere karşı savunma amaçlıdır).
sudo mkdir -p "$YEDEK_DIZIN"
sudo chgrp akalsite "$YEDEK_DIZIN"
sudo chmod 2770 "$YEDEK_DIZIN"

YEDEK_DOSYA="$YEDEK_DIZIN/${DB_NAME}_deploy_$(date +%Y%m%d_%H%M%S).dump"

# pg_dump'ı konteynere 'exec' ile girmeden, host'a açık TCP portu üzerinden
# çalıştırıyoruz — yedekleme/services/yedek_servisi.py'deki (akalsite için
# podman erişimi hiç verilmeyen) aynı yaklaşım; host'ta pg_dump'ın kurulu ve
# sunucuyla aynı/daha yeni sürümde olması kurulumcu tarafından garanti edilir
# (bkz. kurulumcu/veritabani.py: istemci_araclarini_dogrula).
#
# Çıktı düz '>' yerine 'sudo tee' ile yazılıyor: yukarıdaki chgrp/chmod doğru
# olsa bile, senolirmak'ın akalsite grubuna üyeliği yalnızca YENİ bir oturumda
# (yeniden SSH bağlantısında) etkinleşir — bu betik eski bir oturumda
# çalıştırılıyorsa düz '>' yine "Erişim engellendi" verebilirdi; sudo bu
# belirsizliğe hiç bağımlı değildir.
PGPASSWORD="$DB_PASSWORD" pg_dump \
    -h "${DB_HOST:-127.0.0.1}" \
    -p "${DB_PORT:-5432}" \
    -U "$DB_USER" \
    -d "$DB_NAME" \
    -Fc \
    | sudo tee "$YEDEK_DOSYA" > /dev/null
sudo chown senolirmak:akalsite "$YEDEK_DOSYA"

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
# collectstatic --clear önce staticfiles/ içindeki ESKİ dosyaları siler — bu
# betiği çalıştıran kullanıcının (senolirmak) o an dizine yazma izni olduğundan
# emin olunmalı; aşağıdaki adım 10'daki chown bunu yalnızca collectstatic'ten
# SONRA garanti eder, bu yüzden aynısı burada da (işlemden önce) tekrarlanıyor
# (bkz. backups/ için adım 2'deki aynı desen).
sudo mkdir -p "$PROJE_DIZIN/staticfiles"
sudo chown -R senolirmak:senolirmak "$PROJE_DIZIN/staticfiles"

bilgi "Static dosyalar toplanıyor..."
python manage.py collectstatic --noinput --clear -v 0 --settings=config.settings.production
basari "Static dosyalar güncellendi."

# ── 9. Nginx reload ──────────────────────────────────────────
bilgi "Nginx yeniden yükleniyor..."
sudo systemctl reload nginx || uyari "Nginx reload atlandı."
basari "Nginx yeniden yüklendi."

# ── 10. İzinleri düzelt ───────────────────────────────────────

bilgi "Dosya izinleri düzenleniyor..."

# .env yalnızca servis kullanıcısı (akalsite) ve onun grubu tarafından
# okunabilsin — deploy'u çalıştıran kullanıcı (senolirmak) bu grubun üyesidir,
# bkz. kurulumcu/servis_kullanicisi.py: servis_kullanicisini_hazirla/
# calisma_zamani_dosyalarini_devret.
sudo chmod 640 "$PROJE_DIZIN/.env"
sudo chown akalsite:akalsite "$PROJE_DIZIN/.env"

# staticfiles bu betiği (senolirmak) çalıştıran kullanıcı tarafından üretiliyor
# (adım 8, collectstatic); media/ ise çalışma zamanında Gunicorn'un altında
# çalıştığı servis kullanıcısı (akalsite) tarafından yazılıyor.
sudo chown -R senolirmak:senolirmak "$PROJE_DIZIN/staticfiles" 2>/dev/null || true
sudo chown -R akalsite:www-data "$PROJE_DIZIN/media" 2>/dev/null || true
sudo chmod g+s "$PROJE_DIZIN/media" 2>/dev/null || true

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
