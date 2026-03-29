# Pardus Sunucuya Kurulum / Güncelleme Rehberi

Hedef dizin: `/opt/akalyonetim`

---

## SENARYO A — İLK KEZ KURULUM (sunucuda proje hiç yok)

### A1. Pardus Paketleri

```bash
sudo apt update
sudo apt install -y python3.12 python3.12-venv python3-pip \
  postgresql postgresql-contrib nginx poppler-utils
```

> `poppler-utils` → pdf2image kütüphanesi için gerekli

---

### A2. Proje Dosyalarını Sunucuya Kopyala

**Geliştirme makinesinde** çalıştır:

```bash
rsync -av \
  --exclude='.venv' --exclude='__pycache__' --exclude='*.pyc' \
  --exclude='.env' --exclude='backups/' --exclude='media/' \
  /home/senolirmak/vcodeproject/nobet_proje/ \
  KULLANICI@SUNUCU-IP:/opt/akalyonetim/
```

---

### A3. PostgreSQL Kurulumu

**Sunucuda** çalıştır:

```bash
sudo -u postgres psql <<EOF
CREATE USER nobet_user WITH PASSWORD '452869Zx.c';
CREATE DATABASE nobet_db OWNER nobet_user;
GRANT ALL PRIVILEGES ON DATABASE nobet_db TO nobet_user;
EOF
```

---

### A4. Python Ortamı

```bash
cd /opt/akalyonetim
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

---

### A5. .env Dosyası

```bash
cat > /opt/akalyonetim/.env <<EOF
SECRET_KEY=buraya-en-az-50-karakterli-guclu-bir-key-yazin
DEBUG=False

DB_NAME=nobet_db
DB_USER=nobet_user
DB_PASSWORD=452869Zx.c
DB_HOST=localhost
DB_PORT=5432

TIME_ZONE=Europe/Istanbul
LANGUAGE_CODE=tr-tr
USE_I18N=True
USE_TZ=True

ALLOWED_HOSTS=SUNUCU-IP,alan-adi.com,localhost
EOF

chmod 600 /opt/akalyonetim/.env
```

---

### A6. Veritabanı Yedeğini Aktar (önerilen)

Geliştirme makinesindeki güncel veriyi taşımak için:

**Geliştirme makinesinde:**

```bash
# En güncel .dump dosyasını sunucuya gönder
scp /home/senolirmak/vcodeproject/nobet_proje/backups/nobet_db_20260322_195806.dump \
  KULLANICI@SUNUCU-IP:/opt/nobet_db.dump
```

**Sunucuda:**

```bash
PGPASSWORD=452869Zx.c pg_restore \
  -U nobet_user -h localhost -p 5432 \
  -d nobet_db --clean --if-exists \
  /opt/nobet_db.dump
```

---

### A7. Django Kurulum Adımları

```bash
cd /opt/akalyonetim
source .venv/bin/activate

python manage.py migrate
python manage.py collectstatic --noinput
python manage.py kullanici_gruplari_olustur
python manage.py createsuperuser
```

> Veritabanı yedeğinden geri yüklediyseniz `migrate` ve `createsuperuser`
> atlanabilir — kullanıcılar zaten gelir.

---

### A8. Gunicorn Systemd Servisi

```bash
sudo nano /etc/systemd/system/akalyonetim.service
```

```ini
[Unit]
Description=Akal Yönetim Django
After=network.target postgresql.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/akalyonetim
EnvironmentFile=/opt/akalyonetim/.env

# systemd her başlatmada /run/akalyonetim/ dizinini otomatik oluşturur.
# /run tmpfs olduğundan reboot sonrası dizin kaybolur — RuntimeDirectory bunu çözer.
RuntimeDirectory=akalyonetim
RuntimeDirectoryMode=0755

ExecStart=/opt/akalyonetim/.venv/bin/gunicorn \
    --workers 3 \
    --bind unix:/run/akalyonetim/akalyonetim.sock \
    config.wsgi:application
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo chown -R www-data:www-data /opt/akalyonetim
sudo systemctl daemon-reload
sudo systemctl enable akalyonetim
sudo systemctl start akalyonetim
sudo systemctl status akalyonetim
```

---

### A9. Nginx Yapılandırması

```bash
sudo nano /etc/nginx/sites-available/akalyonetim
```

```nginx
server {
    listen 80;
    server_name SUNUCU-IP alan-adi.com;

    client_max_body_size 20M;

    location /static/ {
        alias /opt/akalyonetim/staticfiles/;
    }

    location /media/ {
        alias /opt/akalyonetim/media/;
    }

    location / {
        proxy_pass http://unix:/run/akalyonetim/akalyonetim.sock;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/akalyonetim /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

---

---

## SENARYO B — ÖNCEKİ VERSİYONU GÜNCELLEME (sunucuda eski sürüm çalışıyor)

### B1. Servisi Durdur

```bash
sudo systemctl stop akalyonetim
```

---

### B2. Veritabanı Yedeği Al (sunucuda, güvenlik için)

```bash
PGPASSWORD=452869Zx.c pg_dump -Fc \
  -U nobet_user -h localhost -p 5432 nobet_db \
  > /opt/yedek_guncelleme_oncesi_$(date +%Y%m%d_%H%M%S).dump
```

---

### B3. Proje Dosyalarını Güncelle

**Geliştirme makinesinde** çalıştır:

```bash
rsync -av \
  --exclude='.venv' --exclude='__pycache__' --exclude='*.pyc' \
  --exclude='.env' --exclude='backups/' --exclude='media/' \
  /home/senolirmak/vcodeproject/nobet_proje/ \
  KULLANICI@SUNUCU-IP:/opt/akalyonetim/
```

---

### B4. Bağımlılıkları Güncelle

**Sunucuda:**

```bash
cd /opt/akalyonetim
source .venv/bin/activate
pip install -r requirements.txt
```

---

### B5. Migration ve Static Dosyalar

```bash
cd /opt/akalyonetim
source .venv/bin/activate

python manage.py migrate
python manage.py collectstatic --noinput --clear
python manage.py kullanici_gruplari_olustur
```

---

### B6. İzinleri Düzelt ve Servisi Başlat

```bash
sudo chown -R www-data:www-data /opt/akalyonetim
sudo systemctl start akalyonetim
sudo systemctl status akalyonetim
```

---

---

## MEVCUT SUNUCUYU GÜNCELLEME (RuntimeDirectory geçişi)

Servis dosyasını yukarıdaki yeni haliyle güncelledikten sonra:

```bash
sudo systemctl daemon-reload
sudo systemctl restart akalyonetim
sudo systemctl restart nginx
# Kontrol:
ls -la /run/akalyonetim/   # dizin ve sock görünmeli
```

---

## KONTROL KOMUTLARI

| Komut | Amaç |
|---|---|
| `sudo systemctl status akalyonetim` | Gunicorn durumu |
| `sudo journalctl -u akalyonetim -f` | Canlı loglar |
| `sudo systemctl status nginx` | Nginx durumu |
| `sudo nginx -t` | Nginx config testi |
| `sudo systemctl restart akalyonetim` | Gunicorn yeniden başlat |
| `sudo systemctl restart nginx` | Nginx yeniden başlat |
| `ls -la /run/akalyonetim/` | Socket dizini kontrolü |

---

## REQUIREMENTS (güncel paketler)

```
Django==6.0.3
gunicorn==25.1.0
psycopg2-binary==2.9.11
pandas==3.0.1
numpy==2.4.2
openpyxl==3.1.5
xlrd==2.0.2
reportlab==4.4.10
pdf2image==1.17.0
pillow==12.1.1
PuLP==3.3.0
networkx==3.6.1
python-dotenv==1.0.1
python-decouple==3.8
```

---

## NOTLAR

- `DEBUG=False` olduğunda `.env` dosyasındaki `SECRET_KEY` güçlü bir değer olmalı
- Sunucu IP'si veya alan adı `ALLOWED_HOSTS`'a eklenmeli
- `media/` dizini rsync'e dahil edilmez — PDF çıktıları, yüklenen dosyalar orada kalır
- Port 80 dışında çalıştırmak isterseniz Nginx'teki `listen 80` değiştirilmeli
