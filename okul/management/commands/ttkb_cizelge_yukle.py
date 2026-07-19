"""
MEB Talim ve Terbiye Kurulu Başkanlığı'nın resmi "Öğretmenlik Alanları, Atama
ve Ders Okutma Esasları" PDF'ini (ör. https://ttkb.meb.gov.tr/...cizelgeveesaslar.pdf)
çözümleyip OgretmenlikAlanCizelgesi tablosuna aktarır.

Sayfa aralığı sabit kodlanmadı: PDF'teki HER sayfa taranır, "SIRA NO" başlıklı
4 sütunlu çizelge tablosu içeren sayfalar otomatik tespit edilir. Bu sayede
TTKB belgeyi güncelleyip sayfa sayısını değiştirse bile komut çalışmaya devam
eder (belge yapısı — 4 sütunlu SIRA NO çizelgesi — aynı kaldığı sürece).

Çizelgenin hücre yapısı (birleşik hücreler, alt-alan satırları, birden fazla
mezun-program grubu) için ayrıştırma kuralları:
  - SIRA NO dolu satır: yeni bir branş bloğu başlar.
  - SIRA NO boş + ALAN dolu + MEZUN/DERSLER boş: bir üstteki bloğun adına
    eklenen salt etiket (ör. "Denizcilik" bloğuna "Gemi Yönetimi" eklenir →
    "Denizcilik / Gemi Yönetimi"), çünkü verisi zaten üstteki satırdadır.
  - SIRA NO boş + ALAN dolu + MEZUN/DERSLER dolu: aynı SIRA NO altında ayrı
    bir alt-branş (ör. "Gemi Makineleri", "Gemi Elektroniği").
  - SIRA NO boş + ALAN boş + MEZUN dolu: mevcut branşın ek bir mezun-program
    grubu (ör. Din Kültürü ve Ahlâk Bilgisi'nde İlahiyat mezunları grubu —
    farklı mezun grupları farklı ders listesine sahip olabilir).
  - SIRA NO dolu + MEZUN/DERSLER boş: "Değişik: ... TTKK" ile kaldırılmış
    alan notu — atlanır.

Kullanım:
  python manage.py ttkb_cizelge_yukle /yol/cizelge.pdf
  python manage.py ttkb_cizelge_yukle /yol/cizelge.pdf --temizle
"""
import re

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from okul.models import OgretmenlikAlanCizelgesi

_DEGISIK_RE = re.compile(r"\(Değişik:.*?\)", re.DOTALL)
_FOOTNOTE_RE = re.compile(r"\(\*+\)")
_NUM_ITEM_RE = re.compile(r"^\s*(\d+)\.\s+(.*)$")
_BULLET_RE = re.compile(r"^\s*[•]\s*(.*)$")
_WINGDINGS_BULLET = ""

_TABLE_SETTINGS = {"vertical_strategy": "lines", "horizontal_strategy": "lines"}


def _clean_alan_adi(text):
    if not text:
        return ""
    text = _DEGISIK_RE.sub("", text)
    return " ".join(text.split()).strip(" /")


def _parse_mezun_bloklari(text):
    if not text:
        return []
    items = []
    current_num_text = None
    current_children = []
    in_footnote = False

    def flush():
        nonlocal current_num_text, current_children
        if current_num_text is None:
            return
        base = _FOOTNOTE_RE.sub("", current_num_text).strip().rstrip(";").strip()
        if current_children:
            for ch in current_children:
                items.append(f"{base} - {_FOOTNOTE_RE.sub('', ch).strip()}")
        else:
            items.append(base)
        current_num_text = None
        current_children = []

    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        if in_footnote:
            continue
        m = _NUM_ITEM_RE.match(line)
        if m:
            flush()
            current_num_text = m.group(2)
            continue
        mb = _BULLET_RE.match(line)
        if mb and current_num_text is not None:
            current_children.append(mb.group(1))
            continue
        if line.startswith("(*"):
            in_footnote = True
            continue
        if current_num_text is not None and not current_children:
            current_num_text += " " + line
        elif current_children:
            current_children[-1] += " " + line
    flush()

    if not items:
        tek = _FOOTNOTE_RE.sub("", text).strip()
        if tek:
            items = [" ".join(tek.split())]
    return items


def _normalize_dersler(text):
    if not text:
        return ""
    text = text.replace(_WINGDINGS_BULLET, "▪")
    satirlar = [satir.rstrip() for satir in text.split("\n")]
    return "\n".join(satir for satir in satirlar if satir.strip())


def _extract_raw_rows(pdf):
    raw_rows = []
    for page in pdf.pages:
        for table in page.extract_tables(_TABLE_SETTINGS):
            if not table or len(table[0]) != 4:
                continue
            if not (table[0][0] or "").strip().startswith("SIRA"):
                continue
            for row in table[1:]:
                raw_rows.append(row)
    return raw_rows


def _build_blocks(raw_rows):
    blocks = []
    current_sira = None

    for cols in raw_rows:
        sira_raw, alan_raw, mezun_raw, dersler_raw = cols[0], cols[1], cols[2], cols[3]
        sira = (sira_raw or "").strip()
        alan_present = bool(alan_raw and alan_raw.strip())
        mezun_present = bool(mezun_raw and mezun_raw.strip())
        dersler_present = bool(dersler_raw and dersler_raw.strip())

        if sira.isdigit():
            current_sira = int(sira)
            if not mezun_present and not dersler_present:
                continue  # "Değişik: ... TTKK" kaldırılmış alan notu
            blocks.append({
                "sira_no": current_sira, "alan": _clean_alan_adi(alan_raw),
                "mezun_raw": mezun_raw, "dersler_raw": dersler_raw,
            })
            continue

        if alan_present and not mezun_present and not dersler_present:
            # Bazı satırlar (ör. "Müzik" branşındaki çalgı bazlı norm-kadro alt
            # etiketleri: "- Bağlama/ - Kanun/ ...") gerçek bir bileşik alan adı
            # değil, madde işaretli bir alt-liste notudur — bunlar isim
            # birleştirmeye dahil edilmez (aksi halde alan adı anlamsız uzar).
            if alan_raw.count("\n-") < 2 and blocks:
                blocks[-1]["alan"] = (blocks[-1]["alan"] + " / " + _clean_alan_adi(alan_raw)).strip(" /")
            continue

        if alan_present and (mezun_present or dersler_present):
            blocks.append({
                "sira_no": current_sira, "alan": _clean_alan_adi(alan_raw),
                "mezun_raw": mezun_raw, "dersler_raw": dersler_raw,
            })
            continue

        if not alan_present and mezun_present and blocks:
            blocks.append({
                "sira_no": current_sira, "alan": blocks[-1]["alan"],
                "mezun_raw": mezun_raw,
                "dersler_raw": dersler_raw if dersler_present else blocks[-1]["dersler_raw"],
            })

    return blocks


def _build_final_rows(blocks):
    final = []
    for b in blocks:
        dersler = _normalize_dersler(b["dersler_raw"])
        mezun_items = _parse_mezun_bloklari(b["mezun_raw"]) or [""]
        for mo in mezun_items:
            final.append({
                "sira_no": b["sira_no"], "brans": b["alan"],
                "mezunokul": mo, "dersler": dersler,
            })
    return final


class Command(BaseCommand):
    help = "TTKB 'Öğretmenlik Alanları, Atama ve Ders Okutma Esasları' PDF'ini OgretmenlikAlanCizelgesi tablosuna aktarır."

    def add_arguments(self, parser):
        parser.add_argument("pdf_yolu", help="TTKB çizelge PDF dosyasının yolu.")
        parser.add_argument(
            "--temizle", action="store_true",
            help="İçe aktarmadan önce mevcut tüm kayıtları siler (TTKB güncellemesi sonrası tam yenileme için).",
        )

    def handle(self, *args, **options):
        try:
            import pdfplumber
        except ImportError as exc:
            raise CommandError("pdfplumber paketi kurulu değil.") from exc

        pdf_yolu = options["pdf_yolu"]
        try:
            with pdfplumber.open(pdf_yolu) as pdf:
                raw_rows = _extract_raw_rows(pdf)
        except Exception as exc:
            raise CommandError(f"PDF okunamadı: {exc}") from exc

        if not raw_rows:
            raise CommandError(
                "PDF'te 'SIRA NO' başlıklı 4 sütunlu çizelge tablosu bulunamadı. "
                "Belge yapısı değişmiş olabilir."
            )

        blocks = _build_blocks(raw_rows)
        final_rows = _build_final_rows(blocks)

        with transaction.atomic():
            if options["temizle"]:
                silinen, _ = OgretmenlikAlanCizelgesi.objects.all().delete()
                self.stdout.write(f"{silinen} eski kayıt silindi.")

            eklenen = 0
            for row in final_rows:
                brans, mezunokul = row["brans"], row["mezunokul"]
                if len(brans) > 200 or len(mezunokul) > 300:
                    self.stdout.write(self.style.WARNING(
                        f"UYARI: '{brans[:60]}...' alan/mezun metni beklenenden uzun, kırpıldı — "
                        f"PDF yapısı değişmiş olabilir, elle kontrol edin."
                    ))
                    brans, mezunokul = brans[:200], mezunokul[:300]
                _, created = OgretmenlikAlanCizelgesi.objects.get_or_create(
                    sira_no=row["sira_no"], brans=brans, mezunokul=mezunokul,
                    defaults={"dersler": row["dersler"]},
                )
                if created:
                    eklenen += 1

        self.stdout.write(self.style.SUCCESS(
            f"Tamamlandı: {len(raw_rows)} ham satır → {len(blocks)} branş bloğu → "
            f"{len(final_rows)} satır işlendi, {eklenen} yeni kayıt eklendi."
        ))
