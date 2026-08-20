# varsayilan_ders_verileri.json

Her Anadolu Lisesi için genel olarak geçerli olan (MEB haftalık ders çizelgesine
dayanan) referans veri: branşlar, Ortak Ders Havuzu, Seçmeli Ders Havuzu,
Zorunlu (Ortak) Dersler ve Seçmeli Ders Grupları. Bu okulun gerçek, kullanımda
olan verisinden dışa aktarılmıştır (2026-2027 eğitim-öğretim yılı) — Django'nun
`dumpdata` formatında değil, `varsayilan_ders_verilerini_yukle` komutunun
beklediği sade bir şema kullanır (pk yerine doğal anahtar — `ders_adi`/`adi` —
ve branş adlarıyla referans verir, böylece farklı bir kurulumdaki farklı pk'lara
bağımlı değildir).

Yeni bir kurulumda bu dosyayı yüklemek için:

```bash
python manage.py varsayilan_ders_verilerini_yukle
```

Ortak Ders Havuzu ve Seçmeli Ders Havuzu (eğitim yılından bağımsız) her zaman
yüklenir. Zorunlu (Ortak) Dersler ve Seçmeli Ders Grupları (eğitim yılına bağlı)
için aktif bir `EgitimOgretimYili` gerekir — `OkulBilgi.okul_egtyil` üzerinden
otomatik bulunur ya da `--egitim-yili "2025-2026"` ile açıkça belirtilebilir.

Komut idempotenttir: tekrar çalıştırmak var olan kayıtları güncelleyip yenilerini
ekler, kopya oluşturmaz.

Veriyi güncel tutmak isterseniz (örn. müfredat değişikliğinde), bu dosyayı elle
düzenleyebilir ya da `python manage.py dumpdata` benzeri bir dışa aktarma
scriptiyle yeniden üretebilirsiniz — script bu README'nin yanına eklenmemiştir,
gerekirse tekrar yazılabilir.
