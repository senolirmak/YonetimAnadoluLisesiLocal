# Nöbet Yönetim Sistemi

Okul personelinin haftalık nöbet görevlerini, ders doldurma listelerini, devamsızlık kayıtlarını, öğrenci takip süreçlerini ve ortak sınav oturma düzenini yöneten Django tabanlı web uygulaması.

---

## Özellikler

- **Nöbet Dağıtımı** — Haftalık otomatik ve manuel nöbet dağıtımı
- **Ders Doldurma** — Devamsız öğretmen yerine ders dolduracak öğretmen atama
- **Günün Nöbetçileri** — Günlük nöbet çizelgesi görüntüleme ve PNG dışa aktarma
- **Devamsızlık Takibi** — Personel ve öğrenci devamsızlık kayıtları
- **Ders Programı** — Öğretmen ve sınıf bazlı ders programı yönetimi
- **Veri Aktarma** — 5 adımlı Excel import sihirbazı (personel, sınıf/şube, ders programı, nöbet verileri)
- **Dijital Pano** — Duyuru, etkinlik ve medya içerik yönetimi (kiosk)
- **Öğrenci Modülü** — Öğrenci bilgileri, rehberlik, disiplin, müdüriyet çağrı kayıtları
- **Ortak Sınav Yönetimi (Kelebek)** — Sınav takvimi, oturma planı üretimi, salon ve sıra ataması, PDF raporlama
- **Sınav Gözetim** — Öğretmenlere sınav günü kendi sınıflarının Kelebek yerleşim listesini gösterir
- **Raporlama** — PDF, PNG ve Excel dışa aktarma

---

## Teknoloji Yığını

| Katman | Teknoloji |
|---|---|
| Backend | Django 6.0.3, Python 3.12 |
| Veritabanı | PostgreSQL |
| ORM | Django ORM (psycopg2-binary) |
| Excel | openpyxl 3.1.5, pandas 3.0.1 |
| PDF | reportlab 4.4.10, pdf2image 1.17.0 |
| Görsel | Pillow 12.1.1 |
| Optimizasyon | networkx 3.6.1, PuLP 3.3.0 |
| Env | python-decouple, python-dotenv |
| Sunucu | Gunicorn 25.1.0 |

---

## Kurulum

### Gereksinimler

- Python 3.12+
- PostgreSQL
- pip

### 1. Depoyu Klonlayın

```bash
git clone <repo-url>
cd nobet_proje
```

### 2. Sanal Ortam Oluşturun

```bash
python -m venv .venv
source .venv/bin/activate        # Linux/macOS
.venv\Scripts\activate           # Windows
```

### 3. Bağımlılıkları Yükleyin

```bash
pip install -r requirements.txt
```

### 4. Ortam Değişkenlerini Ayarlayın

Proje kök dizininde `.env` dosyası oluşturun:

```env
SECRET_KEY=your-secret-key-here
DEBUG=True

DB_NAME=nobet_db
DB_USER=nobet_user
DB_PASSWORD=your-db-password
DB_HOST=localhost
DB_PORT=5432
```

### 5. Veritabanı Migrations

```bash
python manage.py migrate
```

### 6. Kullanıcı Gruplarını Oluşturun

```bash
python manage.py kullanici_gruplari_olustur

# Örnek kullanıcılarla birlikte:
python manage.py kullanici_gruplari_olustur --ornek-kullanici
```

### 7. Öğretmen Kullanıcılarını Oluşturun

NobetPersonel kayıtlarından otomatik kullanıcı oluşturur:

```bash
# Önce önizle:
python manage.py ogretmen_kullanici_olustur

# Uygula:
python manage.py ogretmen_kullanici_olustur --kaydet
```

### 8. Süper Kullanıcı Oluşturun

```bash
python manage.py createsuperuser
```

### 9. Statik Dosyaları Toplayın

```bash
python manage.py collectstatic
```

### 10. Geliştirme Sunucusunu Başlatın

```bash
python manage.py runserver
```

Uygulama `http://127.0.0.1:8000/` adresinde çalışacaktır.

---

## Kullanıcı Rolleri ve Yetkileri

| Rol | Yetki |
|---|---|
| `mudur_yardimcisi` | Tüm işlemler (nöbet dağıtım, rotasyon, devamsızlık, ders doldurma, veri aktarma, sınav yönetimi) |
| `okul_muduru` | Yalnızca görüntüleme |
| `rehber_ogretmen` | Görüntüleme + rehberlik işlemleri + sınav gözetim listesi |
| `disiplin_kurulu` | Görüntüleme + disiplin işlemleri + sınav gözetim listesi |
| `ogretmen` | Görüntüleme + yoklama + sınav gözetim listesi |

> Sınav gözetim listesi (`/sinav/gozetim/`) yalnızca o öğretmenin gözetmen olarak atandığı slotlar varsa ve sınav saatinden 50 dakika önce itibaren aktif hale gelir.

---

## Uygulama Modülleri

| Uygulama | URL | Açıklama |
|---|---|---|
| `main` | `/` | Ana panel ve öğretmen görünümleri |
| `nobet` | `/dagitim/` | Haftalık nöbet dağıtımı |
| `nobet` | `/ders-doldurma/` | Ders doldurma listesi |
| `nobet` | `/gunun-nobetcileri/` | Günün nöbet çizelgesi |
| `sinav` | `/sinav/` | Ortak sınav yönetimi (Kelebek) — yöneticiye özel |
| `dersprogrami` | `/dersprogrami/` | Ders programı yönetimi |
| `personeldevamsizlik` | `/personeldevamsizlik/` | Personel devamsızlık kayıtları |
| `veriaktar` | `/veriaktar/` | Excel veri aktarma sihirbazı |
| `personel` | `/personel/` | Personel listesi ve yönetimi |
| `ogrenci` | `/ogrenci/` | Öğrenci bilgileri |
| `devamsizlik` | `/devamsizlik/` | Öğrenci devamsızlık |
| `faaliyet` | `/faaliyet/` | Faaliyet kayıtları |
| `rehberlik` | `/rehberlik/` | Rehberlik görüşmeleri |
| `disiplin` | `/disiplin/` | Disiplin görüşmeleri |
| `muduriyetcagri` | `/muduriyetcagri/` | Müdüriyet çağrı kayıtları |
| `cagri` | `/cagri/` | Öğrenci çağrı yönlendirme |
| `ogrencinobet` | `/ogrencinobet/` | Öğrenci nöbet görevleri |
| `pano` | `/pano/` | Dijital pano / kiosk |
| `admin` | `/admin/` | Django yönetim paneli |

**Auth URL'leri:**
- Giriş: `/giris/`
- Çıkış: `/cikis/`

---

## Yönetim Komutları

```bash
# Kullanıcı gruplarını oluştur
python manage.py kullanici_gruplari_olustur

# Öğretmen kullanıcılarını otomatik oluştur (önizleme)
python manage.py ogretmen_kullanici_olustur
# Uygula:
python manage.py ogretmen_kullanici_olustur --kaydet

# Veri aktarma komutları (yönetici için)
python manage.py PersonelAktar
python manage.py NobetciAktar
python manage.py OkulDersProgramiAktar
python manage.py SinifSubeAktar
```

---

## Veritabanı Yedeği

```bash
PGPASSWORD=<şifre> pg_dump -U nobet_user -h localhost -F c -f backups/nobet_db_$(date +%Y%m%d_%H%M%S).dump nobet_db

# Geri yüklemek için:
PGPASSWORD=<şifre> pg_restore -U nobet_user -h localhost -d nobet_db backups/<dosya>.dump
```

---

## Proje Yapısı

```
nobet_proje/
├── config/                  # Django ayarları ve ana URL konfigürasyonu
│   ├── settings.py
│   └── urls.py
├── nobet/                   # Nöbet çekirdek uygulaması
│   ├── models.py            # NobetPersonel, NobetOgretmen, NobetGorevi, ...
│   ├── views.py
│   ├── services/
│   ├── management/commands/
│   └── templates/
├── sinav/                   # Ortak sınav yönetimi (Kelebek)
│   ├── models.py            # SinavBilgisi, OturmaPlani, TakvimUretim, ...
│   ├── views.py
│   ├── utils.py             # gozetmen_bul, onceki_ders_saati
│   └── templates/sinav/
├── ortaksinav_engine/       # Sınav takvimi ve oturma optimizasyon motoru
├── dersprogrami/            # Ders programı
├── personeldevamsizlik/     # Personel devamsızlık
├── veriaktar/               # Excel import sihirbazı
│   └── services/            # PersonelIsleyici, NobetIsleyici, ...
├── utility/                 # Paylaşılan servisler ve yönetim komutları
├── main/                    # Ana panel ve öğretmen görünümleri
├── personel/                # Personel yönetimi
├── ogrenci/                 # Öğrenci modülü
├── devamsizlik/             # Öğrenci devamsızlık
├── faaliyet/                # Faaliyet kayıtları
├── rehberlik/               # Rehberlik görüşmeleri
├── disiplin/                # Disiplin
├── muduriyetcagri/          # Müdüriyet çağrıları
├── cagri/                   # Öğrenci çağrı yönlendirme
├── ogrencinobet/            # Öğrenci nöbetleri
├── pano/                    # Dijital pano
├── duyuru/                  # Duyurular
├── backups/                 # Veritabanı yedekleri
├── manage.py
└── requirements.txt
```

---

## Veritabanı Tabloları (Seçili)

| Tablo | Model | Açıklama |
|---|---|---|
| `nobet_personel` | NobetPersonel | Tüm okul personeli |
| `nobet_ogretmen` | NobetOgretmen | Ders görevi olan öğretmenler |
| `nobet_gorevi` | NobetGorevi | Haftalık nöbet atamaları |
| `nobet_gecmis` | NobetGecmisi | Nöbet geçmişi |
| `nobet_istatistik` | NobetIstatistik | Nöbet istatistikleri |
| `nobet_dersprogrami` | NobetDersProgrami | Ders programı |
| `nobet_devamsizlik` | Devamsizlik | Personel devamsızlık |
| `gunluk_nobet_cizelgesi` | GunlukNobetCizelgesi | Günlük nöbet çizelgesi |
| `okul_bilgi` | OkulBilgi | Okul bilgileri |
| `sinav_sinav_bilgisi` | SinavBilgisi | Aktif sınav tanımı |
| `sinav_oturma_plani` | OturmaPlani | Öğrenci salon ve sıra atamaları |
| `sinav_takvim_uretim` | TakvimUretim | Sınav takvimi üretim kayıtları |

---

## Lisans

Bu proje okul yönetim amaçlı geliştirilmiş özel bir yazılımdır.
