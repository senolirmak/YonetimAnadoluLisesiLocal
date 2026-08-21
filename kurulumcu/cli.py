"""Okul Yönetim Sistemi kurulum sihirbazının ana akışı.

'pip install -e .' sonrası oluşan 'okulyonetim-kur' konsol komutuyla çalışır
(bkz. pyproject.toml [project.scripts]). Doğrudan çalıştırmak isteyen kullanıcılar
için proje kökündeki bootstrap.py, venv'i oluşturup projeyi kurduktan sonra bu
modülün main() fonksiyonuna devreder.

İki moddan biri seçilir:
  1) Yerel geliştirme — runserver ile çalıştırılır.
  2) Sunucu / üretim  — Gunicorn + Nginx + systemd ile site ayağa kaldırılır
     (yalnızca /srv/akalyonetim dizininden çalıştırılmalıdır, bkz. deploy.sh).
     Bu sihirbazı çalıştıran (sudo yetkili) kullanıcı ile Gunicorn'un fiilen
     altında çalıştığı kullanıcı kasıtlı olarak ayrıdır — bkz. servis_kullanicisi.py.

Tekrar çalıştırmak güvenlidir: zaten tamamlanmış adımlar atlanır.
"""

from __future__ import annotations

import datetime
import secrets
import subprocess
import sys
from pathlib import Path

from . import env_dosyasi, paket_yoneticisi, servis_kullanicisi, sunucu, veritabani
from . import yardimci as y

PROJE_DIZIN = Path(__file__).resolve().parent.parent
VENV = PROJE_DIZIN / "venv"
SUNUCU_HEDEF_DIZIN = Path("/srv/akalyonetim")

SUPERUSER_KONTROL_KODU = (
    "from django.contrib.auth.models import User; import sys; "
    "sys.exit(0 if User.objects.filter(is_superuser=True).exists() else 1)"
)
OKUL_BILGISI_KONTROL_KODU = (
    "from okul.models import OkulBilgi; import sys; "
    "sys.exit(0 if OkulBilgi.get().okul_adi else 1)"
)


def _varsayilan_egitim_yili() -> str:
    """Bugünün tarihine göre mantıklı bir eğitim-öğretim yılı önerisi üretir
    (Ağustos-Aralık: içinde bulunulan yıl başlar; Ocak-Temmuz: bir önceki yıl)."""
    bugun = datetime.date.today()
    if bugun.month >= 8:
        return f"{bugun.year}-{bugun.year + 1}"
    return f"{bugun.year - 1}-{bugun.year}"


def _rastgele_secret_key() -> str:
    try:
        from django.core.management.utils import get_random_secret_key

        return get_random_secret_key()
    except ImportError:
        return secrets.token_urlsafe(50)


def _manage_py(*args: str) -> None:
    subprocess.run([sys.executable, "manage.py", *args], cwd=PROJE_DIZIN, check=True)


def _manage_py_sessiz(*args: str) -> None:
    subprocess.run(
        [sys.executable, "manage.py", *args],
        cwd=PROJE_DIZIN,
        check=True,
        stdout=subprocess.DEVNULL,
    )


def _manage_py_basarili_mi(*args: str) -> bool:
    sonuc = subprocess.run(
        [sys.executable, "manage.py", *args],
        cwd=PROJE_DIZIN,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return sonuc.returncode == 0


def _banner(baslik: str, renk: str) -> None:
    cizgi = "━" * 48
    print()
    print(f"{renk}{cizgi}{y.SIFIRLA}")
    print(f"{renk}  {baslik}{y.SIFIRLA}")
    print(f"{renk}{cizgi}{y.SIFIRLA}")
    print()


def main() -> None:
    _banner("Okul Yönetim Sistemi — Kurulum", y.MAVI)

    # ── 0. Kurulum modu ──────────────────────────────────────────
    print("Kurulum modu seçin:")
    print("  1) Yerel geliştirme (runserver ile çalıştırılır)")
    print("  2) Sunucu / üretim (Gunicorn + Nginx + systemd ile site ayağa kalkar)")
    sunucu_modu = y.sor("Seçim", "1") == "2"

    django_ayar_bayragi: list[str] = []
    if sunucu_modu:
        if PROJE_DIZIN != SUNUCU_HEDEF_DIZIN:
            y.hata(
                f"Sunucu kurulumu için proje {SUNUCU_HEDEF_DIZIN} dizininde olmalı "
                f"(şu an: {PROJE_DIZIN}). Projeyi oraya klonlayın/taşıyın ve komutu oradan çalıştırın."
            )
        django_ayar_bayragi = ["--settings=config.settings.production"]
        y.basari(f"Sunucu (üretim) modu seçildi. Hedef dizin: {SUNUCU_HEDEF_DIZIN}")
    else:
        y.basari("Yerel geliştirme modu seçildi.")

    # ── 1. Ön kontroller ─────────────────────────────────────────
    y.bilgi("Gerekli araçlar kontrol ediliyor...")

    paket_yon = paket_yoneticisi.tespit_et()
    konteyner_araci = veritabani.konteyner_araci_tespit_et()

    if konteyner_araci:
        y.bilgi(f"Konteyner aracı bulundu: {konteyner_araci} (PostgreSQL konteynerle başlatılabilir)")
    elif y.komut_var_mi("psql"):
        y.bilgi("Konteyner aracı (podman/docker) bulunamadı; native PostgreSQL kullanılacak (psql mevcut).")
    elif paket_yon:
        y.bilgi(
            "Konteyner aracı (podman/docker) ve psql bulunamadı; PostgreSQL adımında "
            "'Konteyner ile başlat' seçilirse podman otomatik kurulacak."
        )
    elif not sunucu_modu:
        y.hata(
            "Ne podman/docker ne de psql bulundu, otomatik kurulum için bir paket yöneticisi "
            "(apt/dnf) da yok. PostgreSQL'e bağlanmak veya başlatmak için en az birini kurun."
        )

    if sunucu_modu:
        if not paket_yon:
            y.hata("Desteklenen bir paket yöneticisi (apt/dnf) bulunamadı.")
        paket_yoneticisi.sunucu_paketlerini_kur(paket_yon)
    elif not y.komut_var_mi("pdftoppm"):
        y.uyari("poppler-utils bulunamadı (PDF → PNG dönüşümleri için gerekli).")
        y.uyari("  Fedora/RHEL  : sudo dnf install poppler-utils")
        y.uyari("  Ubuntu/Debian: sudo apt install poppler-utils")
        y.uyari("  macOS        : brew install poppler")

    y.basari("Ön kontroller tamam.")

    # ── 2. Bağımlılıklar ─────────────────────────────────────────
    # bootstrap.py bu komutu çalıştırmadan önce 'pip install -e .' ile zaten kurdu.
    y.basari("Bağımlılıklar zaten kurulu (bootstrap.py tarafından, pip install -e .).")

    # ── 3. .env dosyası ──────────────────────────────────────────
    env_yolu = PROJE_DIZIN / ".env"
    degerler = env_dosyasi.oku(env_yolu)

    if degerler:
        y.uyari(".env dosyası zaten var, dokunulmuyor.")
    else:
        y.bilgi(".env dosyası oluşturuluyor...")
        degerler = {
            "DB_NAME": y.sor("Veritabanı adı", "nobet_db"),
            "DB_USER": y.sor("Veritabanı kullanıcı adı", "nobet_user"),
            "DB_PASSWORD": y.sor_sifre("Veritabanı şifresi (yeni oluşturulacak)"),
            "DB_HOST": y.sor("Veritabanı host", "localhost"),
            "DB_PORT": y.sor("Veritabanı port", "5432"),
        }
        if sunucu_modu:
            degerler["DEBUG"] = "False"
            degerler["ALLOWED_HOSTS"] = y.sor(
                "ALLOWED_HOSTS (virgülle ayrılmış domain/IP)", "localhost,127.0.0.1"
            )
        else:
            degerler["DEBUG"] = "True"
        degerler["SECRET_KEY"] = _rastgele_secret_key()

        env_dosyasi.yaz(env_yolu, degerler)
        y.basari(".env dosyası oluşturuldu (rastgele SECRET_KEY üretildi).")

    if sunucu_modu and not degerler.get("ALLOWED_HOSTS"):
        y.uyari(
            "ALLOWED_HOSTS .env içinde tanımlı değil; production.py bunu zorunlu kılar, Django tüm "
            "istekleri reddedebilir (400 Bad Request). .env dosyasına elle ekleyin, örn: "
            "ALLOWED_HOSTS=alan-adi.com,sunucu-ip"
        )

    # ── 4. PostgreSQL veritabanı ve kullanıcısı ──────────────────
    y.bilgi("PostgreSQL bağlantısı kontrol ediliyor...")
    ayar = veritabani.DBAyarlari(
        ad=degerler["DB_NAME"],
        kullanici=degerler["DB_USER"],
        sifre=degerler["DB_PASSWORD"],
        host=degerler["DB_HOST"],
        port=degerler["DB_PORT"],
    )

    konteyner_adi: str | None = None
    if veritabani.baglanabiliyor_mu(ayar):
        detaylar = [f"{ayar.kullanici}@{ayar.host}:{ayar.port}/{ayar.ad}"]
        surum = veritabani.sunucu_surumu(ayar)
        if surum:
            detaylar.append(surum)
        if konteyner_araci:
            calisan_konteyner = veritabani.konteyner_calisiyor_mu(konteyner_araci, ayar)
            if calisan_konteyner:
                detaylar.append(f"konteynerde çalışıyor: {calisan_konteyner}")
        y.basari(f"Veritabanına zaten bağlanılabiliyor ({', '.join(detaylar)}), bu adım atlanıyor.")
    else:
        print()
        print("PostgreSQL nasıl çalıştırılsın?")
        print("  1) Zaten kurulu/çalışan bir sunucuya bağlan (native)")
        if konteyner_araci:
            print(f"  2) Konteyner ile başlat (Önerilen — algılanan araç: {konteyner_araci})")
        elif paket_yon:
            print("  2) Konteyner ile başlat (Önerilen — podman otomatik kurulacak)")
        varsayilan_secim = "2" if (konteyner_araci or paket_yon) else "1"
        db_mod = y.sor("Seçim", varsayilan_secim)

        if db_mod == "2" and (konteyner_araci or paket_yon):
            if not konteyner_araci:
                konteyner_araci = paket_yoneticisi.konteyner_araci_kur(paket_yon)
            konteyner_adi = veritabani.konteyner_ile_kur(konteyner_araci, ayar, PROJE_DIZIN, paket_yon)
            # yedekleme/ app'i pg_dump/pg_restore'u konteyner içinde çalıştırabilsin
            # diye — konteyner modunda host'a bu istemci araçları hiç kurulmuyor,
            # bu satır olmadan yedekleme tamamen çalışmaz (bkz.
            # yedekleme/services/yedek_servisi.py).
            env_dosyasi.anahtar_ayarla(env_yolu, "YEDEKLEME_POSTGRES_KONTEYNER", konteyner_adi)
            y.basari(f"'.env' güncellendi: YEDEKLEME_POSTGRES_KONTEYNER={konteyner_adi}")
        else:
            veritabani.native_ile_kur(ayar, paket_yon, sunucu_modu)

    # ── 5. Django: migrate, gruplar, superuser, statik dosyalar ──
    y.bilgi("Migration'lar uygulanıyor...")
    _manage_py("migrate", *django_ayar_bayragi)
    y.basari("Migration'lar tamamlandı.")

    y.bilgi("Kullanıcı grupları oluşturuluyor...")
    _manage_py("kullanici_gruplari_olustur", *django_ayar_bayragi)
    y.basari("Kullanıcı grupları hazır.")

    if _manage_py_basarili_mi("shell", *django_ayar_bayragi, "-c", SUPERUSER_KONTROL_KODU):
        y.uyari("Süper kullanıcı zaten var, atlanıyor.")
    else:
        y.bilgi("Süper kullanıcı oluşturuluyor (istenen bilgileri girin):")
        _manage_py("createsuperuser", *django_ayar_bayragi)

    y.bilgi("Statik dosyalar toplanıyor...")
    _manage_py_sessiz("collectstatic", "--noinput", *django_ayar_bayragi)
    y.basari("Statik dosyalar toplandı.")

    # ── 5.5 Okul Bilgisi, Eğitim-Öğretim Yılı ve varsayılan ders verileri ──
    # Seçmeli dersler, ders programı ve dönem bazlı raporlama gibi birçok modül
    # OkulBilgi'deki aktif eğitim-öğretim yılına bağlıdır (bkz. CLAUDE.md).
    okul_bilgisi_hazir = _manage_py_basarili_mi("shell", *django_ayar_bayragi, "-c", OKUL_BILGISI_KONTROL_KODU)
    if okul_bilgisi_hazir:
        y.uyari("Okul Bilgisi zaten yapılandırılmış, bu adım atlanıyor.")
    else:
        print()
        print("Okul Bilgisi ve Eğitim-Öğretim Yılı henüz tanımlı değil — seçmeli dersler,")
        print("ders programı ve dönem bazlı raporlama gibi modüller bu olmadan boş görünür.")
        if y.sor("Şimdi oluşturulsun mu?", "E").lower().startswith("e"):
            okul_adi = y.sor("Okul adı")
            egitim_yili = y.sor("Eğitim-Öğretim Yılı", _varsayilan_egitim_yili())
            okul_kodu = y.sor("Okul kodu (boş bırakılabilir)")
            okul_muduru = y.sor("Okul müdürü (boş bırakılabilir)")

            komut = ["okul_bilgisi_olustur", "--okul-adi", okul_adi, "--egitim-yili", egitim_yili]
            if okul_kodu:
                komut += ["--okul-kodu", okul_kodu]
            if okul_muduru:
                komut += ["--okul-muduru", okul_muduru]
            _manage_py(*komut, *django_ayar_bayragi)
            y.basari("Okul Bilgisi oluşturuldu.")
            okul_bilgisi_hazir = True

            print()
            print("Proje, her Anadolu Lisesi için genel olarak geçerli varsayılan ders")
            print("verilerini (Ortak/Seçmeli Ders Havuzu, Zorunlu Dersler, Seçmeli Ders")
            print("Grupları) içeriyor — okulunuz farklı bir müfredat kullanıyorsa atlayın.")
            if y.sor("Varsayılan ders verileri yüklensin mi?", "E").lower().startswith("e"):
                _manage_py("varsayilan_ders_verilerini_yukle", *django_ayar_bayragi)
                y.basari("Varsayılan ders verileri yüklendi.")
        else:
            y.uyari(
                "Atlandı — daha sonra admin panelinden ya da "
                "'python manage.py okul_bilgisi_olustur' ile oluşturabilirsiniz."
            )

    # ── 6. Sunucu servisleri (Gunicorn + Nginx + systemd) ────────
    servis: str | None = None
    if sunucu_modu:
        # Servis, kurulumu çalıştıran (sudo yetkili) kullanıcıdan kasıtlı olarak
        # ayrı, sudo yetkisiz bir sistem kullanıcısı (akalsite) altında çalışır —
        # bkz. kurulumcu/servis_kullanicisi.py.
        servis_kullanicisi.servis_kullanicisini_hazirla(PROJE_DIZIN)
        servis_kullanicisi.calisma_zamani_dosyalarini_devret(PROJE_DIZIN, env_yolu)

        servis_adi = PROJE_DIZIN.name
        servis = sunucu.gunicorn_servisi_kur(
            PROJE_DIZIN,
            VENV,
            servis_adi,
            servis_kullanicisi.SERVIS_KULLANICISI,
            servis_kullanicisi.SERVIS_GRUBU,
        )
        sunucu.nginx_yapilandir(PROJE_DIZIN, servis_adi, degerler.get("ALLOWED_HOSTS", ""))
        sunucu.saglik_kontrolu(servis)

    # ── 7. Bitiş ──────────────────────────────────────────────────
    _banner("Kurulum tamamlandı!", y.YESIL)

    if not okul_bilgisi_hazir:
        print("Kalan tek manuel adım:")
        print("  Admin panelinden (/admin/) 'Okul → Okul Bilgisi' ve 'Eğitim-Öğretim Yılı'")
        print("  kaydını oluşturun; bu olmadan seçmeli dersler, ders programı ve dönem")
        print("  bazlı raporlama gibi modüller aktif yılı bulamadığı için boş görünür.")
        print()

    if konteyner_adi:
        print(f"PostgreSQL konteyneri '{konteyner_adi}' olarak {konteyner_araci} compose ile çalışıyor.")
        print(f"  Yapılandırma : {PROJE_DIZIN}/docker-compose.yaml")
        print(f"  Durum        : {konteyner_araci} ps --filter name={konteyner_adi}")
        print(f"  Durdur       : {konteyner_araci} compose -f docker-compose.yaml stop")
        print(f"  Başlat       : {konteyner_araci} compose -f docker-compose.yaml up -d")
        print(f"  Loglar       : {konteyner_araci} logs {konteyner_adi}")
        print()

    if sunucu_modu:
        print("Site Gunicorn + Nginx ile ayakta:")
        print(f"  Durum        : sudo systemctl status {servis}")
        print(f"  Canlı loglar : sudo journalctl -u {servis} -f")
        print("  Nginx durumu : sudo systemctl status nginx")
        print("  Sonraki güncellemeler için: bash deploy.sh")
        print()
        print(
            "ALLOWED_HOSTS listesindeki adres(ler) üzerinden tarayıcıdan erişilebilir "
            f"({degerler.get('ALLOWED_HOSTS', 'tanımsız')})."
        )
    else:
        print("Sunucuyu başlatmak için:")
        print("  source venv/bin/activate")
        print("  python manage.py runserver")
        print()
        print("Uygulama http://127.0.0.1:8000/ adresinde çalışacak.")
    print()


if __name__ == "__main__":
    main()
