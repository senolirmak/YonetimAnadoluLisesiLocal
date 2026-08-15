from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Sum, Value
from django.db.models.functions import Coalesce
from .models import Alan, AlanDers, OrtakDersHavuzu, SecmeliDers, SecmeliDersGrubu, SecmeliDersHavuzu, SinifSeviyeToplamSaat


class SinifSeviyeToplamSaatForm(forms.ModelForm):
    class Meta:
        model = SinifSeviyeToplamSaat
        fields = ["haftalik_toplam_saat"]
        widgets = {
            "haftalik_toplam_saat": forms.NumberInput(attrs={"min": 1, "max": 99, "style": "width:70px;text-align:center;"}),
        }
        labels = {
            "haftalik_toplam_saat": "Toplam Saat",
        }

    def clean_haftalik_toplam_saat(self):
        deger = self.cleaned_data.get("haftalik_toplam_saat")
        if deger is None or deger < 1:
            raise ValidationError("Toplam saat en az 1 olmalıdır.")
        return deger


class SecmeliDersGrubuForm(forms.ModelForm):
    class Meta:
        model = SecmeliDersGrubu
        fields = ["sinif_seviyesi", "adi", "zorunlu_grup", "sira"]
        widgets = {
            "sinif_seviyesi": forms.Select(),
            "adi": forms.TextInput(attrs={"placeholder": "Örn: Akademik Çalışmalar"}),
            "sira": forms.NumberInput(attrs={"min": 0}),
        }
        labels = {
            "sinif_seviyesi": "Sınıf Seviyesi",
            "adi": "Grup Adı",
            "zorunlu_grup": "Zorunlu Grup",
            "sira": "Sıra",
        }


class SecmeliDersForm(forms.ModelForm):
    class Meta:
        model = SecmeliDers
        fields = ["ders_adi", "saat_secenekleri", "sira", "aktif", "branslar"]
        widgets = {
            "ders_adi": forms.TextInput(attrs={"placeholder": "Örn: Web Tasarımı ve Kodlama"}),
            "saat_secenekleri": forms.TextInput(attrs={"placeholder": "Örn: 4  veya  2,4"}),
            "sira": forms.NumberInput(attrs={"min": 0}),
            "branslar": forms.SelectMultiple(attrs={"size": 6}),
        }
        labels = {
            "ders_adi": "Ders Adı",
            "saat_secenekleri": "Saat Seçenekleri",
            "sira": "Sıra",
            "aktif": "Aktif",
            "branslar": "Branş(lar)",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["branslar"].required = False

    def clean_saat_secenekleri(self):
        deger = self.cleaned_data.get("saat_secenekleri", "").strip()
        parcalar = [p.strip() for p in deger.split(",") if p.strip()]
        if not parcalar:
            raise ValidationError("En az bir saat değeri giriniz.")
        for p in parcalar:
            if not p.isdigit() or int(p) < 1:
                raise ValidationError(
                    "Saat seçenekleri virgülle ayrılmış pozitif tam sayılar olmalıdır. "
                    "Örn: '4' veya '2,4'"
                )
        return ",".join(parcalar)


class OrtakDersHavuzuForm(forms.ModelForm):
    class Meta:
        model = OrtakDersHavuzu
        fields = ["ders_adi", "derssaati", "sira", "aktif", "branslar"]
        widgets = {
            "ders_adi": forms.TextInput(attrs={"placeholder": "Örn: Türk Dili ve Edebiyatı"}),
            "derssaati": forms.TextInput(attrs={"placeholder": "Örn: 4  veya  2,4"}),
            "sira": forms.NumberInput(attrs={"min": 0}),
            "branslar": forms.SelectMultiple(attrs={"size": 6}),
        }
        labels = {
            "ders_adi": "Ders Adı",
            "derssaati": "Ders Saati",
            "sira": "Sıra",
            "aktif": "Aktif",
            "branslar": "Branş(lar)",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["branslar"].required = False

    def clean_derssaati(self):
        deger = self.cleaned_data.get("derssaati", "").strip()
        if not deger:
            return deger
        parcalar = [p.strip() for p in deger.split(",") if p.strip()]
        for p in parcalar:
            if not p.isdigit() or int(p) < 1:
                raise ValidationError(
                    "Ders saati virgülle ayrılmış pozitif tam sayılar olmalıdır. Örn: '4' veya '2,4'"
                )
        return ",".join(parcalar)


class SecmeliDersHavuzuForm(forms.ModelForm):
    class Meta:
        model = SecmeliDersHavuzu
        fields = ["ders_adi", "derssaati", "secimsayisi", "sira", "aktif", "branslar"]
        widgets = {
            "ders_adi": forms.TextInput(attrs={"placeholder": "Örn: Web Tasarımı ve Kodlama"}),
            "derssaati": forms.TextInput(attrs={"placeholder": "Örn: 4  veya  2,4"}),
            "secimsayisi": forms.NumberInput(attrs={"min": 1}),
            "sira": forms.NumberInput(attrs={"min": 0}),
            "branslar": forms.SelectMultiple(attrs={"size": 6}),
        }
        labels = {
            "ders_adi": "Ders Adı",
            "derssaati": "Ders Saati",
            "secimsayisi": "Seçim Sayısı",
            "sira": "Sıra",
            "aktif": "Aktif",
            "branslar": "Branş(lar)",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["branslar"].required = False

    def clean_derssaati(self):
        deger = self.cleaned_data.get("derssaati", "").strip()
        parcalar = [p.strip() for p in deger.split(",") if p.strip()]
        if not parcalar:
            raise ValidationError("En az bir saat değeri giriniz.")
        for p in parcalar:
            if not p.isdigit() or int(p) < 1:
                raise ValidationError(
                    "Ders saati virgülle ayrılmış pozitif tam sayılar olmalıdır. Örn: '4' veya '2,4'"
                )
        return ",".join(parcalar)


class AlanForm(forms.ModelForm):
    class Meta:
        model = Alan
        fields = ["sinif_seviyesi", "adi"]

    grup_field_map = None

    def __init__(self, *args, egitim_yili=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._egitim_yili = egitim_yili

        self.fields["sinif_seviyesi"].widget = forms.Select(
            choices=[(9, "9. Sınıf"), (10, "10. Sınıf"), (11, "11. Sınıf"), (12, "12. Sınıf")]
        )
        self.fields["sinif_seviyesi"].label = "Sınıf Seviyesi"
        self.fields["adi"].label = "Alan Adı"
        self.fields["adi"].widget.attrs.update({"placeholder": "Örn: MF, TM, DİL"})

        # Mevcut kayıtlı dersler ve saatleri
        mevcut = {}
        if self.instance.pk:
            for ad in AlanDers.objects.filter(alan=self.instance).select_related("ders"):
                mevcut[ad.ders_id] = ad.secilen_saat

        grup_qs = SecmeliDersGrubu.objects.filter(sinif_seviyesi__in=[9, 10, 11, 12])
        if self._egitim_yili:
            grup_qs = grup_qs.filter(egitim_yili=self._egitim_yili)
        gruplar = grup_qs.prefetch_related("dersler").order_by("sinif_seviyesi", "sira")

        # grup_id → (grup_obj, [(fname, fname_saat_or_None, ders_obj), ...])
        self.grup_field_map = {}

        for grup in gruplar:
            field_items = []
            for ders in grup.dersler.filter(aktif=True).order_by("sira"):
                fname = f"ders_{ders.pk}"
                saat_lst = ders.saat_listesi

                self.fields[fname] = forms.BooleanField(required=False, label=ders.ders_adi)
                if ders.pk in mevcut:
                    self.initial[fname] = True

                if len(saat_lst) == 1:
                    field_items.append((fname, None, ders))
                else:
                    fname_saat = f"ders_{ders.pk}_saat"
                    choices = [(str(s), f"{s} saat") for s in saat_lst]
                    self.fields[fname_saat] = forms.ChoiceField(
                        required=False,
                        choices=choices,
                        label=f"{ders.ders_adi} — Saat",
                        widget=forms.RadioSelect,
                    )
                    self.initial[fname_saat] = str(mevcut.get(ders.pk, saat_lst[0]))
                    field_items.append((fname, fname_saat, ders))

            if field_items:
                self.grup_field_map[grup.pk] = (grup, field_items)

    @property
    def sinif_bloklar(self):
        """
        Template için:
        [(sinif_seviyesi, [(grup, [(fname, fname_saat_or_None, ders, chk_bf, saat_bf_or_None)])]), ...]
        """
        result = {}
        for grup, field_items in self.grup_field_map.values():
            sv = grup.sinif_seviyesi
            if sv not in result:
                result[sv] = []
            entries = []
            for fname, fname_saat, ders in field_items:
                chk_bf = self[fname]
                saat_bf = self[fname_saat] if fname_saat else None
                entries.append((fname, fname_saat, ders, chk_bf, saat_bf))
            result[sv].append((grup, entries))
        return list(result.items())

    def get_secimler(self):
        """Seçilen (ders, saat) çiftlerini döndürür."""
        result = []
        for grup, field_items in self.grup_field_map.values():
            for fname, fname_saat, ders in field_items:
                if not self.cleaned_data.get(fname):
                    continue
                if fname_saat is None:
                    result.append((ders, ders.sabit_saat))
                else:
                    try:
                        saat = int(self.cleaned_data.get(fname_saat) or 0)
                        if saat in ders.saat_listesi:
                            result.append((ders, saat))
                    except (ValueError, TypeError):
                        pass
        return result

    def clean(self):
        cleaned = super().clean()
        for grup, field_items in self.grup_field_map.values():
            for fname, fname_saat, ders in field_items:
                if fname_saat is None:
                    continue
                if cleaned.get(fname):
                    try:
                        saat = int(cleaned.get(fname_saat) or 0)
                        if saat not in ders.saat_listesi:
                            self.add_error(fname_saat, "Lütfen geçerli bir saat seçiniz.")
                    except (ValueError, TypeError):
                        self.add_error(fname_saat, "Lütfen ders saatini seçiniz.")
        return cleaned

    def save(self, commit=True):
        alan = super().save(commit=commit)
        if commit:
            AlanDers.objects.filter(alan=alan).delete()
            AlanDers.objects.bulk_create([
                AlanDers(alan=alan, ders=ders, secilen_saat=saat)
                for ders, saat in self.get_secimler()
            ])
        return alan
