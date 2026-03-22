from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password

from nobet.models import NobetPersonel


class KayitForm(forms.Form):
    tckimlikno = forms.CharField(
        label="TC Kimlik No",
        max_length=11,
        min_length=11,
        widget=forms.TextInput(
            attrs={"maxlength": "11", "inputmode": "numeric", "autocomplete": "off"}
        ),
    )
    username = forms.CharField(label="Kullanıcı Adı", max_length=150)
    password1 = forms.CharField(label="Şifre", widget=forms.PasswordInput())
    password2 = forms.CharField(label="Şifre (Tekrar)", widget=forms.PasswordInput())

    def clean_tckimlikno(self):
        tc = self.cleaned_data["tckimlikno"]
        if not tc.isdigit():
            raise forms.ValidationError("TC kimlik no yalnızca rakamlardan oluşmalıdır.")
        try:
            personel = NobetPersonel.objects.get(kimlikno=tc)
        except NobetPersonel.DoesNotExist:
            raise forms.ValidationError(
                "Bu TC kimlik no ile kayıtlı personel bulunamadı. Yöneticiniz ile iletişime geçin."
            )
        if personel.user:
            raise forms.ValidationError("Bu TC kimlik no ile zaten bir hesap oluşturulmuş.")
        return tc

    def clean_username(self):
        username = self.cleaned_data["username"]
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("Bu kullanıcı adı zaten kullanılıyor.")
        return username

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("password1")
        p2 = cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Şifreler eşleşmiyor.")
        if p1:
            try:
                validate_password(p1)
            except forms.ValidationError as e:
                self.add_error("password1", e)
        return cleaned


class ProfilDuzenleForm(forms.Form):
    first_name = forms.CharField(
        label="Adı",
        max_length=150,
        widget=forms.TextInput(attrs={"class": "vTextField"}),
    )
    last_name = forms.CharField(
        label="Soyadı",
        max_length=150,
        widget=forms.TextInput(attrs={"class": "vTextField"}),
    )
    email = forms.EmailField(
        label="E-posta",
        required=False,
        widget=forms.EmailInput(attrs={"class": "vTextField"}),
    )


class SifreDegistirForm(forms.Form):
    eski_sifre = forms.CharField(
        label="Mevcut Şifre",
        widget=forms.PasswordInput(attrs={"class": "vTextField"}),
    )
    yeni_sifre1 = forms.CharField(
        label="Yeni Şifre",
        widget=forms.PasswordInput(attrs={"class": "vTextField"}),
    )
    yeni_sifre2 = forms.CharField(
        label="Yeni Şifre (Tekrar)",
        widget=forms.PasswordInput(attrs={"class": "vTextField"}),
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_eski_sifre(self):
        eski = self.cleaned_data.get("eski_sifre")
        if not self.user.check_password(eski):
            raise forms.ValidationError("Mevcut şifre hatalı.")
        return eski

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("yeni_sifre1")
        p2 = cleaned.get("yeni_sifre2")
        if p1 and p2 and p1 != p2:
            self.add_error("yeni_sifre2", "Şifreler eşleşmiyor.")
        if p1:
            try:
                validate_password(p1, user=self.user)
            except forms.ValidationError as e:
                self.add_error("yeni_sifre1", e)
        return cleaned


class OgretmenKullaniciForm(forms.Form):
    username = forms.CharField(
        label="Kullanıcı Adı",
        max_length=150,
        widget=forms.TextInput(attrs={"class": "vTextField"}),
    )
    first_name = forms.CharField(
        label="Adı",
        max_length=150,
        widget=forms.TextInput(attrs={"class": "vTextField"}),
    )
    last_name = forms.CharField(
        label="Soyadı",
        max_length=150,
        widget=forms.TextInput(attrs={"class": "vTextField"}),
    )
    password1 = forms.CharField(
        label="Şifre",
        widget=forms.PasswordInput(attrs={"class": "vTextField"}),
    )
    password2 = forms.CharField(
        label="Şifre (Tekrar)",
        widget=forms.PasswordInput(attrs={"class": "vTextField"}),
    )

    def clean_username(self):
        username = self.cleaned_data["username"]
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("Bu kullanıcı adı zaten kullanılıyor.")
        return username

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("password1")
        p2 = cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Şifreler eşleşmiyor.")
        if p1:
            try:
                validate_password(p1)
            except forms.ValidationError as e:
                self.add_error("password1", e)
        return cleaned


class PersonelDuzenleForm(forms.ModelForm):
    class Meta:
        model = NobetPersonel
        fields = [
            "adi_soyadi",
            "kimlikno",
            "brans",
            "cinsiyet",
            "nobeti_var",
            "gorev_tipi",
            "sabit_nobet",
        ]
        widgets = {
            "adi_soyadi": forms.TextInput(attrs={"class": "vTextField"}),
            "kimlikno": forms.TextInput(
                attrs={"class": "vTextField", "maxlength": "11", "inputmode": "numeric"}
            ),
            "brans": forms.TextInput(attrs={"class": "vTextField"}),
            "gorev_tipi": forms.TextInput(attrs={"class": "vTextField"}),
        }
        labels = {
            "adi_soyadi": "Adı Soyadı",
            "kimlikno": "TC Kimlik No",
            "brans": "Branş",
            "cinsiyet": "Cinsiyet",
            "nobeti_var": "Nöbeti Var",
            "gorev_tipi": "Görev Tipi",
            "sabit_nobet": "Sabit Nöbet",
        }
