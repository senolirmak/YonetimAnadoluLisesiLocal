from django import forms
from django.core.exceptions import ValidationError

from okul.models import EgitimOgretimYili, OkulBilgi, OkulDonem


class OkulBilgiAyarForm(forms.ModelForm):
    class Meta:
        model = OkulBilgi
        fields = ["okul_kodu", "okul_adi", "okul_muduru", "okul_donem", "okul_egtyil"]
        labels = {
            "okul_kodu": "Okul Kodu",
            "okul_adi": "Okul Adı",
            "okul_muduru": "Okul Müdürü",
            "okul_donem": "Aktif Dönem",
            "okul_egtyil": "Aktif Eğitim-Öğretim Yılı",
        }


class EgitimOgretimYiliForm(forms.ModelForm):
    class Meta:
        model = EgitimOgretimYili
        fields = ["egitim_yili", "egitim_baslangic", "egitim_bitis"]
        labels = {
            "egitim_yili": "Eğitim-Öğretim Yılı",
            "egitim_baslangic": "Başlangıç Tarihi",
            "egitim_bitis": "Bitiş Tarihi",
        }
        widgets = {
            "egitim_baslangic": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "egitim_bitis": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }

    def clean(self):
        cleaned = super().clean()
        baslangic = cleaned.get("egitim_baslangic")
        bitis = cleaned.get("egitim_bitis")

        if baslangic and bitis:
            if bitis <= baslangic:
                raise ValidationError("Bitiş tarihi başlangıç tarihinden sonra olmalıdır.")

            qs = EgitimOgretimYili.objects.filter(
                egitim_baslangic__lt=bitis,
                egitim_bitis__gt=baslangic,
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                cakisan = qs.first()
                raise ValidationError(
                    f"Bu tarih aralığı mevcut bir yılla çakışıyor: {cakisan.egitim_yili} "
                    f"({cakisan.egitim_baslangic} – {cakisan.egitim_bitis})"
                )
        return cleaned


class OkulDonemForm(forms.ModelForm):
    class Meta:
        model = OkulDonem
        fields = ["egitim_yili", "donem", "baslangic", "bitis"]
        labels = {
            "egitim_yili": "Eğitim-Öğretim Yılı",
            "donem": "Dönem",
            "baslangic": "Başlangıç Tarihi",
            "bitis": "Bitiş Tarihi",
        }
        widgets = {
            "baslangic": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "bitis": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }

    def clean(self):
        cleaned = super().clean()
        egitim_yili = cleaned.get("egitim_yili")
        baslangic = cleaned.get("baslangic")
        bitis = cleaned.get("bitis")
        donem = cleaned.get("donem")

        if baslangic and bitis:
            if bitis <= baslangic:
                raise ValidationError("Dönem bitiş tarihi başlangıç tarihinden sonra olmalıdır.")

            if egitim_yili:
                if baslangic < egitim_yili.egitim_baslangic or bitis > egitim_yili.egitim_bitis:
                    raise ValidationError(
                        f"Dönem tarihleri eğitim-öğretim yılı aralığının dışında: "
                        f"{egitim_yili.egitim_baslangic} – {egitim_yili.egitim_bitis}"
                    )

                qs = OkulDonem.objects.filter(egitim_yili=egitim_yili).exclude(donem=donem)
                if self.instance.pk:
                    qs = qs.exclude(pk=self.instance.pk)
                for diger in qs:
                    if baslangic < diger.bitis and bitis > diger.baslangic:
                        raise ValidationError(
                            f"Bu dönem tarihleri aynı yıl içindeki diğer dönemle çakışıyor: "
                            f"{dict(OkulDonem.DONEM_CHOICES).get(diger.donem)} "
                            f"({diger.baslangic} – {diger.bitis})"
                        )
        return cleaned
