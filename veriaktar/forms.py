from django import forms
from django.utils import timezone


class BaseImportForm(forms.Form):
    uygulama_tarihi = forms.DateField(
        label="Uygulama Tarihi",
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={"type": "date", "class": "vDateField"}, format="%Y-%m-%d"),
    )
    aciklama = forms.CharField(
        label="Açıklama",
        required=False,
        widget=forms.TextInput(attrs={"class": "vTextField", "placeholder": "Açıklama"}),
    )


class PersonelImportForm(BaseImportForm):
    dosya = forms.FileField(label="Personel Excel Dosyası (personel.xlsx)")


class NobetImportForm(BaseImportForm):
    dosya = forms.FileField(label="Nöbet Excel Dosyası (..ÖğretmenNöbet.xlsx)")


class DersProgramiImportForm(forms.Form):
    uygulama_tarihi = forms.DateField(
        label="Uygulama Tarihi",
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={"type": "date", "class": "vDateField"}, format="%Y-%m-%d"),
    )
    dosya = forms.FileField(label="Ders Programı Excel Dosyası (OOK...XLS)")


class OkulBilgiForm(forms.Form):
    okul_kodu = forms.CharField(
        label="Okul Kodu",
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={"class": "vTextField", "placeholder": "Örn: 123456"}),
    )
    okul_adi = forms.CharField(
        label="Okul Adı",
        max_length=200,
        required=False,
        widget=forms.TextInput(
            attrs={"class": "vTextField", "placeholder": "Örn: Atatürk Anadolu Lisesi"}
        ),
    )
    okul_muduru = forms.CharField(
        label="Okul Müdürü",
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={"class": "vTextField", "placeholder": "Örn: Ahmet Yılmaz"}),
    )


class OgrenciImportForm(forms.Form):
    dosya = forms.FileField(label="Öğrenci Listesi Excel Dosyası (OOG01001R020_...XLS)")


class SinifSubeImportForm(forms.Form):
    sinif_9 = forms.CharField(
        label="9. Sınıf Şubeleri",
        widget=forms.TextInput(attrs={"class": "vTextField", "style": "width: 100%;"}),
        required=False,
    )
    sinif_10 = forms.CharField(
        label="10. Sınıf Şubeleri",
        widget=forms.TextInput(attrs={"class": "vTextField", "style": "width: 100%;"}),
        required=False,
    )
    sinif_11 = forms.CharField(
        label="11. Sınıf Şubeleri",
        widget=forms.TextInput(attrs={"class": "vTextField", "style": "width: 100%;"}),
        required=False,
    )
    sinif_12 = forms.CharField(
        label="12. Sınıf Şubeleri",
        widget=forms.TextInput(attrs={"class": "vTextField", "style": "width: 100%;"}),
        required=False,
    )
