# -*- coding: utf-8 -*-
from django import forms
from okul.models import Brans, DersHavuzu, DersSaatleri, Personel, SinifSube, SinifSubeYil


class BransForm(forms.ModelForm):
    class Meta:
        model = Brans
        fields = ["ad"]
        labels = {"ad": "Branş Adı"}


class DersHavuzuForm(forms.ModelForm):
    class Meta:
        model = DersHavuzu
        fields = ["cift_oturum", "sinav_yapilmayacak"]
        widgets = {
            "cift_oturum": forms.Select(attrs={"class": "form-select form-select-sm"}),
            "sinav_yapilmayacak": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class DersHavuzuFullForm(forms.ModelForm):
    """okul/yonetim CRUD'unda ekle/düzenle için — DersHavuzuForm'un tüm alanlı hâli."""

    class Meta:
        model = DersHavuzu
        fields = ["ders_adi", "cift_oturum", "sinav_yapilmayacak"]
        labels = {
            "ders_adi": "Ders Adı",
            "cift_oturum": "Sınav Türü",
            "sinav_yapilmayacak": "Sınav Yapılmayacak",
        }


class SinifSubeForm(forms.ModelForm):
    class Meta:
        model = SinifSube
        fields = ["sinif", "sube"]
        labels = {"sinif": "Sınıf", "sube": "Şube"}


class SinifSubeYilForm(forms.ModelForm):
    """Bir SinifSube'un belirli bir eğitim-öğretim yılındaki açık/kapalı durumunu
    ekler/günceller — bkz. `okul.crud.sinif_sube_yil_ata`."""

    class Meta:
        model = SinifSubeYil
        fields = ["egitim_yili", "acik"]
        labels = {"egitim_yili": "Eğitim-Öğretim Yılı", "acik": "Açık"}


class DersSaatleriForm(forms.ModelForm):
    class Meta:
        model = DersSaatleri
        fields = ["derssaati_no", "derssaati_baslangic", "derssaati_bitis"]
        labels = {
            "derssaati_no": "Ders No",
            "derssaati_baslangic": "Başlangıç Saati",
            "derssaati_bitis": "Bitiş Saati",
        }
        widgets = {
            "derssaati_baslangic": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "derssaati_bitis": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
        }


class PersonelForm(forms.ModelForm):
    class Meta:
        model = Personel
        fields = [
            "kimlikno", "adi_soyadi", "brans", "mezunokul", "cinsiyet",
            "nobeti_var", "gorev_tipi", "durum", "sabit_nobet", "user",
        ]
        labels = {
            "kimlikno": "TC Kimlik No",
            "adi_soyadi": "Adı Soyadı",
            "brans": "Branş",
            "mezunokul": "Mezun Olduğu Yükseköğretim Programı/Fakülte",
            "cinsiyet": "Cinsiyet",
            "nobeti_var": "Nöbeti Var",
            "gorev_tipi": "Görevi",
            "durum": "Durum",
            "sabit_nobet": "Sabit Nöbet",
            "user": "Bağlı Kullanıcı Hesabı",
        }
