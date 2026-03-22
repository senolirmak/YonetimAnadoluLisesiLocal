# Pardus Sunucuya Kurulum Rehberi

Projeyi Pardus Server yüklü bilgisayara `/opt/akalyonetim` altına kurma adımları.

---

## 1. Sunucuya Proje Dosyalarını Kopyala

Geliştirme makinesinden sunucuya aktarın:

```bash
# Geliştirme makinesinde — sunucuya gönder
rsync -av --exclude='.venv' --exclude='__pycache__' --exclude='*.pyc' \
  --exclude='.env' --exclude='backups/' \
  /home/senolirmak/vcodeproject/nobet_proje/ \
  kullanici@sunucu-ip:/opt/akalyonetim/
```

Ya da ZIP ile:
```bash
# Geliştirme makinesinde
cd /home/senolirmak/vcodeproject
zip -r nobet_proje.zip nobet_proje/ --exclude "nobet_proje/.venv/*" --exclude "nobet_proje/__pycache__/*"

# Sunucuya kopyala
scp nobet_proje.zip kullanici@sunucu-ip:/opt/
```

---

## 2. Sunucuda Hazırlık

```bash
# Pardus/Debian paketleri
sudo apt update
sudo apt install -y python3.12 python3.12-venv python3-pip \
  postgresql postgresql-contrib nginx git

# Proje dizini
sudo mkdir -p /opt/akalyonetim
sudo chown $USER:$USER /opt/akalyonetim

# ZIP ile gönderdiyseniz
cd /opt
sudo unzip nobet_proje.zip
sudo mv nobet_proje/* akalyonetim/
```

---

## 3. PostgreSQL Kurulumu

```bash
sudo -u postgres psql <<EOF
CREATE USER nobet_user WITH PASSWORD '452869Zx.c';
CREATE DATABASE nobet_db OWNER nobet_user;
GRANT ALL PRIVILEGES ON DATABASE nobet_db TO nobet_user;
EOF
```

---

## 4. Python Ortamı ve Bağımlılıklar

```bash
cd /opt/akalyonetim

python3.12 -m venv .venv
source .venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt
```

---

## 5. .env Dosyası Oluştur

```bash
cat > /opt/akalyonetim/.env <<EOF
SECRET_KEY=buraya-guclu-bir-secret-key-yazin
DEBUG=False

DB_NAME=nobet_db
DB_USER=nobet_user
DB_PASSWORD=452869Zx.c
DB_HOST=localhost
DB_PORT=5432

ALLOWED_HOSTS=sunucu-ip,alan-adi.com
EOF

chmod 600 /opt/akalyonetim/.env
```

---

## 6. Django Kurulum Adımları

```bash
cd /opt/akalyonetim
source .venv/bin/activate

python manage.py migrate
python manage.py collectstatic --noinput
python manage.py kullanici_gruplari_olustur
python manage.py createsuperuser
```

---

## 7. Gunicorn Systemd Servisi

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
ExecStart=/opt/akalyonetim/.venv/bin/gunicorn \
    --workers 3 \
    --bind unix:/run/akalyonetim.sock \
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

## 8. Nginx Yapılandırması

```bash
sudo nano /etc/nginx/sites-available/akalyonetim
```

```nginx
server {
    listen 80;
    server_name sunucu-ip alan-adi.com;

    location /static/ {
        alias /opt/akalyonetim/staticfiles/;
    }

    location /media/ {
        alias /opt/akalyonetim/media/;
    }

    location / {
        proxy_pass http://unix:/run/akalyonetim.sock;
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

## 9. Veritabanı Yedeğini Aktar (Opsiyonel)

Geliştirme makinesindeki veriyi sunucuya taşımak isterseniz:

```bash
# Geliştirme makinesinde
PGPASSWORD=452869Zx.c pg_dump -U nobet_user -h localhost -F c -f nobet_db.dump nobet_db
scp nobet_db.dump kullanici@sunucu-ip:/opt/

# Sunucuda
PGPASSWORD=452869Zx.c pg_restore -U nobet_user -h localhost -d nobet_db /opt/nobet_db.dump
```

---

## Kontrol

| Komut | Amaç |
|---|---|
| `sudo systemctl status akalyonetim` | Gunicorn durumu |
| `sudo journalctl -u akalyonetim -f` | Canlı loglar |
| `sudo systemctl status nginx` | Nginx durumu |
| `sudo nginx -t` | Nginx config testi |

---

> `config/settings.py` dosyasında `ALLOWED_HOSTS` ayarının sunucu IP'sini içerdiğinden emin olun.
