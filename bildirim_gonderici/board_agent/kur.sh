#!/usr/bin/env bash
# =============================================================================
# Pardus 23 Sınıf Tahtası Bildirim Ajanı — Kurulum Scripti
# =============================================================================
# Kullanım:
#   sudo bash kur.sh
#
# Seçenekler:
#   sudo bash kur.sh --kaldir    → Ajanı tamamen kaldırır
#   sudo bash kur.sh --durum     → Servis durumunu gösterir
# =============================================================================

set -euo pipefail

# ── Renkler ──────────────────────────────────────────────────
KIRMIZI='\033[0;31m'
YESIL='\033[0;32m'
SARI='\033[1;33m'
MAVI='\033[0;34m'
SIFIRLA='\033[0m'

bilgi()  { echo -e "${MAVI}[BİLGİ]${SIFIRLA}  $*"; }
basari() { echo -e "${YESIL}[TAMAM]${SIFIRLA}  $*"; }
uyari()  { echo -e "${SARI}[UYARI]${SIFIRLA}  $*"; }
hata()   { echo -e "${KIRMIZI}[HATA]${SIFIRLA}   $*" >&2; exit 1; }

# ── Yapılandırma ─────────────────────────────────────────────
AJAN_DIZIN="/opt/tahta_agent"
AJAN_DOSYA="$AJAN_DIZIN/agent.py"
SIFRELER_DIZIN="/etc/tahta_agent"
SIFRELER_DOSYA="$SIFRELER_DIZIN/secrets"
SERVIS_ADI="tahta_agent"
SERVIS_DOSYA="/etc/systemd/system/${SERVIS_ADI}.service"
LOG_DOSYA="/var/log/tahta_agent.log"
DINLEME_PORTU="8765"
SCRIPT_DIZIN="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DOSYA="$SCRIPT_DIZIN/config.txt"

# ── USB'deki config.txt'den değerleri oku ────────────────────
SUNUCU_IP=""
if [[ -f "$CONFIG_DOSYA" ]]; then
    SUNUCU_IP=$(grep -E "^SUNUCU_IP=" "$CONFIG_DOSYA" | cut -d'=' -f2 | xargs)
    bilgi "config.txt okundu → SUNUCU_IP=$SUNUCU_IP" 2>/dev/null || true
fi

# ── Root kontrolü ─────────────────────────────────────────────
[[ $EUID -ne 0 ]] && hata "Bu script root yetkisiyle çalıştırılmalıdır: sudo bash $0"

# ── Argüman işleme ───────────────────────────────────────────
EYLEM="${1:-kur}"

# ── UFW yardımcıları ─────────────────────────────────────────
ufw_kur_ve_yapilandir() {
    local sunucu_ip="$1"

    bilgi "UFW kuruluyor..."
    apt-get install -y -qq ufw 2>/dev/null
    basari "UFW kuruldu."

    # Mevcut port 8765 kurallarını temizle (yeniden çalıştırmaya karşı)
    ufw delete allow "$DINLEME_PORTU/tcp" 2>/dev/null || true
    ufw delete deny  "$DINLEME_PORTU/tcp" 2>/dev/null || true
    ufw delete allow from "$sunucu_ip" to any port "$DINLEME_PORTU" proto tcp 2>/dev/null || true

    # Yeni kuralları ekle
    ufw allow from "$sunucu_ip" to any port "$DINLEME_PORTU" proto tcp comment "Okul sunucusu bildirim ajanı"
    ufw deny "$DINLEME_PORTU/tcp" comment "Diğer tüm kaynaklardan kapat"

    # UFW daha önce devre dışıysa etkinleştir
    if ! ufw status | grep -q "Status: active"; then
        # SSH kuralını ekle — bağlantı kesilmesin
        ufw allow OpenSSH 2>/dev/null || ufw allow 22/tcp 2>/dev/null || true
        echo "y" | ufw enable
        basari "UFW etkinleştirildi."
    else
        ufw reload
        basari "UFW kuralları güncellendi."
    fi

    bilgi "Aktif UFW kuralları:"
    ufw status numbered
}

# ─────────────────────────────────────────────────────────────
kaldir() {
    bilgi "Ajan kaldırılıyor..."
    systemctl stop  "$SERVIS_ADI" 2>/dev/null || true
    systemctl disable "$SERVIS_ADI" 2>/dev/null || true
    rm -f "$SERVIS_DOSYA"
    systemctl daemon-reload
    rm -rf "$AJAN_DIZIN"
    # secrets dosyasını silmeden bırak (yeniden kurulumda kullanılabilir)
    uyari "Gizli anahtar dosyası $SIFRELER_DOSYA silinmedi."
    uyari "Manuel silmek için: sudo rm -rf $SIFRELER_DIZIN"
    basari "Ajan kaldırıldı."
    exit 0
}

durum() {
    echo ""
    systemctl status "$SERVIS_ADI" --no-pager || true
    echo ""
    bilgi "Son log satırları:"
    journalctl -u "$SERVIS_ADI" -n 20 --no-pager 2>/dev/null || tail -20 "$LOG_DOSYA" 2>/dev/null || true
    exit 0
}

[[ "$EYLEM" == "--kaldir" ]] && kaldir
[[ "$EYLEM" == "--durum"  ]] && durum

# ─────────────────────────────────────────────────────────────
# KURULUM
# ─────────────────────────────────────────────────────────────
echo ""
echo -e "${MAVI}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${SIFIRLA}"
echo -e "${MAVI}  Sınıf Tahtası Bildirim Ajanı — Kurulum${SIFIRLA}"
echo -e "${MAVI}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${SIFIRLA}"
echo ""

# 1. Bağımlılıklar
bilgi "Bağımlılıklar kontrol ediliyor..."
apt-get update -qq
apt-get install -y -qq libnotify-bin python3 2>/dev/null
basari "libnotify-bin ve python3 hazır."

# 2. Ajan dizini
bilgi "Ajan dizini oluşturuluyor: $AJAN_DIZIN"
mkdir -p "$AJAN_DIZIN"

# 3. agent.py kopyala (script ile aynı dizinden)
SCRIPT_DIZIN="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$SCRIPT_DIZIN/agent.py" ]]; then
    cp "$SCRIPT_DIZIN/agent.py" "$AJAN_DOSYA"
    chmod 755 "$AJAN_DOSYA"
    basari "agent.py kopyalandı → $AJAN_DOSYA"
else
    hata "agent.py bulunamadı. kur.sh ile aynı dizinde olmalıdır."
fi

# 4. Gizli anahtar
mkdir -p "$SIFRELER_DIZIN"
if [[ -f "$SIFRELER_DOSYA" ]]; then
    uyari "$SIFRELER_DOSYA zaten mevcut, üzerine yazılmıyor."
    uyari "Anahtarı güncellemek için: sudo nano $SIFRELER_DOSYA"
else
    # Mevcut değer yoksa kullanıcıdan iste
    echo ""
    echo -e "${SARI}Gizli anahtar giriniz (Django settings.py'deki BILDIRIM_ANAHTAR ile aynı olmalı):${SIFIRLA}"
    read -r -s -p "GIZLI_ANAHTAR= " GIZLI_ANAHTAR_DEGERI
    echo ""
    [[ -z "$GIZLI_ANAHTAR_DEGERI" ]] && hata "Gizli anahtar boş bırakılamaz."

    cat > "$SIFRELER_DOSYA" <<EOF
GIZLI_ANAHTAR=${GIZLI_ANAHTAR_DEGERI}
DINLEME_PORTU=${DINLEME_PORTU}
MASAUSTU_UID=1000
EOF
    chmod 600 "$SIFRELER_DOSYA"
    chown root:root "$SIFRELER_DOSYA"
    basari "Gizli anahtar kaydedildi → $SIFRELER_DOSYA (izin: 600)"
fi

# 5. Log dosyası
touch "$LOG_DOSYA"
chmod 640 "$LOG_DOSYA"
basari "Log dosyası hazır → $LOG_DOSYA"

# 6. Systemd servis dosyası
bilgi "Systemd servis dosyası oluşturuluyor..."
cat > "$SERVIS_DOSYA" <<EOF
[Unit]
Description=Okul Tahtası Bildirim Ajanı
After=network.target graphical-session.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 ${AJAN_DOSYA}
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
User=root
EnvironmentFile=${SIFRELER_DOSYA}

[Install]
WantedBy=multi-user.target
EOF
chmod 644 "$SERVIS_DOSYA"
basari "Servis dosyası oluşturuldu → $SERVIS_DOSYA"

# 7. Servisi etkinleştir ve başlat
bilgi "Servis etkinleştiriliyor ve başlatılıyor..."
systemctl daemon-reload
systemctl enable "$SERVIS_ADI"
systemctl restart "$SERVIS_ADI"

sleep 2

# 8. Durum kontrolü
if systemctl is-active --quiet "$SERVIS_ADI"; then
    basari "Servis çalışıyor."
else
    uyari "Servis başlatılamadı. Log kontrol edin:"
    journalctl -u "$SERVIS_ADI" -n 15 --no-pager
    exit 1
fi

# 9. UFW yapılandırması
echo ""
echo -e "${MAVI}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${SIFIRLA}"
echo -e "${MAVI}  Güvenlik Duvarı (UFW) Yapılandırması${SIFIRLA}"
echo -e "${MAVI}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${SIFIRLA}"
echo ""
echo -e "  Port ${DINLEME_PORTU} yalnızca okul sunucusundan gelen bağlantılara açılacak."
echo -e "  Sunucunun giden trafiği için ek kural gerekmez (varsayılan: açık)."
echo ""

if [[ -n "$SUNUCU_IP" ]]; then
    bilgi "Sunucu IP config.txt'den okundu: ${SARI}$SUNUCU_IP${SIFIRLA}"
    echo -e "  Değiştirmek için Enter'a basın, onaylamak için doğrudan Enter'a basın:"
    read -r -p "  Sunucu IP [$SUNUCU_IP]: " GIRDI
    [[ -n "$GIRDI" ]] && SUNUCU_IP="$GIRDI"
else
    echo -e "${SARI}config.txt bulunamadı veya SUNUCU_IP tanımlı değil.${SIFIRLA}"
    echo -e "${SARI}Okul sunucusunun IP adresini girin (ör: 192.168.1.10):${SIFIRLA}"
    read -r -p "Sunucu IP: " SUNUCU_IP
fi

# Basit IPv4 format kontrolü
if [[ ! "$SUNUCU_IP" =~ ^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$ ]]; then
    uyari "Geçersiz IP formatı. UFW yapılandırması atlandı."
    uyari "Manuel yapılandırma için:"
    echo "  sudo ufw allow from <SUNUCU_IP> to any port ${DINLEME_PORTU} proto tcp"
    echo "  sudo ufw deny ${DINLEME_PORTU}/tcp"
    echo "  sudo ufw enable"
else
    ufw_kur_ve_yapilandir "$SUNUCU_IP"
    basari "UFW yapılandırması tamamlandı."
    echo ""
    echo -e "  ✓ ${YESIL}İzin verilen${SIFIRLA}: ${SUNUCU_IP} → port ${DINLEME_PORTU}/tcp"
    echo -e "  ✗ ${KIRMIZI}Engellenen${SIFIRLA} : Diğer tüm kaynaklar → port ${DINLEME_PORTU}/tcp"
    echo -e "  ℹ Sunucu gideni: Kural gerekmez (UFW varsayılan: izin)"
fi

echo ""
echo -e "${YESIL}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${SIFIRLA}"
echo -e "${YESIL}  Kurulum tamamlandı!${SIFIRLA}"
echo -e "${YESIL}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${SIFIRLA}"
echo ""
echo "  Servis durumu : sudo bash kur.sh --durum"
echo "  Servisi durdur: sudo systemctl stop  $SERVIS_ADI"
echo "  Servisi başlat: sudo systemctl start $SERVIS_ADI"
echo "  Kaldır        : sudo bash kur.sh --kaldir"
echo ""
