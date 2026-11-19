from django.urls import path, re_path

from . import views, views_eta, views_paket, views_panel

app_name = "tahtalar"

urlpatterns = [
    path("", views_panel.tahta_listesi, name="liste"),
    path("komut/", views_panel.komut_ver, name="komut_ver"),
    path("eta/", views_eta.eta_sayfasi, name="eta"),
    path("paket/", views_paket.paket_sayfasi, name="paket"),
    # Tahtada wget ile çekilen süreli, imzalı paket linki (oturum gerektirmez)
    path("paket/indir/<str:token>/", views_paket.paket_link, name="paket_link"),
    # Tahtaların akal-eta-yonetim güncellemelerini çektiği APT deposu (oturumsuz;
    # gizli bilgi içermez). Düz depo: APT adresleri "apt/./InRelease" biçiminde ister.
    re_path(
        r"^apt/(?:\./)?(?P<dosya>[A-Za-z0-9][A-Za-z0-9._+~-]*)$",
        views_paket.apt_deposu_dosyasi,
        name="apt_deposu",
    ),
    # Tahtadaki akal-eta-yonetim'in uç noktaları (token ile)
    path("api/kayit/", views.kayit, name="api_kayit"),
    path("api/durum/", views.durum, name="api_durum"),
]
