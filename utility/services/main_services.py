import random
from datetime import datetime
from datetime import time as Time
from typing import Any

import pandas as pd
from django.db import transaction
from django.utils import timezone

from dersprogrami.models import NobetDersProgrami
from nobet.models import (
    NobetAtanamayan,
    NobetGecmisi,
    NobetGorevi,
    NobetIstatistik,
    NobetOgretmen,
    NobetPersonel,
    SinifSube,
)


def _generate_kimlikno() -> str:
    """
    Sistemde bulunmayan öğretmen için 11 haneli benzersiz placeholder kimlik no üretir.
    Gerçek TC kimlik no algoritmasıyla çakışmaması için 999XXXXXXXX aralığı kullanılır.
    """
    while True:
        kimlikno = str(random.randint(99900000000, 99999999999))
        if not NobetPersonel.objects.filter(kimlikno=kimlikno).exists():
            return kimlikno


def _get_or_create_eksik_personel(adi_soyadi: str):
    """
    İsme göre NobetPersonel arar; bulamazsa otomatik oluşturur.
    NobetOgretmen kaydını da garanti eder.
    Döner: (NobetOgretmen instance, personel_created: bool)
    """
    personel = NobetPersonel.objects.filter(adi_soyadi=adi_soyadi).first()
    personel_created = False
    if not personel:
        personel = NobetPersonel.objects.create(
            adi_soyadi=adi_soyadi,
            kimlikno=_generate_kimlikno(),
            brans="Bilinmiyor",
            gorev_tipi="Öğretmen",
            nobeti_var=True,
            sabit_nobet=False,
            cinsiyet=True,
        )
        personel_created = True
    ogretmen, _ = NobetOgretmen.objects.get_or_create(personel=personel)
    return ogretmen, personel_created


class EOkulVeriAktar:
    def __init__(self) -> None:
        pass

    def parse_time(self, t: Any) -> Time | None:
        if isinstance(t, str):
            try:
                return datetime.strptime(t, "%H:%M").time()
            except ValueError:
                return None
        elif isinstance(t, pd.Timestamp):
            return t.time()
        elif isinstance(t, datetime):
            return t.time()
        return t  # zaten time objesi

    # ------------------ PERSONEL ------------------
    def save_yeni_veri_NobetPersonel(self, personel_df: pd.DataFrame) -> dict[str, Any]:
        status = {"inserted": 0, "updated": 0, "errors": 0, "status": "success", "message": ""}
        required_columns = ["adi_soyadi", "brans", "kimlikno", "gorev_tipi", "cinsiyet"]
        missing = [col for col in required_columns if col not in personel_df.columns]
        if missing:
            return {
                "status": "error",
                "message": f"Eksik sütun(lar): {', '.join(missing)}",
                **status,
            }

        personel_df = personel_df.dropna(subset=["adi_soyadi", "brans", "kimlikno"])
        try:
            with transaction.atomic():
                for _, row in personel_df.iterrows():
                    try:
                        obj, created = NobetPersonel.objects.update_or_create(
                            kimlikno=str(row["kimlikno"]),
                            defaults={
                                "adi_soyadi": row["adi_soyadi"],
                                "brans": row["brans"],
                                "gorev_tipi": row["gorev_tipi"],
                                "cinsiyet": row["cinsiyet"],
                            },
                        )
                        NobetOgretmen.objects.get_or_create(personel=obj)
                        status["inserted" if created else "updated"] += 1
                    except Exception as e:
                        print(f"Satır hatası: {e}")
                        status["errors"] += 1
            status["message"] = (
                f"Personel: {status['inserted']} eklendi, {status['updated']} güncellendi, {status['errors']} hata."
            )
        except Exception as e:
            status.update({"status": "error", "message": f"Veritabanı hatası: {str(e)}"})
        return status

    # ------------------ ÖĞRETMEN ------------------
    def save_yeni_veri_NobetOgretmen(self, personel_df: pd.DataFrame) -> dict[str, Any]:
        """
        Öğretmen kayıtlarını veritabanına ekler veya günceller.
        Aynı adi_soyadi + brans + gorev_tipi + uygulama_tarihi kombinasyonu varsa update eder.
        """
        status = {"inserted": 0, "updated": 0, "errors": 0, "status": "success", "message": ""}

        required_columns = [
            "adi_soyadi",
            "brans",
            "nobeti_var",
            "gorev_tipi",
            "uygulama_tarihi",
            "cinsiyet",
        ]
        missing = [col for col in required_columns if col not in personel_df.columns]
        if missing:
            return {
                "status": "error",
                "message": f"Eksik sütun(lar): {', '.join(missing)}",
                **status,
            }

        # Temizlik
        personel_df = personel_df.dropna(subset=["adi_soyadi", "brans", "nobeti_var"])
        personel_df["adi_soyadi"] = personel_df["adi_soyadi"].astype(str).str.strip()
        personel_df["brans"] = personel_df["brans"].astype(str).str.strip()
        personel_df["gorev_tipi"] = personel_df["gorev_tipi"].astype(str).str.strip()

        try:
            with transaction.atomic():
                for _, row in personel_df.iterrows():
                    try:
                        # 🔹 nobeti_var normalize et
                        nobeti_var_raw = str(row["nobeti_var"]).strip().lower()
                        nobeti_var = (
                            False if nobeti_var_raw in ["0", "false", "hayır", "no"] else True
                        )

                        # Tarihi normalize et (saat kısmını sıfırla)
                        uygulama_tarihi = pd.to_datetime(row["uygulama_tarihi"]).replace(
                            hour=0, minute=0, second=0, microsecond=0
                        )
                        if timezone.is_naive(uygulama_tarihi):
                            uygulama_tarihi = timezone.make_aware(uygulama_tarihi)

                        # Personeli bul
                        personel = NobetPersonel.objects.filter(
                            adi_soyadi=row["adi_soyadi"]
                        ).first()
                        if not personel:
                            print(f"⚠️ Personel bulunamadı: {row['adi_soyadi']}")
                            status["errors"] += 1
                            continue

                        # Personel bilgilerini güncelle
                        personel.brans = row["brans"]
                        personel.gorev_tipi = row["gorev_tipi"]
                        personel.cinsiyet = row["cinsiyet"]
                        personel.nobeti_var = nobeti_var
                        personel.save()

                        # NobetOgretmen kaydını güncelle veya oluştur
                        obj, created = NobetOgretmen.objects.update_or_create(
                            personel=personel, defaults={"uygulama_tarihi": uygulama_tarihi}
                        )
                        status["inserted" if created else "updated"] += 1

                    except Exception as row_err:
                        print(f"⚠️ Satır hatası ({row.get('adi_soyadi', '???')}): {row_err}")
                        status["errors"] += 1

            status["message"] = (
                f"Öğretmen: {status['inserted']} eklendi, "
                f"{status['updated']} güncellendi, "
                f"{status['errors']} hata oluştu."
            )

        except Exception as e:
            status.update({"status": "error", "message": f"Veritabanı hatası: {str(e)}"})

        return status

    # ------------------ NÖBET GÖREVİ ------------------
    def save_yeni_veri_NobetGorevi(self, nobet_df: pd.DataFrame) -> dict[str, Any]:
        """
        Belirtilen uygulama tarihlerindeki kayıtları siler ve yenilerini ekler.
        Sistemde bulunmayan öğretmenler otomatik olarak oluşturulur.
        """
        nobet_df = nobet_df.dropna(subset=["nobetci"])
        status = {
            "inserted": 0,
            "updated": 0,
            "errors": 0,
            "otomatik_eklenen": 0,
            "otomatik_eklenen_isimler": [],
            "status": "success",
            "message": "",
        }

        if nobet_df.empty:
            status["message"] = "İşlenecek veri yok."
            return status

        try:
            with transaction.atomic():
                # 1. Silinecek tarihleri belirle
                dates_to_delete = set()
                for dt in nobet_df["uygulama_tarihi"].unique():
                    d = pd.to_datetime(dt).replace(hour=0, minute=0, second=0, microsecond=0)
                    if timezone.is_naive(d):
                        d = timezone.make_aware(d)
                    dates_to_delete.add(d)

                if dates_to_delete:
                    NobetGorevi.objects.filter(uygulama_tarihi__in=dates_to_delete).delete()

                # 2. Öğretmen map'ini hazırla
                ogretmen_map = {
                    o.personel.adi_soyadi: o
                    for o in NobetOgretmen.objects.select_related("personel").all()
                }

                objs_to_create = []
                for _, row in nobet_df.iterrows():
                    try:
                        ogretmen_adi = str(row["nobetci"]).strip()
                        ogretmen = ogretmen_map.get(ogretmen_adi)

                        if not ogretmen:
                            ogretmen, created = _get_or_create_eksik_personel(ogretmen_adi)
                            ogretmen_map[ogretmen_adi] = ogretmen
                            if created:
                                status["otomatik_eklenen"] += 1
                                status["otomatik_eklenen_isimler"].append(ogretmen_adi)

                        uygulama_tarihi = pd.to_datetime(row["uygulama_tarihi"]).replace(
                            hour=0, minute=0, second=0, microsecond=0
                        )
                        if timezone.is_naive(uygulama_tarihi):
                            uygulama_tarihi = timezone.make_aware(uygulama_tarihi)

                        objs_to_create.append(
                            NobetGorevi(
                                ogretmen=ogretmen,
                                uygulama_tarihi=uygulama_tarihi,
                                nobet_gun=row["nobet_gun"],
                                nobet_yeri=row["nobet_yeri"],
                            )
                        )
                    except Exception as row_error:
                        print(f"⚠️ Satır hatası ({row.get('nobetci', '???')}): {row_error}")
                        status["errors"] += 1

                if objs_to_create:
                    NobetGorevi.objects.bulk_create(objs_to_create)
                    status["inserted"] = len(objs_to_create)

            status["message"] = (
                f"Nöbet: {status['inserted']} kayıt eklendi"
                + (f", {status['otomatik_eklenen']} yeni personel otomatik oluşturuldu" if status["otomatik_eklenen"] else "")
                + (f", {status['errors']} satır hatalı" if status["errors"] else "")
                + "."
            )

        except Exception as e:
            status.update(
                {
                    "status": "error",
                    "message": f"İşlem başarısız, değişiklikler geri alındı: {str(e)}",
                    "inserted": 0,
                }
            )

        return status

    # ------------------ DERS PROGRAMI ------------------
    def save_yeni_veri_NobetDersProgrami(self, program_df: pd.DataFrame) -> dict[str, Any]:
        """
        Aynı uygulama_tarihi için kayıtları siler, yenilerini ekler.
        Sistemde bulunmayan öğretmenler otomatik olarak oluşturulur.
        """
        program_df = program_df.dropna(subset=["ders_ogretmeni"])
        status = {
            "inserted": 0,
            "updated": 0,
            "errors": 0,
            "otomatik_eklenen": 0,
            "otomatik_eklenen_isimler": [],
            "status": "success",
            "message": "",
        }

        if program_df.empty:
            status["message"] = "İşlenecek veri yok."
            return status

        try:
            with transaction.atomic():
                # 1. Silinecek tarihleri belirle
                dates_to_delete = set()
                for dt in program_df["uygulama_tarihi"].unique():
                    if pd.isna(dt):
                        continue
                    d = pd.to_datetime(dt).replace(hour=0, minute=0, second=0, microsecond=0)
                    if timezone.is_naive(d):
                        d = timezone.make_aware(d)
                    dates_to_delete.add(d)

                if dates_to_delete:
                    NobetDersProgrami.objects.filter(uygulama_tarihi__in=dates_to_delete).delete()

                # 2. Map'leri hazırla
                personel_map = {p.adi_soyadi: p for p in NobetPersonel.objects.all()}
                sinif_sube_map = {(ss.sinif, ss.sube): ss for ss in SinifSube.objects.all()}

                objs_to_create = []
                for _, row in program_df.iterrows():
                    try:
                        ogretmen_adi = str(row["ders_ogretmeni"]).strip()
                        ogretmen = personel_map.get(ogretmen_adi)

                        if not ogretmen:
                            nobet_ogretmen, created = _get_or_create_eksik_personel(ogretmen_adi)
                            ogretmen = nobet_ogretmen.personel
                            personel_map[ogretmen_adi] = ogretmen
                            if created:
                                status["otomatik_eklenen"] += 1
                                status["otomatik_eklenen_isimler"].append(ogretmen_adi)

                        uygulama_tarihi = pd.to_datetime(row["uygulama_tarihi"], errors="coerce")
                        if pd.isna(uygulama_tarihi):
                            uygulama_tarihi = timezone.now().replace(
                                hour=0, minute=0, second=0, microsecond=0
                            )
                        else:
                            uygulama_tarihi = uygulama_tarihi.replace(
                                hour=0, minute=0, second=0, microsecond=0
                            )
                        if timezone.is_naive(uygulama_tarihi):
                            uygulama_tarihi = timezone.make_aware(uygulama_tarihi)

                        sinif_sube = sinif_sube_map.get((int(row["sinif"]), str(row["sube"])))
                        objs_to_create.append(
                            NobetDersProgrami(
                                ogretmen=ogretmen,
                                gun=row["gun"],
                                ders_saati=int(row["ders_saati"]),
                                uygulama_tarihi=uygulama_tarihi,
                                ders_adi=row["ders_adi"],
                                sinif_sube=sinif_sube,
                                giris_saat=self.parse_time(row["giris_saat"]),
                                cikis_saat=self.parse_time(row["cikis_saat"]),
                                ders_saati_adi=row.get(
                                    "ders_saati_adi", f"{row['ders_saati']}. Ders"
                                ),
                            )
                        )
                    except Exception as row_err:
                        print(f"⚠️ Satır hatası ({row.get('ders_ogretmeni', '???')}): {row_err}")
                        status["errors"] += 1

                if objs_to_create:
                    NobetDersProgrami.objects.bulk_create(objs_to_create)
                    status["inserted"] = len(objs_to_create)

            status["message"] = (
                f"Ders programı: {status['inserted']} kayıt eklendi"
                + (f", {status['otomatik_eklenen']} yeni personel otomatik oluşturuldu" if status["otomatik_eklenen"] else "")
                + (f", {status['errors']} satır hatalı" if status["errors"] else "")
                + "."
            )

        except Exception as e:
            status.update(
                {
                    "status": "error",
                    "message": f"İşlem başarısız, değişiklikler geri alındı: {str(e)}",
                    "inserted": 0,
                }
            )

        return status


class IstatistikService:
    def hesapla_ve_kaydet(self) -> int:
        """
        Tüm öğretmenlerin nöbet istatistiklerini (NobetGecmisi ve NobetAtanamayan)
        hesaplar ve NobetIstatistik tablosuna kaydeder.
        """
        ogretmenler = NobetOgretmen.objects.all()
        updated_count = 0

        for ogretmen in ogretmenler:
            # 1. Geçmiş görevler (Atanan nöbetler)
            gecmis = NobetGecmisi.objects.filter(ogretmen=ogretmen)
            toplam_nobet = gecmis.count()

            son_gorev = gecmis.order_by("-tarih").first()
            son_nobet_tarihi = son_gorev.tarih if son_gorev else None
            son_nobet_yeri = son_gorev.sinif if son_gorev else None

            # 2. Atanamayan (Öğretmenin devamsız olduğu ve dersinin boş geçtiği durumlar)
            # NobetAtanamayan modeli 'ogretmen' alanını devamsız öğretmene bağlar.
            atanmayan_nobet = NobetAtanamayan.objects.filter(ogretmen=ogretmen).count()

            # 3. Hafta sayısı hesaplama (Görev alınan benzersiz hafta sayısı)
            if toplam_nobet > 0:
                weeks = set()
                for g in gecmis:
                    # Yıl ve hafta numarası (Örn: 2024-42)
                    weeks.add(g.tarih.strftime("%Y-%W"))
                hafta_sayisi = len(weeks)
            else:
                hafta_sayisi = 0

            # 4. Haftalık ortalama
            divisor = hafta_sayisi if hafta_sayisi > 0 else 1
            haftalik_ortalama = toplam_nobet / divisor

            # 5. Ağırlıklı Puan (Şimdilik toplam nöbet sayısı, ileride katsayı eklenebilir)
            agirlikli_puan = float(toplam_nobet)

            NobetIstatistik.objects.update_or_create(
                ogretmen=ogretmen,
                defaults={
                    "toplam_nobet": toplam_nobet,
                    "atanmayan_nobet": atanmayan_nobet,
                    "haftalik_ortalama": haftalik_ortalama,
                    "hafta_sayisi": hafta_sayisi,
                    "son_nobet_tarihi": son_nobet_tarihi,
                    "son_nobet_yeri": son_nobet_yeri,
                    "agirlikli_puan": agirlikli_puan,
                },
            )
            updated_count += 1

        return updated_count
