# Bu app'in bir veritabanı modeli yoktur: yedekler, tek kaynak olarak `backups/`
# dizinindeki `.dump` dosyaları üzerinden yönetilir (bkz. yedekleme/services/yedek_servisi.py).
# Ayrı bir model tutmak, dosya sistemiyle senkron kalması gereken ikinci bir kayıt
# kaynağı yaratıp deploy.sh'in otomatik aldığı yedekleri de görünmez kılardı.
