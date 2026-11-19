# akal-eta-yonetim

Etkileşimli tahtalarda çalışan küçük bir yönetim servisi (eski adı: `okul-ajan`). Her 60 saniyede bir okul
sunucusuna tahtanın durumunu gönderir ve bekleyen komutları (kapat / yeniden
başlat / güncelle / ETA'ya kaydet) alır. Sunucu tarafı `tahtalar` Django uygulamasıdır; tahtalar admin
panelinde **Etkileşimli Tahtalar → Tahtalar** altında listelenir.

- Yalnızca Python'un standart kütüphanesini kullanır, `pip` gerekmez.
- Tahta sunucuya bağlanır; tahtada dışarıya açık bir port yoktur.
- **MEB Ahenk ile çakışmaz:** `/etc/ahenk` altına hiçbir şey yazmaz. Ahenk
  servisinin durumunu (`systemctl show ahenk.service`) ve MEB kaydını
  (`/etc/ahenk/ahenk.db`, olmazsa `ahenk.conf`) yalnızca okur. Servis dosyası
  `/etc/ahenk`'i bu servis için salt okunur yapar.

## Sunucuda (bir kez)

1. Bir kayıt anahtarı üretin:
   `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`
2. Sunucudaki `.env` dosyasına ekleyin: `TAHTA_KAYIT_ANAHTARI=<KAYIT_ANAHTARI>`
3. Servisi yeniden başlatın (deploy sonrası zaten yeniden başlar).

Anahtar yalnızca yeni tahtaların kaydı için kullanılır. Değiştirilirse kayıtlı
tahtalar çalışmaya devam eder; yalnızca yeni kayıtlar yeni anahtarı ister.

## Her tahtada: .deb paketiyle (önerilen)

Tahtalar sayfasındaki **Kurulum paketi (.deb)** düğmesi (`/tahtalar/paket/`,
yalnızca müdür yardımcısı ve okul müdürü) sunucu adresini, kayıt anahtarını ve
varsa yerel CA sertifikasını içeren bir paket üretir:

- **İndirme linki oluştur:** 24 saat geçerli, imzalı bir link ve tahtada
  çalıştırılacak tek satırlık komut verir
  (`wget … && sudo apt install -y ./akal-eta-yonetim_<sürüm>_all.deb`).
  Tahta yerel CA'ya henüz güvenmiyorsa wget sertifika hatası verir; o zaman
  USB yolunu kullanın.
- **Paketi indir (USB için):** paketi indirir; tahtada
  `sudo apt install ./akal-eta-yonetim_<sürüm>_all.deb`.

Paket `kur.sh` ile kurulmuş tahtalara da kurulabilir: ayar dosyasında yalnızca
`sunucu` ve `kayit_anahtari` güncellenir, tahtanın kaydı (token) korunur.
Kaldırma: `sudo apt remove akal-eta-yonetim` (ayarlarla birlikte `apt purge`).

Kontrol: tahta bir dakika içinde Tahtalar sayfasında "Çevrimiçi" görünmeli.
Günlük için `sudo journalctl -u akal-eta-yonetim -n 20 -f` (sudo olmadan ETAP'ta boş
döner). Daha önce kayıtlı tahtada kayıt korunduğu için "Sunucuya kaydolundu"
yazmaz, yalnızca "akal-eta-yonetim … başladı" görünür; başarılı bağlantılar günlüğe
yazılmaz.
Paket ve link kayıt anahtarını içerir; okul dışına paylaşmayın.

Paket sürümü `akal_eta_yonetim.py` içindeki `SURUM`'dan alınır; sayfa eski
sürümle çalışan tahtaları listeler. Tahtalar yeni sürümü yalnızca `SURUM` artınca
alır. Pakete giren bir şey (bu klasördeki dosyalar ya da `kurulum_paketi.py`'deki
postinst/prerm/postrm/control) değiştiğinde:

```sh
python manage.py tahta_surum_artir            # düzeltme: 1.2.0 → 1.2.1
python manage.py tahta_surum_artir --kucuk    # yeni özellik: 1.2.0 → 1.3.0
python manage.py tahta_surum_artir --buyuk    # 1.2.0 → 2.0.0
python manage.py tahta_surum_artir --denetle  # yalnızca kontrol
```

Komut `SURUM`'u ve içerik özetini (`paket-ozeti.txt`) birlikte günceller; ikisi
birlikte commit'lenir. Unutulursa `tahtalar.test_paket_surumu` testi başarısız
olur ve yeni sürümü önerir — testler geçmeden `main`'e merge edilmediği için
sürümü artırılmamış bir paket tahtalara gitmez. İçerik değişmeden `SURUM`
artırılırsa da test uyarır.

## Otomatik güncelleme (yerel APT deposu)

Sunucu `/tahtalar/apt/` altında küçük bir APT deposu sunar; depoda
akal-eta-yonetim'in güncel sürümü (`SURUM`) bulunur. Dosyalar diskte tutulmaz,
her istekte üretilir: sürüm artırılıp `main`'e alındığında deploy sonrası depo
kendiliğinden güncellenir, `deploy.sh`'ye ek adım gerekmez.

**Sunucu tarafı kurulumcunun işidir:** kurulumcu (sunucu modu) proje içinde
`tahta-deposu/` klasörünü servis kullanıcısına (`akalsite`, mod 700) ait olarak
oluşturur ve depo imza anahtarını (`tahta-deposu/imza-anahtari.json`, mod 600)
yoksa o kullanıcıyla üretir. Klasörde ayrıca sunulmuş paketlerin arşivi
(`tahta-deposu/paketler/`) durur. Proje kökü `akalsite`'a yazılabilir olmadığı
için bu ayrı klasör gerekir (`media/` gibi). Tekrar çalıştırmak güvenlidir: var
olan anahtar korunur, sahiplik düzeltilir; ilk sürümün proje kökünde bıraktığı
`tahta-apt-imza-anahtari.json` ve `tahta-paketleri/` buraya taşınır.

Kurulumcu çalıştırılmadan elle yapmak gerekirse:

```sh
sudo install -d -o akalsite -g akalsite -m 700 /srv/akalyonetim/tahta-deposu
sudo -u akalsite env -C /srv/akalyonetim venv/bin/python manage.py \
    tahta_apt_anahtari_olustur --settings=config.settings.production
```

Anahtar varsa komut bir şey değiştirmez. Sayfada "Permission denied" görünürse
dosya `akalsite`'a ait değildir; kurulumcuyu yeniden çalıştırın.

**Yedekleme:** Yedekleme sayfasından alınan **medya yedeği** anahtarı ve
paket arşivini de içerir (arşivde `_akalyonetim_sistem/` altında).
Geri yüklemede bunlar `media/`'ye değil asıl yerlerine yazılır: anahtar
yalnızca sahibi okuyacak şekilde, mevcutsa ve farklıysa eskisi `.onceki` olarak
saklanarak; paketlerden yalnızca eksik olanlar eklenir. Anahtar kaybolursa her
tahtaya paketi yeniden kurmak gerektiğinden, anahtar üretildikten sonra bir
medya yedeği alın.

**Her tahtada bir kez** bu anahtardan sonra üretilen paketi (1.2.0+) bilinen
yolla kurun (link ya da USB). Paketin postinst'i:

- `/etc/apt/sources.list.d/akal-eta-yonetim.list` dosyasına ayar dosyasındaki
  sunucu adresiyle depo satırını yazar
  (`signed-by=/usr/share/keyrings/akal-eta-yonetim.gpg` — yalnızca bu depo için
  geçerli anahtar; sistemin diğer depolarına etkisi yoktur),
- `/etc/apt/apt.conf.d/50akal-eta-yonetim`: okul sunucusuna vekil sunucusuz
  (DIRECT) gidilir; sunucu HTTPS ise yerel CA `/etc/apt/akal-eta-yonetim-ca.crt`
  olarak kopyalanır (APT `_apt` kullanıcısıyla indirir).

Sonrası kendiliğindendir: sunucu her bağlantıda güncel sürümü (`son_surum`)
bildirir; tahtadaki sürüm daha eskiyse uygulama ayrı bir systemd birimiyle
(`akal-eta-yonetim-kendini-guncelle`) **yalnızca kendi paketini, yalnızca bu
depodan** o sürüme günceller (diğer paketlere ve depolara dokunmaz). Günlük:
`sudo journalctl -u akal-eta-yonetim-kendini-guncelle`

**Sağlık kontrolü ve geri dönüş:** yeni sürüm kurulduktan sonra 180 saniye
içinde sunucuyla en az bir kez başarıyla konuşmalıdır (uygulama bunu
`/var/lib/akal-eta-yonetim/calisiyor` dosyasına yazar). Konuşamazsa — açılışta
çöküyorsa ya da kurulumu yarıda kaldıysa — önceki sürüm depodan geri kurulur
ve servis onunla yeniden başlar. Çalışmayan sürüm
`/var/lib/akal-eta-yonetim/bozuk-surumler`'e yazılır ve bir daha denenmez;
düzeltmeyi `SURUM`'u artırarak yayınlayın, tahtalar yeni sürümü alır. Kurulum
hiç başlamadan durduysa (indirme hatası, paket kilidi) eski sürüm yerinde
kalır; saatte bir yeniden denenir. Sonuç Kurulum paketi sayfasındaki "Eski
sürümlü kurulumlar" tablosunda görünür (örn. "1.3.0: Çalışmadı, geri
dönüldü"). Çalışıp yanlış iş yapan bir sürüm bu kontrolden geçer; onun
düzeltmesi de yeni sürümle yayınlanır.

**Sürüm arşivi:** sunucu tahtalara sunduğu her sürümü bir kez
`tahta-deposu/paketler/` klasörüne kaydeder (repoya girmez; yazamazsa depo yine
çalışır ama geri dönüş noktası kalmaz, günlüğe uyarı düşer). Depo listesinde son 5 sürüm bulunur; geri dönüş buradan yapılır.
Klasörü silmeyin; medya yedeğine kendiliğinden dahil edilir.

**Sabitleme (pin):** paket kurulu sürümünü
`/etc/apt/preferences.d/akal-eta-yonetim` ile sabitler. Böylece **Güncelle**
komutunun genel `apt upgrade`'i bu paketi sağlık kontrolü olmadan yükseltmez;
paket yalnızca yukarıdaki kontrollü yolla ya da elle `.deb` kurularak değişir.

Depodaki paket kayıt anahtarı, sunucu adresi ve CA içermez; kurulu tahtanın
ayarlarına dokunmaz (kurulum paketinden kalan `kurulum.conf` yükseltmede
silinir). Paket kaldırılınca depo satırı, APT ayarı ve sabitleme de silinir.

Anahtar değiştirilirse (`--zorla`) depoyu tanıyan tahtalar güncelleme alamaz;
paketin her tahtaya yeniden kurulması gerekir.

## Eski adla (okul-ajan) kurulmuş tahtalar

Paket ya da `kur.sh`, eski adla yapılmış kurulumu kendisi taşır
(`eski-kurulumu-tasi.sh`): `okul-ajan` servisi durdurulup kapatılır; ayarlar
(`/etc/okul-ajan/ajan.conf` → `/etc/akal-eta-yonetim/akal-eta-yonetim.conf`),
yerel CA sertifikası ve tahtanın sunucu kaydı (token) taşınır; eski dosyalar
silinir. Tahta sunucuda aynı kayıtla devam eder, listede çift görünmez. Eski
`okul-ajan` .deb paketi kuruluysa apt onu kaldırır (`Conflicts`).

## Her tahtada: USB ile kur.sh

USB belleği bir kez hazırlayın, sonra her tahtada tek komutla kurun:

1. Bu klasördeki dosyaları USB belleğe kopyalayın. `kurulum.conf.ornek`
   dosyasını `kurulum.conf` adıyla kopyalayıp doldurun:
   ```
   SUNUCU_ADRESI=https://<SUNUCU_ADRESI>
   TAHTA_KAYIT_ANAHTARI=<KAYIT_ANAHTARI>
   ```
   Sunucu HTTPS kullanıyorsa giriş sayfasından indirilen CA sertifikasını da
   `yerel-ca.crt` adıyla aynı klasöre koyun.
2. Tahtada USB'deki klasörde: `sudo sh kur.sh`
   (ayar dosyası başka yerdeyse: `sudo sh kur.sh /yol/kurulum.conf`).
   Betik değerleri `/etc/akal-eta-yonetim/akal-eta-yonetim.conf`'a yazar ve
   servisi başlatır.
   Yeniden çalıştırmak güvenlidir: yalnızca `sunucu` ve `kayit_anahtari`
   güncellenir, diğer ayarlar korunur.
3. Kontrol: `sudo journalctl -u akal-eta-yonetim -n 20 -f` — "Sunucuya kaydolundu" görünmeli.

`kurulum.conf` kayıt anahtarını içerir: USB belleği okulda tutun, kurulum
bitince dosyayı silebilirsiniz. Bu dosya depoya eklenmez (`.gitignore`).
`kurulum.conf` yoksa betik yine kurar; değerleri
`/etc/akal-eta-yonetim/akal-eta-yonetim.conf` içine elle girip
`sudo systemctl enable --now akal-eta-yonetim` çalıştırırsınız.

Tahta admin panelinde bilgisayar adıyla görünür; adını ve konumunu oradan
düzeltebilirsiniz.

## MEB Lider envanteri

MEB Lider'den indirilen tahta listesi (Excel) sunucuya bir kez yüklenir:

```sh
python manage.py tahta_envanteri_yukle "/yol/Okulda Akıllı Tahtalar.xlsx" --settings=config.settings.production
```

Liste **Etkileşimli Tahtalar → Tahta envanteri (MEB Lider)** altında görünür.
akal-eta-yonetim tahtanın MAC adreslerini bildirir; sunucu tahtayı bu listedeki satırla
otomatik eşleştirir ve şube adını tahtanın adı ve konumu yapar (ad elle
değiştirilmişse dokunmaz). Komut tekrar çalıştırılabilir, Lider Id'ye göre
günceller. Excel dosyası okulun envanteridir, depoya eklenmez.

## Komutlar

Tahtalar sayfasında tahtaları seçip **Seçilenleri kapat / yeniden başlat /
güncelle** düğmelerini kullanın (admin panelinde aynı eylemler de var). Komut, tahtanın bir sonraki bağlantısında
(en geç ~60 sn) uygulanır. 10 dakika içinde tahtaya ulaşmayan komut iptal
olur; böylece kapalı bir tahtaya verilen "kapat" ertesi gün çalışmaz.

## Açık oturumlar

akal-eta-yonetim her turda tahtada o an açık kullanıcı oturumlarını (`loginctl`)
bildirir: kullanıcı adı, gerçek adı (`/etc/passwd`), ekranda olup olmadığı ve
oturumun başlangıç saati. Giriş ekranı ve sistem oturumları gönderilmez.

ETAP'ın EBA karekod girişi (`eta-qr-login`) tahtada yerel bir hesap açar ve
GECOS alanına `<Ad Soyad>,,,,<md5(eba_id)>` yazar. Bu özet de gönderilir;
sunucu onu EBA hesabını bağlamış personelin (`ebagiris.EbaHesap`) kimliğiyle
karşılaştırır. Eşleşirse sayfada personel adı "✓ Personel" ile görünür;
eşleşmezse "EBA girişi" (öğrenci ya da hesabını bağlamamış öğretmen), EBA
dışı hesaplarda "Yerel hesap" yazar. Özetin kendisi sunucuda saklanmaz.

Bu kişisel veridir (KVKK): sunucu yalnızca **son durumu** tutar, her bağlantıda
üzerine yazar; geçmiş oturum kaydı saklanmaz, log'a yazılmaz. Tahtalar
sayfasında yalnızca müdür yardımcısı ve okul müdürü görür. Oturum açık bir
tahtayı kapatırken / yeniden başlatırken sayfa ayrıca uyarır.

## ETA kaydı (eta-register)

ETAP'ın **eta-register** uygulaması tahtayı MEB'in ETA envanterine okul kodu ve
birim adıyla (örn. 10-A) kaydeder. akal-eta-yonetim (1.1.0+) aynı kaydı arayüzsüz
yapar:

- **Durum:** Tahta ETA sunucusuna günde bir kez (hata olursa saatte bir) tahtanın
  kayıtlı olup olmadığını sorar. Sonuç **Tahtalar → ETA kaydı** sayfasında
  (`/tahtalar/eta/`) görünür: kayıtlı olduğu okul, okul kodu ve birim adı.
- **Kayıt / güncelleme:** Aynı sayfada okul (tesis) kodunu girin (varsayılan:
  Okul Bilgisi'ndeki okul kodu), birim adlarını düzeltin (2-12 karakter;
  varsayılan Lider envanterindeki şube adı), tahtaları seçip gönderin. Kayıtsız
  tahta kaydedilir; kayıtlı tahtanın okul kodu ve birim adı güncellenir.
  Komut yalnızca bu sayfadan açıkça verildiğinde çalışır.

akal-eta-yonetim, ETAP 23.5'teki eta-register 2.0.9 ile aynı istekleri aynı uygulama
koduyla gönderir (`http://api-etap.eba.gov.tr:1000/api`): MAC adresi (ilk
kablolu PCI ağ kartı) ve yeni kayıtta ETAP'ın `etainfo` modülünün topladığı
donanım bilgisi. eta-register gibi, dokunmatik panel üreticisi ETAP'ın listesinde
(`https://etap.org.tr/devices.json`) değilse kayıt yapmaz.

eta-register kayıttan sonra Ahenk'i kurar; **akal-eta-yonetim bunu yapmaz** ve `/etc/ahenk`'e
dokunmaz. Ahenk kurulu değilse ETAP'ın kendi eta-register'ı bir sonraki
etapadmin oturumunda kurar.

Bu, MEB'in yayımlanmış bir API'si değil, eta-register'ın iç arayüzüdür; MEB
değiştirirse bu özellik çalışmaz (diğer işleri etkilenmez). Sorgu hatası
sayfada "Son sorgu başarısız" olarak görünür.

## Güncelleme

**Güncelle** komutu tahtada `apt-get update` + `apt-get upgrade` çalıştırır
(tahtanın kendi depolarından, yani MEB/Pardus depolarından; akal-eta-yonetim
sabitlendiği için bu yolla güncellenmez, kendini güncellemesiyle gelir):

- Uygulamanın kısıtlı servisinin dışında, ayrı bir systemd birimi
  (`akal-eta-yonetim-guncelleme`) olarak çalışır. Günlük:
  `sudo journalctl -u akal-eta-yonetim-guncelleme`
- `upgrade` paket kaldırmaz, yalnızca kurulu paketleri günceller
  (`full-upgrade` değil).
- Yapılandırma dosyalarının mevcut hâli korunur (`--force-confold`); güncelleme
  `/etc/ahenk` dahil hiçbir ayarı değiştirmez. Ahenk paketinin kendisi MEB
  deposunda yeni sürüm varsa güncellenebilir — bu, Ahenk'in normal güncellemesidir.
- Önce yarıda kalmış bir kurulum varsa tamamlanır (`dpkg --configure -a`).
  Başka bir paket işlemi (örn. Ahenk) sürüyorsa 15 dakikaya kadar bekler.
- Güncelleme sürerken **kapat / yeniden başlat komutları reddedilir.** Tahtayı
  düğmeden de kapatmayın; sayfada "Yarıda kaldı" görünür ve bir sonraki
  güncelleme kurulumu tamamlar.
- Güncelleme tahtayı yeniden başlatmaz. Çekirdek güncellemesi geldiyse bittikten
  sonra **yeniden başlat** komutu verin.

## Sorun giderme

| Günlükte | Anlamı |
|---|---|
| `HTTP 403: Kayıt anahtarı geçersiz.` | Ayar dosyasındaki ile sunucudaki anahtar farklı ya da sunucuda boş |
| `HTTP 403: Bu tahta pasife alınmış.` | Admin panelinde tahtanın "Aktif" işareti kaldırılmış |
| `HTTP 401` | Tahta sunucuda silinmiş; kendini yeniden kaydeder |
| `CERTIFICATE_VERIFY_FAILED` | `ca_dosyasi` eksik ya da yanlış |
| kendini-guncelle günlüğünde `NO_PUBKEY` / `The following signatures were invalid` | Sunucudaki depo anahtarı değişmiş; paketi tahtaya yeniden kurun |
| kendini-guncelle günlüğünde `... list yok` | Tahtadaki paket depo anahtarından önce üretilmiş; paketi bir kez yeniden kurun |
| Sayfada "Çalışmadı, geri dönüldü" | Yeni sürüm tahtada açılmadı ya da sunucuyla konuşamadı; tahtada `journalctl -u akal-eta-yonetim` ile hatayı görün, düzeltip `SURUM`'u artırın |
| Sayfada "Başarısız" | Paket indirilemedi/kurulamadı (eski sürüm çalışıyor, saatte bir yeniden dener) ya da geri dönüş de başarısız oldu (günlüğe bakın; paketi elle kurun) |
| ETA sayfasında "Son sorgu başarısız: ETA sunucusuna ulaşılamadı" | Tahta `api-etap.eba.gov.tr:1000`'e ulaşamıyor (ağ / vekil sunucu) |
| ETA komutu "Dokunmatik panel üreticisi … listede değil" | eta-register da bu tahtayı kaydetmez; ETAP'a (eta@pardus.org.tr) bildirilmeli |

## Kaldırma

Paketle kurulduysa: `sudo apt purge akal-eta-yonetim`. `kur.sh` ile kurulduysa:

```sh
sudo systemctl disable --now akal-eta-yonetim
sudo rm -rf /opt/akal-eta-yonetim /etc/akal-eta-yonetim /var/lib/akal-eta-yonetim /etc/systemd/system/akal-eta-yonetim.service
sudo systemctl daemon-reload
```
