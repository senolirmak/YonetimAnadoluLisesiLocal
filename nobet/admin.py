from collections import defaultdict

from django import forms
from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.urls import path

from dersprogrami.models import DersProgrami
from personeldevamsizlik.models import Devamsizlik
from veriaktar.forms import (
    DersProgramiImportForm,
    NobetImportForm,
    OkulBilgiForm,
    PersonelImportForm,
    SinifSubeImportForm,
)
from veriaktar.services.default_path_service import DefaultPath
from veriaktar.services.ders_programi_import_service import DersProgramiIsleyici
from veriaktar.services.nobet_import_service import NobetIsleyici
from veriaktar.services.personel_import_service import PersonelIsleyici
from veriaktar.services.sinifsube_import_service import sinif_sube_kaydet

from .models import (
    EgitimOgretimYili,
    NobetGorevi,
    NobetIstatistik,
    NobetOgretmen,
    NobetPersonel,
    OkulBilgi,
    OkulDonem,
    SinifSube,
    VeriYukleme,
)


# ──────────────────────────────────────────────
# EgitimOgretimYili Form — çakışma kontrolü
# ──────────────────────────────────────────────

class EgitimOgretimYiliForm(forms.ModelForm):
    class Meta:
        model = EgitimOgretimYili
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()
        baslangic = cleaned.get("egitim_baslangic")
        bitis = cleaned.get("egitim_bitis")

        if baslangic and bitis:
            if bitis <= baslangic:
                raise ValidationError("Bitiş tarihi başlangıç tarihinden sonra olmalıdır.")

            # Çakışan yıl var mı?
            qs = EgitimOgretimYili.objects.filter(
                egitim_baslangic__lt=bitis,
                egitim_bitis__gt=baslangic,
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                cakisan = qs.first()
                raise ValidationError(
                    f"Bu tarih aralığı mevcut bir eğitim-öğretim yılıyla çakışıyor: {cakisan.egitim_yili} "
                    f"({cakisan.egitim_baslangic} – {cakisan.egitim_bitis})"
                )
        return cleaned


# ──────────────────────────────────────────────
# OkulDonem Form — yıl aralığı ve çakışma kontrolü
# ──────────────────────────────────────────────

class OkulDonemForm(forms.ModelForm):
    class Meta:
        model = OkulDonem
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()
        egitim_yili = cleaned.get("egitim_yili")
        baslangic = cleaned.get("baslangic")
        bitis = cleaned.get("bitis")

        if baslangic and bitis:
            if bitis <= baslangic:
                raise ValidationError("Dönem bitiş tarihi başlangıç tarihinden sonra olmalıdır.")

            # Eğitim yılı aralığı dışında mı?
            if egitim_yili:
                if baslangic < egitim_yili.egitim_baslangic or bitis > egitim_yili.egitim_bitis:
                    raise ValidationError(
                        f"Dönem tarihleri eğitim-öğretim yılı aralığının dışında: "
                        f"{egitim_yili.egitim_baslangic} – {egitim_yili.egitim_bitis}"
                    )

            # Aynı yıl içinde çakışan dönem var mı?
            if egitim_yili:
                donem = cleaned.get("donem")
                qs = OkulDonem.objects.filter(egitim_yili=egitim_yili).exclude(donem=donem)
                if self.instance.pk:
                    qs = qs.exclude(pk=self.instance.pk)
                for diger in qs:
                    if baslangic < diger.bitis and bitis > diger.baslangic:
                        raise ValidationError(
                            f"Bu dönem tarihleri aynı yıl içindeki diğer dönemle çakışıyor: "
                            f"{diger.get_donem_display()} ({diger.baslangic} – {diger.bitis})"
                        )
        return cleaned


class OkulDonemInline(admin.TabularInline):
    model = OkulDonem
    form = OkulDonemForm
    extra = 2
    fields = ("donem", "baslangic", "bitis")


@admin.register(EgitimOgretimYili)
class EgitimOgretimYiliAdmin(admin.ModelAdmin):
    form = EgitimOgretimYiliForm
    list_display = ("egitim_yili", "egitim_baslangic", "egitim_bitis")
    ordering = ("-egitim_yili",)
    inlines = [OkulDonemInline]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change:
            messages.info(
                request,
                f"'{obj.egitim_yili}' eğitim-öğretim yılı eklendi. "
                "Lütfen 1. ve 2. dönem başlangıç/bitiş tarihlerini de giriniz."
            )


@admin.register(OkulDonem)
class OkulDonemAdmin(admin.ModelAdmin):
    form = OkulDonemForm
    list_display = ("egitim_yili", "donem", "baslangic", "bitis")
    list_filter = ("egitim_yili",)
    ordering = ("-egitim_yili__egitim_yili", "donem")


@admin.register(OkulBilgi)
class OkulBilgiAdmin(admin.ModelAdmin):
    list_display = ("okul_adi", "okul_kodu", "okul_muduru", "okul_donem", "okul_egtyil")
    fields = ("okul_kodu", "okul_adi", "okul_muduru", "okul_donem", "okul_egtyil")


@admin.register(NobetPersonel)
class NobetPersonelAdmin(admin.ModelAdmin):
    list_display = (
        "adi_soyadi",
        "brans",
        "gorev_tipi",
        "cinsiyet",
        "nobeti_var",
        "kimlikno",
        "user",
    )
    search_fields = ("adi_soyadi", "kimlikno", "user__username")
    list_filter = ("brans", "gorev_tipi", "cinsiyet", "nobeti_var")


@admin.register(SinifSube)
class SinifSubeAdmin(admin.ModelAdmin):
    list_display = ("sinif", "sube")
    list_filter = ("sinif",)
    ordering = ("sinif", "sube")


class NobetIstatistikInline(admin.StackedInline):
    model = NobetIstatistik
    can_delete = False
    verbose_name_plural = "Nöbet İstatistikleri"
    readonly_fields = (
        "toplam_nobet",
        "atanmayan_nobet",
        "haftalik_ortalama",
        "hafta_sayisi",
        "son_nobet_tarihi",
        "son_nobet_yeri",
        "agirlikli_puan",
    )


@admin.register(NobetOgretmen)
class NobetOgretmenAdmin(admin.ModelAdmin):
    list_display = ("personel", "uygulama_tarihi")
    search_fields = ("personel__adi_soyadi",)
    list_filter = ("uygulama_tarihi",)
    inlines = [NobetIstatistikInline]


@admin.register(DersProgrami)
class DersProgramiAdmin(admin.ModelAdmin):
    list_display = ("ogretmen", "gun", "ders_saati", "ders_adi", "sinif_sube")
    search_fields = ("ogretmen__adi_soyadi", "ders__ders_adi")
    list_filter = ("gun", "sinif_sube")


@admin.register(NobetGorevi)
class NobetGoreviAdmin(admin.ModelAdmin):
    list_display = ("ogretmen", "nobet_gun", "nobet_yeri", "uygulama_tarihi")
    search_fields = ("ogretmen__personel__adi_soyadi", "nobet_yeri__ad")
    list_filter = ("nobet_gun", "nobet_yeri", "uygulama_tarihi")


@admin.register(Devamsizlik)
class DevamsizlikAdmin(admin.ModelAdmin):
    list_display = (
        "ogretmen",
        "baslangic_tarihi",
        "bitis_tarihi",
        "get_devamsiz_tur_display",
        "sure",
        "gorevlendirme_yapilsin",
    )
    list_filter = ("devamsiz_tur", "baslangic_tarihi", "gorevlendirme_yapilsin")
    search_fields = ("ogretmen__personel__adi_soyadi",)
    autocomplete_fields = ["ogretmen"]

    def get_devamsiz_tur_display(self, obj):
        return obj.get_devamsiz_tur_display()

    get_devamsiz_tur_display.short_description = "Devamsızlık Türü"


@admin.register(VeriYukleme)
class VeriYuklemeAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_urls(self):
        urls = super().get_urls()
        my_urls = [
            path(
                "",
                self.admin_site.admin_view(self.yukleme_view),
                name="nobet_veriyukleme_changelist",
            ),
        ]
        return my_urls + urls

    def yukleme_view(self, request):
        # ── Okul Bilgisi ──────────────────────────────────────
        mevcut_okul = OkulBilgi.objects.first()
        okul_initial = {
            "okul_kodu": mevcut_okul.okul_kodu if mevcut_okul else "",
            "okul_adi": mevcut_okul.okul_adi if mevcut_okul else "",
            "okul_muduru": mevcut_okul.okul_muduru if mevcut_okul else "",
        }

        # ── Sınıf/Şube başlangıç değerleri ────────────────────
        mevcut_siniflar = defaultdict(list)
        if not SinifSube.objects.exists():
            defaults = {
                9: ["A", "B", "C", "D", "E", "F"],
                10: ["A", "B", "C", "D", "E", "F", "G", "H", "İ"],
                11: ["A", "B", "C", "D", "E", "F", "G", "H"],
                12: ["A", "B", "C", "D", "E", "F", "G"],
            }
            for k, v in defaults.items():
                mevcut_siniflar[k] = v
        else:
            for s in SinifSube.objects.all().order_by("sinif", "sube"):
                mevcut_siniflar[s.sinif].append(s.sube)

        sinif_initial = {f"sinif_{k}": ",".join(v) for k, v in mevcut_siniflar.items()}

        # ── Form nesneleri ─────────────────────────────────────
        okul_form = OkulBilgiForm(request.POST or None, prefix="okul", initial=okul_initial)
        personel_form = PersonelImportForm(
            request.POST or None, request.FILES or None, prefix="personel"
        )
        sinif_form = SinifSubeImportForm(
            request.POST or None, prefix="sinif", initial=sinif_initial
        )
        ders_form = DersProgramiImportForm(
            request.POST or None, request.FILES or None, prefix="ders"
        )
        nobet_form = NobetImportForm(request.POST or None, request.FILES or None, prefix="nobet")

        if request.method == "POST":
            dp = DefaultPath()
            try:
                if "okul_bilgi_aktar" in request.POST and okul_form.is_valid():
                    OkulBilgi.objects.update_or_create(
                        id=1,
                        defaults={
                            "okul_kodu": okul_form.cleaned_data["okul_kodu"],
                            "okul_adi": okul_form.cleaned_data["okul_adi"],
                            "okul_muduru": okul_form.cleaned_data["okul_muduru"],
                        },
                    )
                    messages.success(request, "Okul bilgileri başarıyla kaydedildi.")

                elif "personel_aktar" in request.POST and personel_form.is_valid():
                    f = request.FILES["personel-dosya"]
                    tarih = personel_form.cleaned_data["uygulama_tarihi"]
                    path = self.save_file(f, dp)
                    PersonelIsleyici(personel_path=path.name, uygulama_tarihi=tarih, kullanici=request.user).calistir()
                    messages.success(request, "Personel listesi başarıyla aktarıldı.")

                elif "sinif_sube_aktar" in request.POST and sinif_form.is_valid():
                    sinif_bilgileri = {}
                    for level in [9, 10, 11, 12]:
                        raw = sinif_form.cleaned_data.get(f"sinif_{level}", "")
                        sinif_bilgileri[level] = [
                            s.strip().upper() for s in raw.split(",") if s.strip()
                        ]
                    sinif_sube_kaydet(sinif_bilgileri)
                    messages.success(request, "Sınıf ve Şube bilgileri başarıyla güncellendi.")

                elif "ders_programi_aktar" in request.POST and ders_form.is_valid():
                    f = request.FILES["ders-dosya"]
                    tarih = ders_form.cleaned_data["uygulama_tarihi"]
                    path = self.save_file(f, dp)
                    DersProgramiIsleyici(file_path=path.name, uygulama_tarihi=tarih, kullanici=request.user).calistir()
                    messages.success(request, "Ders programı başarıyla aktarıldı.")

                elif "nobet_aktar" in request.POST and nobet_form.is_valid():
                    f = request.FILES["nobet-dosya"]
                    tarih = nobet_form.cleaned_data["uygulama_tarihi"]
                    path = self.save_file(f, dp)
                    NobetIsleyici(nobet_path=path.name, uygulama_tarihi=tarih, kullanici=request.user).calistir()
                    messages.success(request, "Nöbetçi listesi başarıyla aktarıldı.")

            except Exception as e:
                messages.error(request, f"Hata oluştu: {str(e)}")

            return redirect(request.path)

        # ── Adım tamamlanma durumları ──────────────────────────
        adimlar = [
            OkulBilgi.objects.exists(),
            NobetPersonel.objects.exists(),
            SinifSube.objects.exists(),
            DersProgrami.objects.exists(),
            NobetGorevi.objects.exists(),
        ]
        tamamlanan = sum(adimlar)
        aktif_adim = next((i + 1 for i, done in enumerate(adimlar) if not done), 6)

        # ── Son aktarım kayıtları ──────────────────────────────
        from okul.models import VeriAktarimGecmisi
        son_aktarimlar = (
            VeriAktarimGecmisi.objects
            .filter(dosya_turu__in=["personel_listesi", "ders_programi", "nobet_listesi"])
            .order_by("-yukleme_tarihi")[:10]
        )

        context = {
            "title": "Kurulum Sihirbazı",
            "opts": self.model._meta,
            "okul_form": okul_form,
            "personel_form": personel_form,
            "sinif_form": sinif_form,
            "ders_form": ders_form,
            "nobet_form": nobet_form,
            "adimlar": adimlar,
            "tamamlanan": tamamlanan,
            "aktif_adim": aktif_adim,
            "son_aktarimlar": son_aktarimlar,
            "media": self.media,
        }
        context.update(self.admin_site.each_context(request))
        return render(request, "admin/nobet/veriyukleme/change_list.html", context)

    def save_file(self, f, dp):
        """Yüklenen dosyayı DefaultPath.VERI_DIR altına kaydeder."""
        file_path = dp.VERI_DIR / f.name
        with open(file_path, "wb+") as destination:
            for chunk in f.chunks():
                destination.write(chunk)
        return file_path


# ──────────────────────────────────────────────
# Öğretmen kullanıcı şifre sıfırlama — custom UserAdmin
# ──────────────────────────────────────────────

User = get_user_model()


class OgretmenSifreDegistirForm(forms.Form):
    yeni_sifre = forms.CharField(
        label="Yeni Şifre",
        widget=forms.PasswordInput(render_value=True),
        min_length=6,
    )
    yeni_sifre2 = forms.CharField(
        label="Yeni Şifre (Tekrar)",
        widget=forms.PasswordInput(render_value=True),
        min_length=6,
    )

    def clean(self):
        cleaned = super().clean()
        s1 = cleaned.get("yeni_sifre", "")
        s2 = cleaned.get("yeni_sifre2", "")
        if s1 and s2 and s1 != s2:
            raise forms.ValidationError("Şifreler eşleşmiyor.")
        return cleaned


admin.site.unregister(User)


@admin.register(User)
class CustomUserAdmin(BaseUserAdmin):
    change_list_template = "admin/auth/user/change_list.html"

    def get_urls(self):
        urls = super().get_urls()
        extra = [
            path(
                "ogretmen-sifre-degistir/",
                self.admin_site.admin_view(self.ogretmen_sifre_degistir_view),
                name="ogretmen_sifre_degistir",
            ),
        ]
        return extra + urls

    def ogretmen_sifre_degistir_view(self, request):
        ogretmenler = User.objects.filter(groups__name="ogretmen", is_active=True)
        form = OgretmenSifreDegistirForm(request.POST or None)

        if request.method == "POST" and form.is_valid():
            yeni_sifre = form.cleaned_data["yeni_sifre"]
            sayi = 0
            for user in ogretmenler:
                user.set_password(yeni_sifre)
                user.save(update_fields=["password"])
                sayi += 1
            self.message_user(
                request,
                f"{sayi} öğretmen kullanıcısının şifresi başarıyla değiştirildi.",
                level=messages.SUCCESS,
            )
            return redirect("../")

        context = {
            "title": "Öğretmen Şifrelerini Değiştir",
            "form": form,
            "ogretmen_sayisi": ogretmenler.count(),
            "ogretmenler": ogretmenler.order_by("username")[:20],
            "opts": self.model._meta,
            **self.admin_site.each_context(request),
        }
        return render(request, "admin/ogretmen_sifre_degistir.html", context)
