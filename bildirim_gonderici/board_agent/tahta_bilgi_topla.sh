#!/usr/bin/env bash
# =============================================================================
# Tahta Bilgi Toplayıcı
# =============================================================================
# USB'den çalıştırılır. Her tahtada bir kez çalıştırılarak sinif_sube, ip_adresi,
# port ve hostname bilgilerini USB kökündeki tahtalar.csv dosyasına ekler.
#
# Kullanım:
#   bash tahta_bilgi_topla.sh
# =============================================================================

set -euo pipefail

# ── Renkler ──────────────────────────────────────────────────
YESIL='\033[0;32m'
SARI='\033[1;33m'
MAVI='\033[0;34m'
KIRMIZI='\033[0;31m'
SIFIRLA='\033[0m'

bilgi()  { echo -e "${MAVI}[BİLGİ]${SIFIRLA}  $*"; }
basari() { echo -e "${YESIL}[TAMAM]${SIFIRLA}  $*"; }
uyari()  { echo -e "${SARI}[UYARI]${SIFIRLA}  $*"; }
hata()   { echo -e "${KIRMIZI}[HATA]${SIFIRLA}   $*" >&2; exit 1; }

# ── CSV dosyası scriptin bulunduğu dizinde (USB kökü) ─────────
SCRIPT_DIZIN="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CSV_DOSYA="$SCRIPT_DIZIN/tahtalar.csv"
VARSAYILAN_PORT="8765"

# ─────────────────────────────────────────────────────────────
echo ""
echo -e "${MAVI}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${SIFIRLA}"
echo -e "${MAVI}  Tahta Bilgi Toplayıcı${SIFIRLA}"
echo -e "${MAVI}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${SIFIRLA}"
echo ""

# ── Otomatik bilgileri topla ─────────────────────────────────

# IP adresi: varsayılan rotada kullanılan arayüzün IP'si
IP_ADRESI=$(ip route get 1.1.1.1 2>/dev/null \
    | awk 'NR==1 {for(i=1;i<=NF;i++) if($i=="src") {print $(i+1); exit}}')

# Fallback: ilk non-loopback IP
if [[ -z "$IP_ADRESI" ]]; then
    IP_ADRESI=$(hostname -I 2>/dev/null | awk '{print $1}')
fi
[[ -z "$IP_ADRESI" ]] && IP_ADRESI="BULUNAMADI"

HOSTNAME=$(hostname 2>/dev/null || echo "BULUNAMADI")

bilgi "Hostname : $HOSTNAME"
bilgi "IP Adresi: $IP_ADRESI"
bilgi "Port     : $VARSAYILAN_PORT"
echo ""

# ── Sınıf/Şube bilgisini kullanıcıdan al ─────────────────────
while true; do
    echo -e "${SARI}Bu tahtanın bulunduğu sınıf/şubeyi girin (örn: 9/A, 10/B, 11/C):${SIFIRLA}"
    read -r -p "Sınıf/Şube: " SINIF_SUBE
    SINIF_SUBE="$(echo "$SINIF_SUBE" | xargs)"   # boşlukları temizle

    if [[ -z "$SINIF_SUBE" ]]; then
        uyari "Sınıf/şube boş bırakılamaz, tekrar deneyin."
        continue
    fi

    # Sınıf/şubenin CSV'de zaten kayıtlı olup olmadığını kontrol et
    if [[ -f "$CSV_DOSYA" ]] && grep -q "^\"$SINIF_SUBE\"," "$CSV_DOSYA" 2>/dev/null; then
        echo ""
        uyari "'$SINIF_SUBE' zaten CSV dosyasında kayıtlı:"
        grep "^\"$SINIF_SUBE\"," "$CSV_DOSYA"
        echo ""
        echo -e "${SARI}Üzerine yazmak ister misiniz? (e/H):${SIFIRLA}"
        read -r -p "" CEVAP
        if [[ "${CEVAP,,}" == "e" ]]; then
            # Mevcut satırı sil
            TMP=$(mktemp)
            grep -v "^\"$SINIF_SUBE\"," "$CSV_DOSYA" > "$TMP" && mv "$TMP" "$CSV_DOSYA"
            break
        else
            uyari "İşlem iptal edildi. Başka bir sınıf/şube girin."
            continue
        fi
    fi
    break
done

# Virgül içeriyorsa çift tırnak içine al (CSV standardı)
_csv_alan() {
    local deger="$1"
    if [[ "$deger" == *","* || "$deger" == *'"'* ]]; then
        deger="${deger//\"/\"\"}"
        echo "\"$deger\""
    else
        echo "\"$deger\""
    fi
}

SATIR="$(_csv_alan "$SINIF_SUBE"),$(_csv_alan "$IP_ADRESI"),$(_csv_alan "$VARSAYILAN_PORT"),$(_csv_alan "$HOSTNAME")"

# ── CSV başlığını ilk kez yaz ─────────────────────────────────
if [[ ! -f "$CSV_DOSYA" ]]; then
    echo '"sinif_sube","ip_adresi","port","hostname"' > "$CSV_DOSYA"
    bilgi "CSV dosyası oluşturuldu: $CSV_DOSYA"
fi

# ── Satırı ekle ──────────────────────────────────────────────
echo "$SATIR" >> "$CSV_DOSYA"

echo ""
basari "Kayıt eklendi:"
echo -e "  ${MAVI}sinif_sube${SIFIRLA} : $SINIF_SUBE"
echo -e "  ${MAVI}ip_adresi${SIFIRLA}  : $IP_ADRESI"
echo -e "  ${MAVI}port${SIFIRLA}       : $VARSAYILAN_PORT"
echo -e "  ${MAVI}hostname${SIFIRLA}   : $HOSTNAME"
echo ""
echo -e "  CSV dosyası: ${SARI}$CSV_DOSYA${SIFIRLA}"
echo ""

# ── Güncel CSV içeriğini göster ───────────────────────────────
KAYIT_SAYISI=$(( $(wc -l < "$CSV_DOSYA") - 1 ))
bilgi "Toplam kayıt: $KAYIT_SAYISI tahta"
echo ""
column -t -s',' "$CSV_DOSYA" 2>/dev/null || cat "$CSV_DOSYA"
echo ""

echo -e "${YESIL}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${SIFIRLA}"
echo -e "${YESIL}  Tamamlandı! USB'yi bir sonraki tahtaya takın.${SIFIRLA}"
echo -e "${YESIL}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${SIFIRLA}"
echo ""
