from django import forms

from okul.models import EgitimOgretimYili, DersSaatleri
from sorumluluk.models import (
    DONEM_TURU_CHOICES,
    SorumluDers,
    SorumluDersHavuzu,
    SorumluOgrenci,
    SorumluSinav,
)

_INPUT  = "form-control"
_SELECT = "form-control"


class XlsAktarForm(forms.Form):
    dosya = forms.FileField(
        label="e-Okul Excel Dosyası (OOK12001R010)",
        widget=forms.ClearableFileInput(attrs={"class": _INPUT, "accept": ".xls,.xlsx"})
    )


class SorumluSinavForm(forms.ModelForm):
    class Meta:
        model = SorumluSinav
        fields = ["sinav_adi", "aciklama", "egitim_yili", "donem_turu"]
        widgets = {
            "sinav_adi":   forms.TextInput(attrs={"class": _INPUT}),
            "aciklama":    forms.TextInput(attrs={"class": _INPUT}),
            "egitim_yili": forms.Select(attrs={"class": _SELECT}),
            "donem_turu":  forms.Select(attrs={"class": _SELECT}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["egitim_yili"].queryset = EgitimOgretimYili.objects.all()
        self.fields["egitim_yili"].empty_label = "— Yıl seçin —"
        self.fields["egitim_yili"].required = False


class SorumluOgrenciForm(forms.ModelForm):
    class Meta:
        model = SorumluOgrenci
        fields = ["okulno", "adi_soyadi", "sinif", "sube", "aktif"]
        widgets = {
            "okulno":     forms.TextInput(attrs={"class": _INPUT}),
            "adi_soyadi": forms.TextInput(attrs={"class": _INPUT}),
            "sinif":      forms.NumberInput(attrs={"class": _INPUT}),
            "sube":       forms.TextInput(attrs={"class": _INPUT, "maxlength": "4"}),
            "aktif":      forms.CheckboxInput(),
        }


class SorumluDersForm(forms.ModelForm):
    class Meta:
        model = SorumluDers
        fields = ["havuz_dersi"]
        widgets = {
            "havuz_dersi": forms.Select(attrs={"class": _SELECT}),
        }

    def __init__(self, *args, **kwargs):
        ogr = kwargs.pop("ogr", None)
        super().__init__(*args, **kwargs)
        if ogr:
            self.fields["havuz_dersi"].queryset = SorumluDersHavuzu.objects.filter(sinav=ogr.sinav)
            self.fields["havuz_dersi"].empty_label = "— Ders Seçin —"


class TakvimAyarForm(forms.Form):
    haric_tutulacak_ogrenciler = forms.ModelMultipleChoiceField(
        queryset=None,
        required=False,
        label="Sınavdan Çıkarılacak Öğrenciler",
        widget=forms.SelectMultiple(attrs={"class": _SELECT, "size": "6"}),
        help_text="Sınava girmeyecek (muaf vb.) öğrencileri seçin. Seçilen öğrenciler takvim ve oturma planına dahil edilmez."
    )
    cift_oturumlu_dersler = forms.ModelMultipleChoiceField(
        queryset=None,
        required=False,
        label="İki Oturumlu (Çift) Dersler",
        widget=forms.SelectMultiple(attrs={"class": _SELECT, "size": "6"}),
        help_text="Uygulama ve Yazılı gibi 2 ayrı oturumda yapılacak dersleri seçin (CTRL/CMD ile çoklu seçim yapabilirsiniz)."
    )
    baslangic_tarihi = forms.DateField(
        label="Sınav Başlangıç Tarihi",
        widget=forms.DateInput(attrs={"class": _INPUT, "type": "date"}),
        help_text="Takvimin başlayacağı ilk günü seçin."
    )
    oturum_saatleri = forms.CharField(
        label="Oturum Saatleri",
        initial="10:00-10:40, 11:00-11:40, 13:30-14:10, 14:30-15:10",
        widget=forms.TextInput(attrs={"class": _INPUT}),
        help_text="Oturum saatleri okuldaki 2., 3., 4. ve 5. ders saatlerinden otomatik alınmıştır. İhtiyaca göre virgül koyarak değiştirebilirsiniz."
    )
    max_gunluk_sinav = forms.IntegerField(
        label="Bir Öğrenci Günde En Fazla Kaç Sınava Girebilir?",
        initial=2,
        min_value=1,
        max_value=5,
        widget=forms.NumberInput(attrs={"class": _INPUT})
    )
    slot_max_ders = forms.IntegerField(
        label="Bir Oturumda Maksimum Farklı Ders",
        initial=6,
        min_value=1,
        max_value=20,
        widget=forms.NumberInput(attrs={"class": _INPUT}),
        help_text="Aynı saatte (oturumda) en fazla kaç farklı dersin sınavı yapılabilsin?"
    )
    max_iter = forms.IntegerField(
        label="Maksimum İterasyon",
        initial=500,
        min_value=50,
        max_value=2000,
        widget=forms.NumberInput(attrs={"class": _INPUT}),
        help_text="Takvim optimizasyonunda deneme sayısı. Yüksek değer daha iyi sonuç verebilir, daha yavaş çalışır."
    )
    tatil_gunleri = forms.CharField(
        label="Tatil Günleri (İsteğe Bağlı)",
        required=False,
        widget=forms.TextInput(attrs={"class": _INPUT, "placeholder": "Örn: 23.04.2026, 24.04.2026"}),
        help_text="Araya giren tatil günlerini virgülle ayırarak GG.AA.YYYY formatında yazın."
    )
    exclude_weekends = forms.BooleanField(
        label="Hafta Sonlarını Atla",
        initial=True, required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
        help_text="İşaretliyse Cumartesi ve Pazar günlerine sınav konmaz."
    )

    def __init__(self, *args, **kwargs):
        sinav = kwargs.pop("sinav", None)
        parametreler = kwargs.pop("parametreler", None)
        super().__init__(*args, **kwargs)

        # Okul ders saatlerinden 2.–5. dersleri varsayılan oturum saati yap
        try:
            ds_list = list(DersSaatleri.objects.all().order_by("derssaati_baslangic"))
            if len(ds_list) >= 5:
                secili = ds_list[1:5]
                saat_str_list = []
                for ds in secili:
                    bas = ds.derssaati_baslangic.strftime("%H:%M") if hasattr(ds.derssaati_baslangic, "strftime") else str(ds.derssaati_baslangic)[:5]
                    bit = ds.derssaati_bitis.strftime("%H:%M") if hasattr(ds.derssaati_bitis, "strftime") else str(ds.derssaati_bitis)[:5]
                    saat_str_list.append(f"{bas}-{bit}")
                if saat_str_list:
                    self.fields["oturum_saatleri"].initial = ", ".join(saat_str_list)
        except Exception:
            pass

        if sinav:
            self.fields["cift_oturumlu_dersler"].queryset = SorumluDersHavuzu.objects.filter(sinav=sinav).order_by("ders_adi")
            self.fields["haric_tutulacak_ogrenciler"].queryset = SorumluOgrenci.objects.filter(sinav=sinav).order_by("sinif", "sube", "adi_soyadi")

            # Kaydedilmiş parametrelerden varsayılanları yükle (ortaksinav CONFIG benzeri)
            if parametreler:
                self.fields["baslangic_tarihi"].initial = parametreler.baslangic_tarihi
                self.fields["oturum_saatleri"].initial = ", ".join(parametreler.oturum_saatleri)
                self.fields["max_gunluk_sinav"].initial = parametreler.max_gunluk_sinav
                self.fields["slot_max_ders"].initial = parametreler.slot_max_ders
                self.fields["max_iter"].initial = parametreler.max_iter
                self.fields["tatil_gunleri"].initial = ", ".join(parametreler.tatil_tarihleri)
                self.fields["exclude_weekends"].initial = parametreler.hafta_sonu_haric
                self.fields["cift_oturumlu_dersler"].initial = SorumluDersHavuzu.objects.filter(
                    id__in=parametreler.cift_oturumlu_dersler
                )
                self.fields["haric_tutulacak_ogrenciler"].initial = SorumluOgrenci.objects.filter(
                    sinav=sinav, aktif=False
                )
            else:
                # Varsayılan çift oturumlu dersler (ortaksinav_engine CIFT_OTURUMLU_DERSLER'e paralel)
                varsayilan_cift = [
                    "GÖRSEL SANATLAR/MÜZİK", "SEÇMELİ İKİNCİ YABANCI DİL",
                    "TÜRK DİLİ VE EDEBİYATI", "YABANCI DİL",
                ]
                self.fields["cift_oturumlu_dersler"].initial = SorumluDersHavuzu.objects.filter(
                    sinav=sinav, ders_adi__in=varsayilan_cift
                )
                self.fields["haric_tutulacak_ogrenciler"].initial = SorumluOgrenci.objects.filter(
                    sinav=sinav, aktif=False
                )
