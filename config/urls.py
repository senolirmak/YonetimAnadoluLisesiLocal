"""
URL configuration for nobetgorevi project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from personel import views as personel_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path(
        "giris/",
        auth_views.LoginView.as_view(template_name="registration/login.html"),
        name="login",
    ),
    path("cikis/", auth_views.LogoutView.as_view(), name="logout"),
    path("kayit/", personel_views.kayit, name="kayit"),
    path("kayit/tc-sorgula/", personel_views.tc_sorgula, name="tc_sorgula"),
    path("profil/", personel_views.profil, name="profil"),
    path("personel/", include("personel.urls")),
    path("faaliyet/", include("faaliyet.urls")),
    path("duyuru/", include("duyuru.urls")),
    path("ogrenci/", include("ogrenci.urls")),
    path("devamsizlik/", include("devamsizlik.urls")),
    path("rehberlik/", include("rehberlik.urls")),
    path("disiplin/", include("disiplin.urls")),
    path("muduriyetcagri/", include("muduriyetcagri.urls")),
    path("cagri/", include("cagri.urls")),
    path("dersprogrami/", include("dersprogrami.urls")),
    path("personeldevamsizlik/", include("personeldevamsizlik.urls")),
    path("veriaktar/", include("veriaktar.urls")),
    path("ogrencinobet/", include("ogrencinobet.urls")),
    path("pano/", include("pano.urls")),
    path("okul/", include("okul.urls")),
    path("sinav/", include("sinav.urls")),
    path("dersdefteri/", include("dersdefteri.urls")),
    path("sinavmedia/", include("sinavmedia.urls")),
    path("bildirim/", include("bildirim_gonderici.urls")),
    path("sorumluluk/", include("sorumluluk.urls")),
    path("ekders/", include("ekders.urls")),
    path("", include("main.urls")),
    path("", include("nobet.urls")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
