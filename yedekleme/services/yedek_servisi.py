"""Veritabanı yedeklerini oluşturma, listeleme, indirme, yükleme, silme ve geri
yükleme servisleri.

`backups/` dizinindeki `*.dump` dosyaları tek kaynak kabul edilir — ayrı bir Django
modeli tutulmaz; böylece `deploy.sh`'in otomatik aldığı yedekler de bu listede
görünür. CLAUDE.md'de belirtildiği gibi bu dosyalar gerçek veritabanı yedekleridir.

Başka bir ortamdan (örn. başka bir okul sunucusundan) elle indirilmiş bir `.dump`
dosyası, web arayüzündeki "Yedek Yükle" formuyla `backups/` dizinine kopyalanıp
mevcut geri yükleme akışına (`yedek_geri_yukle_onay` → `yedek_geri_yukle`) dahil
edilebilir — bkz. `yedek_yukle()`.

Bu modül `pg_dump`/`pg_restore`'u DAİMA host'ta kurulu ikili dosyalarla, TCP
üzerinden (`.env`'deki DB_HOST/DB_PORT) çalıştırır — PostgreSQL bir Podman/Docker
konteynerinde çalışıyor olsa bile: konteyner `127.0.0.1:<port>`'a açık olduğundan
(bkz. `kurulumcu/veritabani.py`) bu her zaman yeterlidir. Bilinçli bir tercihtir:
bu servis web isteği içinden, sunucunun servis kullanıcısı olarak (bkz.
`kurulumcu/servis_kullanicisi.py`) çalışır ve bu kullanıcıya kesinlikle podman/docker
erişimi VERİLMEZ — konteyner içine `exec` ile girme (rootless Podman'da zaten yalnızca
konteyneri oluşturan OS kullanıcısı için mümkündür) burada hiç kullanılmaz. `deploy.sh`
(`senolirmak` olarak çalışır) kendi pre-deploy güvenlik yedeği için de aynı yaklaşımı
(host'taki pg_dump, TCP) kullanır — ikisi ayrı süreçlerdir ama artık ikisi de
`backups/`'a (paylaşılan, setgid'li dizin — bkz. `kurulumcu/servis_kullanicisi.py:
paylasilan_yedek_dizinini_hazirla`) aynı şekilde yazar.

Tüm view'lar bu modülü çağırmadan önce yetki kontrolünü (mudur_yardimcisi_required)
yapmış olmalıdır — burada ek bir yetki kontrolü yoktur.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.db import connection

BACKUP_DIR: Path = settings.BASE_DIR / "backups"
ZAMAN_ASIMI_SANIYE = 600  # pg_dump/pg_restore için üst sınır
RAPOR_ZAMAN_ASIMI_SANIYE = 120  # yalnızca arşiv okuyan (DB'ye bağlanmayan) rapor çağrıları için
PG_DUMP_IMZASI = b"PGDMP"  # pg_dump -Fc (custom format) dosyalarının baştaki imzası


class YedekHatasi(Exception):
    """Yedekleme/geri yükleme sırasında oluşan, kullanıcıya gösterilebilir hatalar için."""


@dataclass
class YedekDosyasi:
    ad: str
    boyut_mb: float
    olusturma_tarihi: datetime


@dataclass
class TabloFarki:
    tablo: str
    canli: int
    yedek: int

    @property
    def fark(self) -> int:
        return self.yedek - self.canli


@dataclass
class YedekRaporu:
    olusturma_tarihi: str
    kaynak_db: str
    kaynak_db_eslesiyor: bool
    toplam_tablo: int
    ayni_tablo_sayisi: int
    okul_adi: str | None = None
    aktif_egitim_yili: str | None = None
    farkli_tablolar: list[TabloFarki] = field(default_factory=list)


def _db_ayarlari() -> dict[str, str]:
    db = settings.DATABASES["default"]
    return {
        "ad": db["NAME"],
        "kullanici": db["USER"],
        "sifre": db["PASSWORD"] or "",
        "host": db["HOST"] or "localhost",
        "port": str(db["PORT"] or "5432"),
    }


def _komut_hazirla(temel_komut: list[str]) -> list[str]:
    """Sandbox'lanmış geliştirme ortamlarında host'a çıkmak için gerekebilecek bir
    komut önekini (örn. 'flatpak-spawn --host') .env'den okuyup öne ekler. Podman/docker
    ile ilgisizdir — yalnızca pg_dump/pg_restore ikili dosyalarının sandbox dışına
    çıkılmadan görünmediği geliştirme ortamları içindir."""
    onek = os.getenv("YEDEKLEME_KOMUT_ONEKI", "").strip()
    if not onek:
        return temel_komut
    return [*shlex.split(onek), *temel_komut]


def _arac_bulunamadi_mesaji() -> str:
    return (
        "'pg_dump'/'pg_restore' bulunamadı. PostgreSQL istemci araçlarının host'ta kurulu "
        "olduğundan emin olun (örn. 'sudo apt install postgresql-client' ya da "
        "'sudo dnf install postgresql') — PostgreSQL bir konteynerde çalışıyor olsa bile bu "
        "araçlar TCP üzerinden (127.0.0.1) bağlanır, konteyner içine girmez."
    )


def _pg_restore_arac_komutu() -> list[str]:
    """`pg_restore`'u doğrudan (host'ta kurulu ikili dosyayla) çalıştıracak komutu
    hazırlar.

    Yalnızca arşiv dosyasını okuyan çağrılar (`-l`, `--data-only -f -`) için
    yeterlidir — bu çağrılar hiçbir veritabanına bağlanmaz, dolayısıyla
    `yedek_geri_yukle()`'in aksine -U/-h/-d veya PGPASSWORD gerekmez.
    """
    return _komut_hazirla(["pg_restore"])


def guvenli_yol(dosya_adi: str) -> Path:
    """Dosya adını yalnızca backups/ içindeki gerçek bir .dump dosyasına çözer;
    path traversal veya dizin dışına çıkma girişimlerini reddeder."""
    ad = Path(dosya_adi).name  # herhangi bir dizin bileşenini at (../ dahil)
    if not ad.endswith(".dump"):
        raise YedekHatasi("Geçersiz dosya adı.")
    yol = (BACKUP_DIR / ad).resolve()
    if yol.parent != BACKUP_DIR.resolve() or not yol.is_file():
        raise YedekHatasi("Yedek dosyası bulunamadı.")
    return yol


def yedekleri_listele() -> list[YedekDosyasi]:
    BACKUP_DIR.mkdir(exist_ok=True)
    sonuc = []
    for yol in BACKUP_DIR.glob("*.dump"):
        istat = yol.stat()
        sonuc.append(
            YedekDosyasi(
                ad=yol.name,
                boyut_mb=round(istat.st_size / (1024 * 1024), 2),
                olusturma_tarihi=datetime.fromtimestamp(istat.st_mtime),
            )
        )
    return sorted(sonuc, key=lambda y: y.olusturma_tarihi, reverse=True)


def _pg_dump_calistir(hedef: Path, ayar: dict[str, str]) -> None:
    """pg_dump'ı host'ta kurulu ikili dosyayla, TCP + PGPASSWORD üzerinden çalıştırıp
    çıktısını (stdout) hedef dosyaya yazar (bkz. modül docstring'i — podman/docker
    exec kasıtlı olarak kullanılmaz)."""
    komut = _komut_hazirla(
        [
            "pg_dump", "-h", ayar["host"], "-p", ayar["port"],
            "-U", ayar["kullanici"], "-d", ayar["ad"], "-Fc",
        ]
    )
    ortam = {**os.environ, "PGPASSWORD": ayar["sifre"]}

    try:
        with open(hedef, "wb") as f:
            sonuc = subprocess.run(
                komut, stdout=f, stderr=subprocess.PIPE, env=ortam, timeout=ZAMAN_ASIMI_SANIYE
            )
    except subprocess.TimeoutExpired as exc:
        raise YedekHatasi(
            f"Yedekleme {ZAMAN_ASIMI_SANIYE} saniyede tamamlanamadı (zaman aşımı)."
        ) from exc
    except FileNotFoundError as exc:
        raise YedekHatasi(_arac_bulunamadi_mesaji()) from exc
    except PermissionError as exc:
        raise YedekHatasi(f"'{hedef}' dosyasına yazma izni yok (dosya/dizin izinlerini kontrol edin).") from exc

    if sonuc.returncode != 0:
        hata_metni = sonuc.stderr.decode(errors="replace").strip()
        raise YedekHatasi(f"Yedekleme başarısız oldu: {hata_metni or 'bilinmeyen hata'}")


def yedek_olustur(etiket: str = "web") -> Path:
    """pg_dump ile yeni bir yedek oluşturur ve dosya yolunu döner."""
    BACKUP_DIR.mkdir(exist_ok=True)
    ayar = _db_ayarlari()
    zaman = datetime.now().strftime("%Y%m%d_%H%M%S")
    hedef = BACKUP_DIR / f"{ayar['ad']}_{etiket}_{zaman}.dump"

    try:
        _pg_dump_calistir(hedef, ayar)
    except YedekHatasi:
        hedef.unlink(missing_ok=True)
        raise

    if not hedef.exists() or hedef.stat().st_size == 0:
        hedef.unlink(missing_ok=True)
        raise YedekHatasi("Yedekleme başarısız oldu: çıktı dosyası boş.")

    return hedef


def yedek_yukle(dosya) -> Path:
    """Kullanıcının web formundan yüklediği bir dump dosyasını `backups/` içine
    kaydeder (bkz. `yedekleme/forms.py: YedekYuklemeForm`).

    Hedef dosya adı yüklenen dosyanın orijinal adından değil, biz tarafımızdan
    üretilir (path traversal / çakışma riskini ortadan kaldırmak için); dosyanın
    gerçekten bir pg_dump custom-format çıktısı olduğu baştaki `PGDMP` imzasıyla
    doğrulanır — uzantı kontrolü tek başına yeterli değildir.
    """
    ilk_baytlar = dosya.read(len(PG_DUMP_IMZASI))
    dosya.seek(0)
    if ilk_baytlar != PG_DUMP_IMZASI:
        raise YedekHatasi(
            "Geçersiz dosya: bir PostgreSQL 'custom format' (pg_dump -Fc) yedeği değil."
        )

    BACKUP_DIR.mkdir(exist_ok=True)
    ayar = _db_ayarlari()
    zaman = datetime.now().strftime("%Y%m%d_%H%M%S")
    hedef = BACKUP_DIR / f"{ayar['ad']}_disaridan_{zaman}.dump"

    try:
        with open(hedef, "wb") as f:
            for parca in dosya.chunks():
                f.write(parca)
    except OSError as exc:
        hedef.unlink(missing_ok=True)
        raise YedekHatasi(f"Dosya kaydedilemedi: {exc}") from exc

    if hedef.stat().st_size == 0:
        hedef.unlink(missing_ok=True)
        raise YedekHatasi("Yüklenen dosya boş.")

    return hedef


def yedek_bilgisi(yol: Path) -> dict[str, str]:
    """Yedek dosyasının başlığından (TOC) alınma tarihini ve kaynak veritabanı
    adını okur — `pg_restore -l`, arşivi hiçbir veritabanına geri yüklemeden
    yalnızca içeriğini listeler."""
    komut = [*_pg_restore_arac_komutu(), "-l"]

    try:
        with open(yol, "rb") as f:
            sonuc = subprocess.run(
                komut, stdin=f, capture_output=True, timeout=RAPOR_ZAMAN_ASIMI_SANIYE
            )
    except subprocess.TimeoutExpired as exc:
        raise YedekHatasi("Yedek başlığı okunamadı (zaman aşımı).") from exc
    except FileNotFoundError as exc:
        raise YedekHatasi(_arac_bulunamadi_mesaji()) from exc
    except PermissionError as exc:
        raise YedekHatasi(f"'{yol.name}' dosyasına okuma izni yok (dosya izinlerini kontrol edin).") from exc

    if sonuc.returncode != 0:
        hata_metni = sonuc.stderr.decode(errors="replace").strip()
        raise YedekHatasi(f"Yedek dosyası okunamadı: {hata_metni or 'bozuk ya da geçersiz dosya'}")

    baslik = sonuc.stdout.decode(errors="replace")
    tarih = re.search(r"Archive created at (.+)", baslik)
    dbadi = re.search(r"dbname:\s*(.+)", baslik)
    return {
        "olusturma_tarihi": tarih.group(1).strip() if tarih else "bilinmiyor",
        "kaynak_db": dbadi.group(1).strip() if dbadi else "bilinmiyor",
    }


_COPY_BASLIK = re.compile(r"^COPY public\.([A-Za-z0-9_]+) \(([^)]*)\) FROM stdin;$")

# Yedek raporunda satır sayısının ötesinde gerçek içeriği de gösterilecek tablolar
# — okul adı ve aktif eğitim-öğretim yılı bu ikisinden okunur (bkz. CLAUDE.md
# "Aktif eğitim-öğretim yılı ve aktif tarih kavramı").
_OZET_TABLOLARI = frozenset({"okul_bilgi", "egitim_ogretim_yili"})


def _pg_restore_veri_metni(yol: Path) -> str:
    """`pg_restore --data-only -f -` çıktısını (düz SQL metni) döner; hiçbir
    veritabanına bağlanmaz/yazmaz, yalnızca arşivi okur.

    Çıktı tamamen belleğe alınır; okul ölçeğindeki veri setleri için sorun
    değildir, çok büyük veritabanlarında (birkaç GB'ı aşan) bellek kullanımı
    artabilir.
    """
    komut = [*_pg_restore_arac_komutu(), "--data-only", "-f", "-"]

    try:
        with open(yol, "rb") as f:
            sonuc = subprocess.run(
                komut, stdin=f, capture_output=True, timeout=ZAMAN_ASIMI_SANIYE
            )
    except subprocess.TimeoutExpired as exc:
        raise YedekHatasi("Yedek verisi okunamadı (zaman aşımı).") from exc
    except FileNotFoundError as exc:
        raise YedekHatasi(_arac_bulunamadi_mesaji()) from exc
    except PermissionError as exc:
        raise YedekHatasi(f"'{yol.name}' dosyasına okuma izni yok (dosya izinlerini kontrol edin).") from exc

    if sonuc.returncode != 0:
        hata_metni = sonuc.stderr.decode(errors="replace").strip()
        raise YedekHatasi(f"Yedek verisi okunamadı: {hata_metni or 'bozuk ya da geçersiz dosya'}")

    return sonuc.stdout.decode(errors="replace")


def yedek_tablo_sayimlari(yol: Path) -> dict[str, int]:
    """Yedek dosyasını geri yüklemeden, içindeki her tablonun kaç satır veri
    taşıdığını döner (bkz. `_copy_bloklarini_ayristir`)."""
    sayimlar, _ = _copy_bloklarini_ayristir(_pg_restore_veri_metni(yol))
    return sayimlar


def _copy_alan_coz(ham: str) -> str:
    """PostgreSQL COPY TEXT formatındaki temel kaçış dizilerini çözer (tab, yeni
    satır, ters taksim); okul adı/eğitim yılı gibi düz metin alanları için
    yeterlidir — sekizlik kaçışlar (\\ddd) gibi nadir durumlar çözülmez."""
    return (
        ham.replace("\\t", "\t")
        .replace("\\n", "\n")
        .replace("\\r", "\r")
        .replace("\\\\", "\\")
    )


def _copy_bloklarini_ayristir(
    metin: str, detay_tablolari: frozenset[str] = frozenset()
) -> tuple[dict[str, int], dict[str, list[dict[str, str | None]]]]:
    """`pg_restore --data-only -f -` çıktısını tek geçişte ayrıştırır.

    Her tablo bir `COPY public.<tablo> (kolon1, kolon2, ...) FROM stdin;`
    satırıyla başlar ve tek başına `\\.` satırıyla biter. Her tablo için satır
    sayısı döner; `detay_tablolari`'nda adı geçen (genelde küçük, tekil kayıtlı)
    tablolar için ayrıca sütun adı → değer sözlükleri de döner. Hiçbir
    veritabanına bağlanılmaz.
    """
    sayimlar: dict[str, int] = {}
    detaylar: dict[str, list[dict[str, str | None]]] = {}
    tablo: str | None = None
    kolonlar: list[str] = []
    detay_aliniyor = False

    for satir in metin.splitlines():
        if tablo is None:
            eslesme = _COPY_BASLIK.match(satir)
            if eslesme:
                tablo = eslesme.group(1)
                sayimlar[tablo] = 0
                detay_aliniyor = tablo in detay_tablolari
                if detay_aliniyor:
                    kolonlar = [k.strip() for k in eslesme.group(2).split(",")]
                    detaylar[tablo] = []
            continue
        if satir == "\\.":
            tablo = None
            continue
        sayimlar[tablo] += 1
        if detay_aliniyor:
            degerler = satir.split("\t")
            detaylar[tablo].append(
                {
                    kolon: (None if deger == "\\N" else _copy_alan_coz(deger))
                    for kolon, deger in zip(kolonlar, degerler, strict=False)
                }
            )
    return sayimlar, detaylar


def _copy_bloklarini_say(metin: str) -> dict[str, int]:
    sayimlar, _ = _copy_bloklarini_ayristir(metin)
    return sayimlar


def _okul_ozetini_cikar(
    detaylar: dict[str, list[dict[str, str | None]]],
) -> tuple[str | None, str | None]:
    """`okul_bilgi` (tekil kayıt) ve `egitim_ogretim_yili` COPY verilerinden okul
    adını ve `okul_bilgi.okul_egtyil_id`'nin işaret ettiği aktif eğitim-öğretim
    yılını çıkarır. Yedekte bu tablolar yoksa ya da aktif yıl seçilmemişse
    (`okul_egtyil_id` NULL) ilgili değer(ler) None döner."""
    okul_satirlari = detaylar.get("okul_bilgi") or []
    if not okul_satirlari:
        return None, None

    okul = okul_satirlari[0]
    okul_adi = okul.get("okul_adi") or None

    yil_id = okul.get("okul_egtyil_id")
    aktif_yil = None
    if yil_id:
        for satir in detaylar.get("egitim_ogretim_yili") or []:
            if satir.get("id") == yil_id:
                aktif_yil = satir.get("egitim_yili")
                break
    return okul_adi, aktif_yil


def mevcut_db_tablo_sayimlari(tablolar: Iterable[str]) -> dict[str, int]:
    """Verilen tablo adları için mevcut (canlı, Django'nun bağlı olduğu) veritabanındaki
    satır sayılarını döner; tablo mevcut şemada yoksa sonuçta yer almaz (örn. yedek
    farklı bir migration setiyle alınmışsa)."""
    mevcut_tablolar = set(connection.introspection.table_names())
    sayimlar: dict[str, int] = {}
    with connection.cursor() as imlec:
        for tablo in tablolar:
            if tablo not in mevcut_tablolar:
                continue
            # `tablo`, yalnızca [A-Za-z0-9_] karakterlerine izin veren _COPY_SATIRI
            # regex'inden geldiği için doğrudan gömülmesi güvenlidir.
            imlec.execute(f'SELECT COUNT(*) FROM "{tablo}"')
            sayimlar[tablo] = imlec.fetchone()[0]
    return sayimlar


def yedek_raporu(yol: Path) -> YedekRaporu:
    """Bir yedeği geri yüklemeden önce özetler: ne zaman alındığı, hangi
    veritabanından alındığı ve mevcut (canlı) veritabanıyla arasındaki tablo
    bazlı satır sayısı farkları. `yedek_geri_yukle_onay` ekranında kullanıcıya
    gösterilir; hiçbir veriyi değiştirmez."""
    bilgi = yedek_bilgisi(yol)
    yedek_sayimlari, ozet_detaylari = _copy_bloklarini_ayristir(
        _pg_restore_veri_metni(yol), detay_tablolari=_OZET_TABLOLARI
    )
    canli_sayimlari = mevcut_db_tablo_sayimlari(yedek_sayimlari.keys())

    tum_tablolar = sorted(set(yedek_sayimlari) | set(canli_sayimlari))
    farklilar = []
    ayni = 0
    for tablo in tum_tablolar:
        canli = canli_sayimlari.get(tablo, 0)
        yedekteki = yedek_sayimlari.get(tablo, 0)
        if canli == yedekteki:
            ayni += 1
        else:
            farklilar.append(TabloFarki(tablo=tablo, canli=canli, yedek=yedekteki))

    okul_adi, aktif_egitim_yili = _okul_ozetini_cikar(ozet_detaylari)

    ayar = _db_ayarlari()
    return YedekRaporu(
        olusturma_tarihi=bilgi["olusturma_tarihi"],
        kaynak_db=bilgi["kaynak_db"],
        kaynak_db_eslesiyor=(bilgi["kaynak_db"] == ayar["ad"]),
        toplam_tablo=len(tum_tablolar),
        ayni_tablo_sayisi=ayni,
        okul_adi=okul_adi,
        aktif_egitim_yili=aktif_egitim_yili,
        farkli_tablolar=sorted(farklilar, key=lambda t: abs(t.fark), reverse=True),
    )


def yedek_sil(dosya_adi: str) -> None:
    yol = guvenli_yol(dosya_adi)
    yol.unlink()


def yedek_geri_yukle(dosya_adi: str) -> None:
    """Seçilen yedeği geri yükler.

    Çağıran view, geri yükleme öncesi doğrulama metnini (DB adı) kontrol etmiş ve
    ayrıca bir güvenlik yedeği (yedek_olustur) almış olmalıdır — bu fonksiyon
    yalnızca fiziksel pg_restore işlemini yapar, ek bir onay/güvenlik adımı içermez.
    """
    yol = guvenli_yol(dosya_adi)
    ayar = _db_ayarlari()

    komut = _komut_hazirla(
        [
            "pg_restore", "-h", ayar["host"], "-p", ayar["port"],
            "-U", ayar["kullanici"], "-d", ayar["ad"], "--clean", "--if-exists",
        ]
    )
    ortam = {**os.environ, "PGPASSWORD": ayar["sifre"]}

    try:
        with open(yol, "rb") as f:
            sonuc = subprocess.run(
                komut, stdin=f, stderr=subprocess.PIPE, env=ortam, timeout=ZAMAN_ASIMI_SANIYE
            )
    except subprocess.TimeoutExpired as exc:
        raise YedekHatasi(
            f"Geri yükleme {ZAMAN_ASIMI_SANIYE} saniyede tamamlanamadı (zaman aşımı)."
        ) from exc
    except FileNotFoundError as exc:
        raise YedekHatasi(_arac_bulunamadi_mesaji()) from exc
    except PermissionError as exc:
        raise YedekHatasi(f"'{yol.name}' dosyasına okuma izni yok (dosya izinlerini kontrol edin).") from exc

    # pg_restore, --clean ile var olmayan nesneler için zararsız uyarılar da
    # basabilir; yine de dönüş kodu != 0 olduğunda işlemi başarısız kabul ediyoruz.
    if sonuc.returncode != 0:
        hata_metni = sonuc.stderr.decode(errors="replace").strip()
        raise YedekHatasi(f"Geri yükleme hata(lar)la tamamlandı: {hata_metni[-2000:]}")
