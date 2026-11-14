from django.contrib import admin

from .models import PerfilUsuario


@admin.register(PerfilUsuario)
class PerfilUsuarioAdmin(admin.ModelAdmin):
    list_display = ("user", "telefono", "cargo_visible", "updated_at")
    search_fields = (
        "user__username",
        "user__first_name",
        "user__last_name",
        "telefono",
        "cargo_visible",
    )
