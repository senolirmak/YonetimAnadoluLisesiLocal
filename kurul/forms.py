from django import forms

from kurul.models import KurulUyesi, KurulYapiKalemi
from ogrenci.models import Ogrenci
from okul.models import Personel


class UyeEkleForm(forms.Form):
    UYE_TURU_CHOICES = (
        ("personel", "Personel"),
        ("ogrenci", "Öğrenci"),
        ("dis", "Dış üye (veli, OAB temsilcisi vb.)"),
    )
    uye_turu = forms.ChoiceField(choices=UYE_TURU_CHOICES, initial="personel", label="Üye Türü")
    personel = forms.ModelChoiceField(
        queryset=Personel.objects.none(), required=False, label="Personel"
    )
    ogrenci = forms.ModelChoiceField(queryset=Ogrenci.objects.none(), required=False, label="Öğrenci")
    dis_uye = forms.CharField(
        max_length=150, required=False, label="Dış üye unvanı",
        help_text="Örn. 'Okul-Aile Birliği temsilcisi (veli)'. Ad-soyad yazmayın.",
    )
    gorev = forms.ChoiceField(choices=KurulUyesi.GOREV_CHOICES, initial=KurulUyesi.GOREV_UYE, label="Görevi")
    asil = forms.BooleanField(required=False, initial=True, label="Asil üye")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["personel"].queryset = Personel.objects.gorevde().order_by("adi_soyadi")
        # Yeni görev ataması: yalnızca okulda kayıtlı (aktif) öğrenciler (bkz. CLAUDE.md)
        self.fields["ogrenci"].queryset = Ogrenci.objects.filter(aktif=True).order_by("sinif", "sube", "okulno")
        self.fields["ogrenci"].label_from_instance = lambda o: f"{o.sinifsube} — {o.okulno} {o.adi} {o.soyadi}"

    def clean(self):
        veri = super().clean()
        tur = veri.get("uye_turu")
        if tur == "personel" and not veri.get("personel"):
            self.add_error("personel", "Personel seçin.")
        elif tur == "ogrenci" and not veri.get("ogrenci"):
            self.add_error("ogrenci", "Öğrenci seçin.")
        elif tur == "dis" and not (veri.get("dis_uye") or "").strip():
            self.add_error("dis_uye", "Dış üyenin unvanını/temsil ettiği yeri yazın.")
        return veri

    def uye_alanlari(self):
        v = self.cleaned_data
        return {
            "personel": v["personel"] if v["uye_turu"] == "personel" else None,
            "ogrenci": v["ogrenci"] if v["uye_turu"] == "ogrenci" else None,
            "dis_uye": v["dis_uye"] if v["uye_turu"] == "dis" else "",
            "gorev": v["gorev"],
            "asil": v["asil"],
        }


class KurulYapiFormu(forms.Form):
    """Kurulun yapısındaki (iskelet) her görev yeri için asil ve yedek seçim alanları.

    Otomatik kalemler (ör. öğretmenler kurulunun üyeleri) formda yer almaz."""

    def __init__(self, kurul, *args, **kwargs):
        from kurul.services.uyelik import kalem_uyeleri, ogrenci_secenekleri, personel_secenekleri

        super().__init__(*args, **kwargs)
        self.kurul = kurul
        self.kalemler = []
        ogrenciler = None
        for kalem in kurul.tur.yapi.filter(otomatik=False):
            mevcut = kalem_uyeleri(kurul, kalem)
            asiller = [u for u in mevcut if u.asil]
            yedekler = [u for u in mevcut if not u.asil]
            satir = {"kalem": kalem, "asil": [], "yedek": []}
            for tur_adi, sayi, liste in (("asil", kalem.asil_sayisi, asiller), ("yedek", kalem.yedek_sayisi, yedekler)):
                for i in range(sayi):
                    ad = f"k{kalem.pk}_{tur_adi}_{i}"
                    uye = liste[i] if i < len(liste) else None
                    if kalem.uye_turu == KurulYapiKalemi.UYE_PERSONEL:
                        alan = forms.ModelChoiceField(queryset=personel_secenekleri(kalem), required=False,
                                                      empty_label="— seçilmedi —")
                        alan.initial = uye.personel_id if uye else None
                    elif kalem.uye_turu == KurulYapiKalemi.UYE_OGRENCI:
                        if ogrenciler is None:
                            ogrenciler = ogrenci_secenekleri()
                        alan = forms.ModelChoiceField(queryset=ogrenciler, required=False,
                                                      empty_label="— seçilmedi —")
                        alan.label_from_instance = lambda o: f"{o.sinifsube} — {o.okulno} {o.adi} {o.soyadi}"
                        alan.initial = uye.ogrenci_id if uye else None
                    else:
                        alan = forms.CharField(max_length=150, required=False,
                                               widget=forms.TextInput(attrs={"placeholder": kalem.unvan}))
                        alan.initial = uye.dis_uye if uye else ""
                    alan.label = f"{kalem.unvan} ({'asil' if tur_adi == 'asil' else 'yedek'} {i + 1})"
                    self.fields[ad] = alan
                    satir[tur_adi].append(ad)
            self.kalemler.append(satir)

    def satirlar(self):
        """Şablon için: her kalem ve alanlarının BoundField'ları."""
        return [
            {"kalem": s["kalem"], "asil": [self[a] for a in s["asil"]], "yedek": [self[a] for a in s["yedek"]]}
            for s in self.kalemler
        ]

    def secimler(self):
        v = self.cleaned_data
        return {
            s["kalem"]: {"asil": [v.get(a) for a in s["asil"]], "yedek": [v.get(a) for a in s["yedek"]]}
            for s in self.kalemler
        }
