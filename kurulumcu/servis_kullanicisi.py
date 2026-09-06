"""Servisin çalışacağı, sudo yetkisiz ayrı sistem kullanıcısının (akalsite) kurulumu.

Kurulumu çalıştıran kullanıcı (örn. senolirmak, sudo yetkili) ile Gunicorn'un fiilen
altında çalıştığı kullanıcı kasıtlı olarak ayrılır: Django/Gunicorn süreci sudo
yetkisi olmayan, kabuksuz (`nologin`) bir sistem kullanıcısı (`akalsite`) altında
çalışır — uygulama katmanında bulunabilecek bir güvenlik açığı istismar edilse bile
saldırgan doğrudan sudo/kabuk erişimi kazanamaz. Kurulumu çalıştıran kullanıcı bu
kullanıcıyla hiç örtüşmez; deploy/kurulum adımları (git pull, pip install, migrate,
collectstatic) her zaman kurulumu çalıştıran kullanıcı olarak kalır.

Nginx, Gunicorn'un unix soketine yalnızca `SERVIS_GRUBU` (www-data) grubu üyesi
olarak erişebilir — bkz. `sunucu.gunicorn_servisi_kur`'daki `Group=`/`UMask=`.
"""

from __future__ import annotations

import getpass
import os
from pathlib import Path

from . import yardimci as y

SERVIS_KULLANICISI = "akalsite"
SERVIS_GRUBU = "www-data"


def _kurulumu_calistiran_kullanici() -> str:
    """Kurulum/deploy'u çalıştıran (sudo'suz komutları çalıştıracak olan) OS
    kullanıcısı — `sudo` altında çalışıyorsa gerçek/hedef kullanıcı, değilse
    mevcut kullanıcı. `veritabani._linger_etkinlestir`'deki aynı desen."""
    return os.environ.get("SUDO_USER") or getpass.getuser()


def _sbin_komut_var_mi(ad: str) -> bool:
    """`shutil.which` (`y.komut_var_mi`), kurulumu çalıştıran kullanıcının PATH'ini
    kullanır — bu genelde `/usr/sbin`'i İÇERMEZ (birçok dağıtımda yalnızca root'un
    PATH'inde bulunur), oysa bu fonksiyonla kontrol edilen komutlar (adduser,
    groupadd, usermod) hep `sudo` ile çalıştırılır ve sudo kendi `secure_path`'ini
    kullanır (genelde /usr/sbin dahildir) — yani asıl çalıştırma başarılı olurdu.
    Bu yüzden PATH'e değil, doğrudan standart sbin konumlarına bakılır."""
    if y.komut_var_mi(ad):
        return True
    return any((Path(dizin) / ad).is_file() for dizin in ("/usr/sbin", "/sbin", "/usr/local/sbin"))


def _kullanici_var_mi(ad: str) -> bool:
    return y.basarili_mi(["id", "-u", ad])


def _grup_var_mi(ad: str) -> bool:
    return y.basarili_mi(["getent", "group", ad])


def _nginx_calisma_kullanicisi() -> str | None:
    """`/etc/nginx/nginx.conf`'taki 'user' direktifini okuyarak nginx'in hangi OS
    kullanıcısı altında çalıştığını tespit eder. Debian/Ubuntu'nun nginx paketinde
    varsayılan `www-data`'dır (bu durumda zaten `SERVIS_GRUBU` ile aynıdır, ekstra
    işlem gerekmez); Fedora/RHEL paketinde ise varsayılan `nginx`'tir — o kullanıcının
    soketi okuyabilmesi için `SERVIS_GRUBU`'na eklenmesi gerekir. Dosya yoksa ya da
    direktif bulunamazsa None döner (nginx henüz kurulmamış olabilir)."""
    try:
        icerik = Path("/etc/nginx/nginx.conf").read_text()
    except OSError:
        return None
    for satir in icerik.splitlines():
        satir = satir.strip()
        if satir.startswith("user ") and satir.endswith(";"):
            return satir[len("user ") : -1].split()[0]
    return None


def servis_kullanicisini_hazirla(proje_dizin: Path) -> None:
    """`SERVIS_GRUBU` grubunu ve `SERVIS_KULLANICISI` sistem kullanıcısını (yoksa)
    oluşturur; nginx'in soketi okuyabilmesi için nginx'in çalışma kullanıcısını da
    gerekirse bu gruba ekler. Tekrar çalıştırmak güvenlidir."""
    if _grup_var_mi(SERVIS_GRUBU):
        y.uyari(f"Grup '{SERVIS_GRUBU}' zaten var, atlanıyor.")
    else:
        y.bilgi(f"Grup oluşturuluyor: {SERVIS_GRUBU}")
        y.calistir(["groupadd", SERVIS_GRUBU], sudo=True)
        y.basari(f"Grup oluşturuldu: {SERVIS_GRUBU}")

    if _kullanici_var_mi(SERVIS_KULLANICISI):
        y.uyari(f"Servis kullanıcısı '{SERVIS_KULLANICISI}' zaten var, atlanıyor.")
    else:
        y.bilgi(f"Servis kullanıcısı oluşturuluyor: {SERVIS_KULLANICISI} (sudo yetkisiz, kabuksuz)")
        if _sbin_komut_var_mi("adduser"):
            # Debian/Ubuntu'nun (adduser paketi) Perl betiği.
            y.calistir(
                [
                    "adduser",
                    "--system",
                    "--group",
                    "--home",
                    str(proje_dizin),
                    "--shell",
                    "/usr/sbin/nologin",
                    SERVIS_KULLANICISI,
                ],
                sudo=True,
            )
        elif _sbin_komut_var_mi("useradd"):
            # Fedora/RHEL gibi dnf tabanlı dağıtımlarda 'adduser' ayrı bir komut
            # değildir — shadow-utils'in 'useradd'ı kullanılır. --user-group,
            # adduser'ın --group'una denk düşer (kullanıcıyla aynı adda birincil
            # grup); --home-dir zaten var olan proje dizinini oluşturmaya/sahiplenmeye
            # çalışmaz (-m verilmediği sürece), tıpkı adduser'daki --home gibi.
            y.calistir(
                [
                    "useradd",
                    "--system",
                    "--user-group",
                    "--home-dir",
                    str(proje_dizin),
                    "--shell",
                    "/usr/sbin/nologin",
                    SERVIS_KULLANICISI,
                ],
                sudo=True,
            )
        else:
            y.hata(
                f"Ne 'adduser' ne 'useradd' bulundu. '{SERVIS_KULLANICISI}' sistem kullanıcısını "
                f"elle oluşturun, örn.: sudo useradd --system --home-dir {proje_dizin} "
                f"--shell /usr/sbin/nologin --user-group {SERVIS_KULLANICISI}"
            )
        y.basari(f"Servis kullanıcısı oluşturuldu: {SERVIS_KULLANICISI}")

    # Yukarıdaki adduser --group / useradd --user-group, SERVIS_KULLANICISI ile
    # aynı adda bir birincil grup oluşturur — '.env'i bu gruba (aşağıda
    # calisma_zamani_dosyalarini_devret'te) grup-okunabilir yapacağız;
    # kurulumu/deploy'u çalıştıran kullanıcı da bu grubun üyesi olmalı ki
    # 'python manage.py migrate' gibi sudo'suz komutlar '.env'i okuyabilsin.
    kurulum_kullanicisi = _kurulumu_calistiran_kullanici()
    if kurulum_kullanicisi != SERVIS_KULLANICISI:
        y.calistir(["usermod", "-aG", SERVIS_KULLANICISI, kurulum_kullanicisi], sudo=True)
        y.bilgi(
            f"'{kurulum_kullanicisi}' '{SERVIS_KULLANICISI}' grubuna eklendi "
            "('.env'i sudo'suz okuyabilsin diye) — yeni oturumda (yeniden SSH bağlantısında) etkin olur."
        )

    nginx_kullanici = _nginx_calisma_kullanicisi()
    if nginx_kullanici and nginx_kullanici not in (SERVIS_GRUBU, SERVIS_KULLANICISI):
        y.bilgi(f"Nginx '{SERVIS_GRUBU}' grubuna ekleniyor (soketi okuyabilsin diye): {nginx_kullanici}")
        y.calistir(["usermod", "-aG", SERVIS_GRUBU, nginx_kullanici], sudo=True)
        y.basari(f"'{nginx_kullanici}' artık '{SERVIS_GRUBU}' grubunun üyesi (etkinleşmesi için nginx yeniden başlatılmalı).")


def proje_dizini_sahipligini_garanti_et(proje_dizin: Path) -> None:
    """Proje dizininin (`proje_dizin`'in KENDİSİ — içindeki `.env`/`media/`/`backups/`
    değil) sahibinin kurulumu/deploy'u çalıştıran kullanıcıda kalmasını garanti eder.

    Bir önceki adımda (`servis_kullanicisini_hazirla`) `adduser --home`/`useradd
    --home-dir` çağrısına `proje_dizin` (zaten var olan git checkout'u) veriliyor;
    bazı dağıtımlarda bu, dizin daha önceden var olsa bile yeni kullanıcının
    (`SERVIS_KULLANICISI`) `--home` dizini olarak sahiplenilmesine yol açabiliyor.
    Böyle bir kaymayı fark etmeden bırakırsak `deploy.sh`'ın `git pull` adımı,
    kurulumu çalıştıran kullanıcının dizine artık yazma izni olmadığı için "unable
    to unlink" hatasıyla başarısız olur (üst dizinde yazma izni olmadan içindeki
    bir dosyayı silmek/değiştirmek POSIX'te mümkün değildir — dosyanın kendi izni
    yeterli olmaz).

    Grup yine de `SERVIS_KULLANICISI` olarak bırakılır ki Gunicorn (o kullanıcı
    altında çalışır) dizine girip (`r-x`) uygulama dosyalarını okuyabilsin; yazma
    izni gerekmiyor — çalışma zamanı yazma ihtiyacı olan alt dizinler (`media/`,
    `backups/`) zaten ayrı ayrı devrediliyor/paylaşılıyor.

    Tekrar çalıştırmak güvenlidir; sahiplik zaten doğruysa hiçbir şey değişmez."""
    kurulum_kullanicisi = _kurulumu_calistiran_kullanici()
    y.calistir(["chown", f"{kurulum_kullanicisi}:{SERVIS_KULLANICISI}", str(proje_dizin)], sudo=True)
    y.basari(f"Proje dizininin sahipliği garanti edildi: {kurulum_kullanicisi}:{SERVIS_KULLANICISI}.")


def calisma_zamani_dosyalarini_devret(proje_dizin: Path, env_yolu: Path) -> None:
    """`.env` ve `media/`'yi `SERVIS_KULLANICISI`'na devreder.

    `.env`: systemd'nin `EnvironmentFile=`'ı değil, Django'nun kendisi
    (`config/settings/base.py`) `python-dotenv` ile bu dosyayı süreç içinden
    doğrudan okur — yani Gunicorn süreci (artık `SERVIS_KULLANICISI` altında
    çalışıyor) dosyayı okuyabilmelidir. Sahibi `SERVIS_KULLANICISI`, mod 640:
    grup üyeleri (kurulumu/deploy'u çalıştıran kullanıcı — bkz.
    `servis_kullanicisini_hazirla`'daki `usermod -aG`) de sudo'suz okuyabilir,
    bu sayede `deploy.sh`'ın çalıştırdığı sade `python manage.py migrate` gibi
    komutlar çalışmaya devam eder; diğerleri hiç erişemez.

    `media/`: çalışma zamanında (öğrenci/personel dosya yüklemeleri vb.)
    `SERVIS_KULLANICISI` tarafından yazılır; grup `SERVIS_GRUBU` olarak
    bırakılır ve setgid biti ile yeni alt dizinlerin de aynı grubu miras
    alması sağlanır (nginx `media/`'yi doğrudan `alias` ile okuyor)."""
    if env_yolu.is_file():
        y.calistir(["chown", f"{SERVIS_KULLANICISI}:{SERVIS_KULLANICISI}", str(env_yolu)], sudo=True)
        y.calistir(["chmod", "640", str(env_yolu)], sudo=True)

    media_dizin = proje_dizin / "media"
    media_dizin.mkdir(exist_ok=True)
    y.calistir(["chown", "-R", f"{SERVIS_KULLANICISI}:{SERVIS_GRUBU}", str(media_dizin)], sudo=True)
    y.calistir(["chmod", "g+s", str(media_dizin)], sudo=True)
    y.basari("'.env' ve 'media/' servis kullanıcısına devredildi.")


def statik_dosyalari_erisilebilir_yap(proje_dizin: Path) -> None:
    """`staticfiles/`'ı nginx için (grup/sahiplik değil) "diğer" (other) erişimiyle
    okunabilir/gezilebilir yapar: dizinler 755, dosyalar 644.

    `staticfiles/`, `media/`'nin aksine `SERVIS_KULLANICISI`'na devredilmez —
    `collectstatic`'i çalıştıran, kurulumu/deploy'u yapan kullanıcının sahipliğinde
    kalır (nginx zaten `www-data` grubunda değil bu kullanıcının grubunda, yani
    grup üzerinden değil "other" bitleri üzerinden okur). `collectstatic` bu
    fonksiyondan ÖNCE, sudo'suz ve kurulumu çalıştıran kullanıcının o anki
    umask'ıyla dosya/dizin oluşturur (bkz. `cli.py`: `_manage_py_sessiz`) — umask
    varsayılandan (022) daha kısıtlayıcıysa (örn. sudoers'da `Defaults umask=077`)
    sonuç dizinler/dosyalar "other" için hiç okunabilir olmaz ve nginx `/static/`
    isteklerine 403 döner. `deploy.sh`'ın adım 10'unda ("İzinleri düzelt") her
    güncellemede tekrarlanan aynı `find ... chmod` çifti burada ilk kuruluma da
    uygulanıyor — aksi halde bu sorun yalnızca ilk `deploy.sh` çalıştırılana kadar
    fark edilmeyebilir."""
    statik_dizin = proje_dizin / "staticfiles"
    if not statik_dizin.is_dir():
        y.uyari("'staticfiles/' bulunamadı, izin düzenlemesi atlandı (collectstatic çalışmamış olabilir).")
        return
    y.calistir(["find", str(statik_dizin), "-type", "d", "-exec", "chmod", "755", "{}", "+"], sudo=True)
    y.calistir(["find", str(statik_dizin), "-type", "f", "-exec", "chmod", "644", "{}", "+"], sudo=True)
    y.basari("'staticfiles/' nginx için erişilebilir hale getirildi.")


def paylasilan_yedek_dizinini_hazirla(proje_dizin: Path) -> None:
    """`backups/`, kurulumu/deploy'u çalıştıran kullanıcı (`deploy.sh`) İLE servis
    kullanıcısının (`akalsite`, web üzerinden yedek al/geri yükle — bkz.
    `yedekleme/services/yedek_servisi.py`) İKİSİNİN de yazması gereken PAYLAŞILAN
    tek dizindir; `.env`/`media/`'nin aksine tek bir tarafa devredilemez.

    Hangi taraf önce oluşturursa oluştursun (`mkdir(exist_ok=True)`), diğer tarafın
    da yazabilmesi gerekir — aksi halde biri diğerini kilitler (örn. web'den ilk
    yedek `akalsite:www-data` mod 0770 ile oluşturursa, `deploy.sh`'in kendi yedeğini
    yazması "Erişim engellendi" ile başarısız olur).

    Çözüm: setgid biti + ortak grup (`SERVIS_KULLANICISI`'nin kendi birincil grubu
    — kurulumu çalıştıran kullanıcı zaten bu grubun üyesi, bkz.
    `servis_kullanicisini_hazirla`'daki `usermod -aG`). setgid sayesinde içinde
    oluşturulan her dosya/dizin, onu oluşturan sürecin KENDİ birincil/etkin
    grubundan bağımsız olarak bu ortak grubu miras alır (POSIX setgid semantiği).

    Bu mirasın Gunicorn tarafında da işlemesi için `SupplementaryGroups=` (değeri
    `SERVIS_KULLANICISI`) şart (bkz. `sunucu.gunicorn_servisi_kur`): `Group=www-data`
    yalnızca soket için ayarlandığından, bu olmadan systemd süreci `SERVIS_KULLANICISI`
    grubunun üyesi SAYMAZ — web tarafından oluşturulan yedekler kendi payına sorun
    çıkarmaz (dosyanın sahibi zaten kendisidir) ama `deploy.sh`'in (mod 0660, grup
    `SERVIS_KULLANICISI` ile) yazdığı yedekleri Gunicorn süreci okuyamaz — yedeği
    geri yüklerken/raporlarken `PermissionError` ile Server Error (500) verir.
    "other" erişimi kapalı tutulur — yedekler ham veritabanı içeriği taşır."""
    yedek_dizin = proje_dizin / "backups"
    yedek_dizin.mkdir(exist_ok=True)
    y.calistir(["chgrp", SERVIS_KULLANICISI, str(yedek_dizin)], sudo=True)
    y.calistir(["chmod", "2770", str(yedek_dizin)], sudo=True)
    y.basari(f"'backups/' paylaşılan dizin olarak hazırlandı (grup: {SERVIS_KULLANICISI}, setgid).")
