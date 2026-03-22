from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from .forms import DevamsizlikForm
from .models import Devamsizlik


def _is_mudur_yardimcisi(user):
    return user.is_superuser or user.groups.filter(name="mudur_yardimcisi").exists()


class MudurYardimcisiMixin(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not _is_mudur_yardimcisi(request.user):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class DevamsizlikListView(MudurYardimcisiMixin, ListView):
    model = Devamsizlik
    template_name = "personeldevamsizlik/devamsizlik_list.html"
    context_object_name = "devamsizliklar"
    ordering = ["-baslangic_tarihi"]

    def get_queryset(self):
        return (
            Devamsizlik.objects.select_related("ogretmen__personel")
            .all()
            .order_by("-baslangic_tarihi")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Devamsız Öğretmen Bilgileri"
        return context


class DevamsizlikCreateView(MudurYardimcisiMixin, CreateView):
    model = Devamsizlik
    form_class = DevamsizlikForm
    template_name = "personeldevamsizlik/devamsizlik_form.html"
    success_url = reverse_lazy("devamsizlik_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Yeni Devamsızlık Kaydı"
        return context


class DevamsizlikUpdateView(MudurYardimcisiMixin, UpdateView):
    model = Devamsizlik
    form_class = DevamsizlikForm
    template_name = "personeldevamsizlik/devamsizlik_form.html"
    success_url = reverse_lazy("devamsizlik_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Devamsızlık Kaydını Düzenle"
        return context


class DevamsizlikDeleteView(MudurYardimcisiMixin, DeleteView):
    model = Devamsizlik
    template_name = "personeldevamsizlik/devamsizlik_confirm_delete.html"
    success_url = reverse_lazy("devamsizlik_list")
    context_object_name = "devamsizlik"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Devamsızlık Kaydını Sil"
        return context
