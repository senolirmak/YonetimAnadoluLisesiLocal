#!/bin/bash
# Sunucu güncelleme scripti
# Sunucuda: bash deploy.sh
# Uzaktan:  ssh senol@akal-yonetim.local "bash /opt/akalyonetim/deploy.sh"
set -e

cd /opt/akalyonetim

echo "Kod çekiliyor..."
git pull origin main

echo "Paketler kontrol ediliyor..."
source venv/bin/activate
pip install -r requirements.txt --quiet

echo "Migration çalıştırılıyor..."
python manage.py migrate

echo "Gunicorn yeniden başlatılıyor..."
sudo systemctl restart gunicorn

echo "Dağıtım tamamlandı."
