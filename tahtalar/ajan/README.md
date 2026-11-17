# Okul tahta ajanı

Etkileşimli tahtalarda çalışan küçük bir servis. Her 60 saniyede bir okul
sunucusuna tahtanın durumunu gönderir ve bekleyen komutları (kapat / yeniden
başlat) alır. Sunucu tarafı `tahtalar` Django uygulamasıdır; tahtalar admin
panelinde **Etkileşimli Tahtalar → Tahtalar** altında listelenir.

- Yalnızca Python'un standart kütüphanesini kullanır, `pip` gerekmez.
- Tahta sunucuya bağlanır; tahtada dışarıya açık bir port yoktur.
- **MEB Ahenk ile çakışmaz:** `/etc/ahenk` altına hiçbir şey yazmaz. Ahenk
  servisinin durumunu (`systemctl show ahenk.service`) ve MEB kaydını
  (`/etc/ahenk/ahenk.db`, olmazsa `ahenk.conf`) yalnızca okur. Servis dosyası
  `/etc/ahenk`'i ajan için salt okunur yapar.

## Sunucuda (bir kez)

1. Bir kayıt anahtarı üretin:
   `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`
2. Sunucudaki `.env` dosyasına ekleyin: `TAHTA_KAYIT_ANAHTARI=<KAYIT_ANAHTARI>`
3. Servisi yeniden başlatın (deploy sonrası zaten yeniden başlar).

Anahtar yalnızca yeni tahtaların kaydı için kullanılır. Değiştirilirse kayıtlı
tahtalar çalışmaya devam eder; yalnızca yeni kayıtlar yeni anahtarı ister.

## Her tahtada

1. Bu klasördeki dosyaları tahtaya kopyalayın (USB bellek ya da `scp`). Sunucu
   HTTPS kullanıyorsa giriş sayfasından indirilen CA sertifikasını da
   `yerel-ca.crt` adıyla aynı klasöre koyun.
2. `sudo sh kur.sh`
3. `/etc/okul-ajan/ajan.conf` içinde `sunucu` ve `kayit_anahtari` değerlerini
   girin, sonra `sudo systemctl enable --now okul-ajan`.
4. Kontrol: `journalctl -u okul-ajan -f` — "Sunucuya kaydolundu" görünmeli.

Tahta admin panelinde bilgisayar adıyla görünür; adını ve konumunu oradan
düzeltebilirsiniz.

## MEB Lider envanteri

MEB Lider'den indirilen tahta listesi (Excel) sunucuya bir kez yüklenir:

```sh
python manage.py tahta_envanteri_yukle "/yol/Okulda Akıllı Tahtalar.xlsx" --settings=config.settings.production
```

Liste **Etkileşimli Tahtalar → Tahta envanteri (MEB Lider)** altında görünür.
Ajan tahtanın MAC adreslerini bildirir; sunucu tahtayı bu listedeki satırla
otomatik eşleştirir ve şube adını tahtanın adı ve konumu yapar (ad elle
değiştirilmişse dokunmaz). Komut tekrar çalıştırılabilir, Lider Id'ye göre
günceller. Excel dosyası okulun envanteridir, depoya eklenmez.

## Komutlar

Admin panelinde tahtaları seçip **Seçili tahtaları kapat** ya da **yeniden
başlat** eylemini çalıştırın. Komut, tahtanın bir sonraki bağlantısında
(en geç ~60 sn) uygulanır. 10 dakika içinde tahtaya ulaşmayan komut iptal
olur; böylece kapalı bir tahtaya verilen "kapat" ertesi gün çalışmaz.

## Açık oturumlar

Ajan her turda tahtada o an açık kullanıcı oturumlarını (`loginctl`)
bildirir: kullanıcı adı, gerçek adı (`/etc/passwd`), ekranda olup olmadığı ve
oturumun başlangıç saati. Giriş ekranı ve sistem oturumları gönderilmez.

ETAP'ın EBA karekod girişi (`eta-qr-login`) tahtada yerel bir hesap açar ve
GECOS alanına `<Ad Soyad>,,,,<md5(eba_id)>` yazar. Ajan bu özeti de gönderir;
sunucu onu EBA hesabını bağlamış personelin (`ebagiris.EbaHesap`) kimliğiyle
karşılaştırır. Eşleşirse sayfada personel adı "✓ Personel" ile görünür;
eşleşmezse "EBA girişi" (öğrenci ya da hesabını bağlamamış öğretmen), EBA
dışı hesaplarda "Yerel hesap" yazar. Özetin kendisi sunucuda saklanmaz.

Bu kişisel veridir (KVKK): sunucu yalnızca **son durumu** tutar, her bağlantıda
üzerine yazar; geçmiş oturum kaydı saklanmaz, log'a yazılmaz. Tahtalar
sayfasında yalnızca müdür yardımcısı ve okul müdürü görür. Oturum açık bir
tahtayı kapatırken / yeniden başlatırken sayfa ayrıca uyarır.

## Güncelleme

**Güncelle** komutu tahtada `apt-get update` + `apt-get upgrade` çalıştırır
(tahtanın kendi depolarından, yani MEB/Pardus depolarından):

- Ajanın kısıtlı servisinin dışında, ayrı bir systemd birimi
  (`okul-ajan-guncelleme`) olarak çalışır. Günlük:
  `journalctl -u okul-ajan-guncelleme`
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
| `HTTP 403: Kayıt anahtarı geçersiz.` | `ajan.conf` ile sunucudaki anahtar farklı ya da sunucuda boş |
| `HTTP 403: Bu tahta pasife alınmış.` | Admin panelinde tahtanın "Aktif" işareti kaldırılmış |
| `HTTP 401` | Tahta sunucuda silinmiş; ajan kendini yeniden kaydeder |
| `CERTIFICATE_VERIFY_FAILED` | `ca_dosyasi` eksik ya da yanlış |

## Kaldırma

```sh
sudo systemctl disable --now okul-ajan
sudo rm -rf /opt/okul-ajan /etc/okul-ajan /var/lib/okul-ajan /etc/systemd/system/okul-ajan.service
sudo systemctl daemon-reload
```
