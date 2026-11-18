from django.contrib import admin, messages
from django.utils.html import format_html

from tahtalar.models import KOMUT_GECERLILIK, Tahta, TahtaEnvanteri, TahtaKomutu
from tahtalar.services import ajan_api


class CevrimiciFiltresi(admin.SimpleListFilter):
    title = "bağlantı"
    parameter_name = "baglanti"

    def lookups(self, request, model_admin):
        return [("cevrimici", "Çevrimiçi"), ("cevrimdisi", "Çevrimdışı")]

    def queryset(self, request, queryset):
        if self.value() == "cevrimici":
            return queryset.cevrimici()
        if self.value() == "cevrimdisi":
            return queryset.cevrimdisi()
        return queryset


class TahtaKomutuInline(admin.TabularInline):
    model = TahtaKomutu
    extra = 0
    max_num = 0
    can_delete = False
    fields = ("komut", "durum", "sonuc_mesaji", "olusturan", "olusturma", "tamamlanma")
    readonly_fields = fields
    ordering = ("-olusturma",)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("olusturan")


@admin.register(Tahta)
class TahtaAdmin(admin.ModelAdmin):
    list_display = (
        "ad",
        "konum",
        "baglanti",
        "ahenk",
        "meb_kayitli",
        "son_gorulme",
        "ip_adresi",
        "ajan_surumu",
        "lider_kaydi",
        "aktif",
    )
    list_filter = (CevrimiciFiltresi, "ahenk_servisi", "meb_kayitli", "aktif")
    list_select_related = ("envanter",)
    search_fields = ("ad", "konum", "hostname", "ip_adresi", "makine_kimligi")
    list_editable = ("konum",)
    actions = ("kapat", "yeniden_baslat", "guncelle")
    inlines = (TahtaKomutuInline,)
    readonly_fields = (
        "envanter",
        "mac_adresleri",
        "makine_kimligi",
        "hostname",
        "ip_adresi",
        "isletim_sistemi",
        "ajan_surumu",
        "acik_kalma_suresi",
        "ahenk_servisi",
        "meb_kayitli",
        "guncelleme_durumu",
        "guncelleme_zamani",
        "oturumlar",
        "son_gorulme",
        "kayit_tarihi",
    )
    fieldsets = (
        (None, {"fields": ("ad", "konum", "aktif", "envanter")}),
        (
            "Tahtanın bildirdiği durum",
            {
                "fields": (
                    "son_gorulme",
                    "ahenk_servisi",
                    "meb_kayitli",
                    "guncelleme_durumu",
                    "guncelleme_zamani",
                    "oturumlar",
                    "hostname",
                    "ip_adresi",
                    "mac_adresleri",
                    "isletim_sistemi",
                    "ajan_surumu",
                    "acik_kalma_suresi",
                    "makine_kimligi",
                    "kayit_tarihi",
                )
            },
        ),
    )

    def has_add_permission(self, request):
        # Tahtalar akal-eta-yonetim üzerinden kendini kaydeder.
        return False

    @admin.display(description="Lider kaydı", boolean=True)
    def lider_kaydi(self, obj):
        return obj.envanter_id is not None

    @admin.display(description="Bağlantı", boolean=True)
    def baglanti(self, obj):
        return obj.cevrimici

    @admin.display(description="Ahenk", ordering="ahenk_servisi")
    def ahenk(self, obj):
        renk = {
            Tahta.AHENK_CALISIYOR: "#198754",
            Tahta.AHENK_DURMUS: "#dc3545",
            Tahta.AHENK_YOK: "#6c757d",
        }.get(obj.ahenk_servisi, "#6c757d")
        return format_html(
            '<span style="color:{}">{}</span>', renk, obj.get_ahenk_servisi_display()
        )

    def has_komut_permission(self, request):
        return request.user.has_perm("tahtalar.add_tahtakomutu")

    def _komut_ver(self, request, queryset, komut, etiket):
        tahtalar = list(queryset)
        sayi = ajan_api.komut_olustur(tahtalar, komut, request.user)
        self.message_user(request, f"{sayi} tahtaya “{etiket}” komutu verildi.", messages.SUCCESS)
        cevrimdisi = [t.ad for t in tahtalar if not t.cevrimici]
        if cevrimdisi:
            dakika = int(KOMUT_GECERLILIK.total_seconds() // 60)
            self.message_user(
                request,
                f"Çevrimdışı tahtalar: {', '.join(cevrimdisi)}. "
                f"Bunlar {dakika} dakika içinde bağlanmazsa komut iptal olur.",
                messages.WARNING,
            )

    @admin.action(description="Seçili tahtaları kapat", permissions=["komut"])
    def kapat(self, request, queryset):
        self._komut_ver(request, queryset, TahtaKomutu.KAPAT, "kapat")

    @admin.action(description="Seçili tahtaları yeniden başlat", permissions=["komut"])
    def yeniden_baslat(self, request, queryset):
        self._komut_ver(request, queryset, TahtaKomutu.YENIDEN_BASLAT, "yeniden başlat")

    @admin.action(description="Seçili tahtaları güncelle", permissions=["komut"])
    def guncelle(self, request, queryset):
        self._komut_ver(request, queryset, TahtaKomutu.GUNCELLE, "güncelle")


@admin.register(TahtaKomutu)
class TahtaKomutuAdmin(admin.ModelAdmin):
    list_display = ("tahta", "komut", "durum", "olusturan", "olusturma", "tamamlanma")
    list_filter = ("durum", "komut")
    search_fields = ("tahta__ad",)
    list_select_related = ("tahta", "olusturan")
    actions = ("iptal_et",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @admin.action(description="Bekleyen komutları iptal et", permissions=["delete"])
    def iptal_et(self, request, queryset):
        sayi = queryset.filter(durum=TahtaKomutu.BEKLIYOR).update(
            durum=TahtaKomutu.IPTAL, sonuc_mesaji="Yönetici iptal etti."
        )
        self.message_user(request, f"{sayi} komut iptal edildi.", messages.SUCCESS)


@admin.register(TahtaEnvanteri)
class TahtaEnvanteriAdmin(admin.ModelAdmin):
    """MEB Lider'den alınan liste — salt okunur; güncellemek için Excel yeniden yüklenir
    (`python manage.py tahta_envanteri_yukle`)."""

    list_display = (
        "sube_adi",
        "mac_adresi",
        "ip_adresi",
        "lider_cevrimici",
        "lider_aktif",
        "ahenk_surumu",
        "model",
        "disk_bos_gb",
        "lider_durum_degisim",
        "ajan_tahtasi",
    )
    list_filter = ("lider_aktif", "lider_cevrimici", "ahenk_surumu", "model")
    search_fields = ("sube_adi", "mac_adresi", "ip_adresi", "lider_id")
    list_select_related = ("tahta",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @admin.display(description="akal-eta-yonetim bağlı", boolean=True)
    def ajan_tahtasi(self, obj):
        return hasattr(obj, "tahta")
