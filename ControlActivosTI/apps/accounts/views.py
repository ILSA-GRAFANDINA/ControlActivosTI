from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.views.generic import FormView

from .forms import CustomAuthenticationForm, PerfilUsuarioForm
from .models import PerfilUsuario


class CustomLoginView(LoginView):
    template_name = "registration/login.html"
    authentication_form = CustomAuthenticationForm
    redirect_authenticated_user = True

    def get_success_url(self):
        return reverse_lazy("dashboard-inicio")

    def form_valid(self, form):
        response = super().form_valid(form)
        if self.request.POST.get("remember_me"):
            self.request.session.set_expiry(60 * 60 * 24 * 14)
        else:
            self.request.session.set_expiry(0)
        return response


class PerfilUsuarioView(LoginRequiredMixin, FormView):
    template_name = "accounts/perfil.html"
    form_class = PerfilUsuarioForm

    def get_profile(self):
        profile, _ = PerfilUsuario.objects.get_or_create(user=self.request.user)
        return profile

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        kwargs["profile"] = self.get_profile()
        return kwargs

    def get_success_url(self):
        return reverse("accounts:perfil")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        profile = self.get_profile()
        user = self.request.user
        full_name = user.get_full_name().strip()
        context["profile"] = profile
        context["full_name"] = full_name or user.get_username()
        context["profile_title"] = "Mi perfil"
        return context

    def form_valid(self, form):
        form.save()
        messages.success(self.request, "Tu perfil fue actualizado correctamente.")
        return redirect(self.get_success_url())
