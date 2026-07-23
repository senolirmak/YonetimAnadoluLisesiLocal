# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Proje Özeti

Django 6.0 / Python 3.12 tabanlı okul yönetim uygulaması ("Nöbet Yönetim Sistemi"). Nöbet dağıtımı,
ders doldurma, devamsızlık, ders programı, ortak/mazeret/sorumluluk sınav yönetimi, öğrenci takibi ve
dijital pano modüllerini tek bir Django projesinde barındırır. Kod ve arayüz metinleri Türkçe'dir
(model/fonksiyon isimleri de dahil) — yeni kod eklerken bu dile uyun.

## Komutlar

```bash
# Sanal ortamı etkinleştir (proje .venv kullanır)
source .venv/bin/activate

# Geliştirme sunucusu (varsayılan settings: config.settings.development)
python manage.py runserver

# Migrations
python manage.py makemigrations
python manage.py migrate

# Lint (ruff — pyproject.toml: E,F,W,I seçili, E501 kapalı; migrations hariç tutulur)
ruff check .
ruff check --fix .

# Testler (settings.test → sqlite in-memory + MD5PasswordHasher)
python manage.py test --settings=config.settings.test
python manage.py test sinav --settings=config.settings.test          # tek app
python manage.py test sinav.tests.SinavTestCase.test_x --settings=config.settings.test  # tek test

# Prod ayarlarına karşı migration kontrolü (CI'da çalışan kontrol — bkz. .github/workflows)
python manage.py migrate --settings=config.settings.production
python manage.py makemigrations --check --dry-run --settings=config.settings.production
```

Not: Çoğu app'in `tests.py` dosyası `django-admin startapp` iskeletinden ibarettir (gerçek test
yok). Gerçek testler yalnızca `sinav/`, `dersdefteri/`, `sinavmedia/`, `sorumluluk/` içindedir.

### Ortam / Ayarlar

- Ayarlar `config/settings/` altında bölünmüş: `base.py` (ortak), `development.py`, `production.py`,
  `test.py`. `manage.py` varsayılan olarak `development` kullanır; CI ve prod komutları
  `--settings=config.settings.production` ile açıkça belirtilmelidir.
- `.env` dosyası (`.env.example` şablon) `SECRET_KEY`, `DB_NAME/USER/PASSWORD/HOST/PORT` ve isteğe
  bağlı `TIME_ZONE`/`LANGUAGE_CODE` değişkenlerini taşır; `python-dotenv` ile `base.py` içinde yüklenir.
- Veritabanı PostgreSQL'dir (development ve production). Test ortamı sqlite `:memory:` kullanır.
- `pdf2image` sistemde `poppler-utils` gerektirir (PDF → PNG dönüşümleri, örn. günün nöbetçileri çıktısı).
- `devtools/` app'i `.gitignore`'dadır ve repoya hiç girmez; `development.py` yalnızca klasör diskte
  fiziksel olarak varsa `INSTALLED_APPS`'e ekler, `config/urls.py` da aynı şekilde koşullu route eder.
  Bu iki dosyadaki koşullu mantığı bozmayın — amaç, devtools olmayan bir makinede projenin sorunsuz
  çalışmasıdır (bkz. `devtools/README.md`).

## Mimari

### App yapısı ve servis katmanı

Her domain ayrı bir Django app'idir (nöbet, sınav, ders programı, devamsızlık, öğrenci vb. — tam
liste ve URL önekleri için `README.md` "Uygulama Modülleri" tablosuna bakın). `views.py` ince
tutulur; iş mantığı `<app>/services/` altındaki modüllerde yaşar (örn. `sinav/services/mazeret_ilp.py`,
`sorumluluk/services/takvim_motoru_ga.py`, `veriaktar/services/*_import_service.py`). Yeni iş mantığı
eklerken bu ayrımı koruyun: view → service çağrısı, service → model erişimi.

### Yetkilendirme (`okul/auth.py`)

Tüm rol/izin kontrolleri tek merkezden gelir — app'lerde tekrarlanmaz:
- `is_mudur_yardimcisi` / `mudur_yardimcisi_required` / `MudurYardimcisiMixin` — yalnızca müdür yardımcısı grubu (+ aktif `okul_yonetici` profili).
- `is_yonetici` / `yonetici_required` — `ogretmen` hariç tüm yönetici grupları (`mudur_yardimcisi`, `okul_muduru`, `rehber_ogretmen`, `disiplin_kurulu`).
- `is_ust_yonetici` / `ust_yonetici_required` / `UstYoneticiMixin` — yalnızca `mudur_yardimcisi` ve `okul_muduru` (planlama modüllerinde: nöbet, ders doldurma, sınav yönetimi, haftalık program).

Django grupları (`mudur_yardimcisi`, `okul_muduru`, `rehber_ogretmen`, `disiplin_kurulu`, `ogretmen`)
`kullanici_gruplari_olustur` komutuyla oluşturulur; her rolün yetki kapsamı için README'deki
"Kullanıcı Rolleri ve Yetkileri" tablosuna bakın. Yeni bir view/mixin yazarken önce `okul/auth.py`'de
uygun yardımcı olup olmadığını kontrol edin, tekrar tekrar grup kontrolü yazmayın.

### Aktif eğitim-öğretim yılı ve aktif tarih kavramı

Birçok modül (seçmeli dersler, ders programı, dönemsel raporlama) `OkulBilgi` singleton kaydındaki
**aktif eğitim-öğretim yılına** bağlıdır; bu kayıt admin panelinden (`Okul → Okul Bilgisi`) elle
oluşturulur ve yoksa ilgili modüller boş görünür (kurulum sonrası atlanabilecek bir adım değildir).

Ayrıca `okul.models.AktifVeriKonfigurasyonu` tablosu, veri türü başına (`ders_programi`,
`personel_listesi`, `nobet_listesi`) hangi `uygulama_tarihi`'nin geçerli olduğunu tutar; `okul/utils.py`
içindeki `get_aktif_tarih` / `set_aktif_tarih` / `get_aktif_nobet_tarihi` bu tabloyu okuyup yazar.
Tarihsiz sorgular (örn. "bugünün ders programı") bu konfigürasyon üzerinden çözülür, import servisleri
başarılı yüklemeden sonra `set_aktif_tarih` çağırmalıdır.

### Öğrenci aktiflik durumu (`Ogrenci.aktif`)

`ogrenci.Ogrenci.aktif` (BooleanField, default `True`) bir öğrencinin okulda hâlâ kayıtlı/aktif
olup olmadığını tutar. `secmelidersler.OgrenciTasdikname` kaydı eklenince (`/secmeli/tasdikname/` —
öğrenim hakkını kullanmış/tasdikname alan öğrenciler) ilgili öğrenci otomatik olarak `aktif=False`
yapılır (`secmelidersler/views.py: tasdikname_ekle`); kayıt silinince tekrar `aktif=True`'ya döner
(`tasdikname_sil`). `sinif`/`sube` alanları değişmez — geçmişte hangi sınıfta olduğu bilgisi kalır.

Bu yüzden **yeni bir "öğrenci seç/listele" sorgusu yazarken varsayılan olarak `.filter(aktif=True)`
ekleyin** (disiplin, rehberlik, müdüriyet çağrı, faaliyet, öğrenci nöbeti, devamsızlık alma, ders
programı/seçmeli ders planlama gibi güncel işlem ekranlarında bu zaten yapılıyor). İstisnalar:
zaten var olan bir kaydı pk ile çekmek (örn. bir disiplin görüşmesinin geçmişini görüntülemek),
geçmiş rapor/filtre dropdown'ları, Excel import eşleştirmeleri ve `ogrenci` app'inin kendi genel
öğrenci dizini/yönetim sayfaları — bunlar arşivlenmiş öğrencileri de görebilmeli.

### Excel içe aktarma (`veriaktar`)

`/veriaktar/` altında 5 adımlı bir sihirbaz personel, sınıf/şube, ders programı ve nöbet verilerini
Excel'den içe aktarır. Her veri türü için ayrı bir `*_import_service.py` vardır
(`veriaktar/services/`); `utility/services/` altında aynı isimli dosyalar da bulunur — ikisi
karıştırılmamalı, hangi app'in hangisini import ettiğine dikkat edin.

### Ortak sınav motoru (Kelebek) — `sinav` + `ortaksinav_engine`

`sinav` app'i modelleri/view'ları barındırır (`SinavBilgisi`, `OturmaPlani`, `TakvimUretim`,
`AlgoritmaParametreleri`); asıl optimizasyon mantığı `ortaksinav_engine/services/` altındadır
(`takvim.py`, `oturma.py`, `ders_analiz.py`, `veri_import.py`, `pdf_rapor.py`) ve ILP tabanlı takvim +
oturma planı üretimi için `PuLP`/`networkx` kullanır. Katılacak sınıf seviyeleri, kelebek/kendi sınıfı
dağılım oranı ve günlük maks. sınav sayısı `AlgoritmaParametreleri` üzerinden yapılandırılır.
Öğretmenlerin sınav günü kendi sınıflarının yerleşim listesini gördüğü gözetim ekranı
(`/sinav/gozetim/`) yalnızca o öğretmen gözetmen olarak atanmışsa ve sınav saatinden 50 dakika önce
itibaren aktif olur — bu zamanlama kısıtını değiştirirken dikkatli olun.

`sinav/services/` ise ayrı bir alt sistemdir: **mazeret sınavı** (makeup exam) ILP dağıtımı ve
takvimi (`mazeret_ilp.py`, `mazeret_dagitim.py`, `mazeret_takvim.py`) — Kelebek motoruyla karıştırmayın.

`sorumluluk` app'i de kendi ILP/genetik algoritma motorunu taşır (`takvim_motoru.py` vs.
`takvim_motoru_ga.py`) — sorumluluk sınavı (responsibility exam) için ayrı bir optimizasyon problemidir.

### Şablonlar ve statik dosyalar

Her app kendi `templates/<app_adı>/` ve gerekirse `static/` klasörünü taşır (Django `APP_DIRS`
şablon yükleyicisi). Ortak statikler `main/static/` ve kök `static/`de; `collectstatic` çıktısı
`staticfiles/`e gider (repoya girmez).

## Notlar

- `main.context_processors.kullanici_rol` tüm şablonlara kullanıcının rolünü enjekte eder — yeni bir
  role dayalı UI koşulu eklerken önce bu context processor'ı kontrol edin.
- `backups/` altındaki `.dump`/`.sql` dosyaları gerçek veritabanı yedekleridir, düzenlenmez/silinmez.
- `SunucuTarifi.md` prod sunucu kurulum notlarıdır; gizli bilgi içermez (daha önce sızan şifreler
  placeholder ile değiştirildi) ama yine de yeni gerçek kimlik bilgileri eklenmemelidir.
