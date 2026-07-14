from django import forms
from django.contrib.auth.forms import AuthenticationForm

class CustomAuthenticationForm(AuthenticationForm):
    error_messages = {
        "invalid_login": "Usuario o contraseña incorrectos. Verifica tus credenciales.",
        "inactive": "Tu cuenta se encuentra inactiva.",
    }

    username = forms.CharField(
        label="Usuario",
        max_length=150,
        widget=forms.TextInput(
            attrs={
                "class": (
                    "w-full rounded-2xl border border-white/10 bg-white/5 "
                    "py-3.5 pl-12 pr-4 text-sm text-white placeholder:text-slate-400 "
                    "outline-none transition duration-200 "
                    "focus:border-cyan-400/70 focus:bg-white/10 focus:ring-4 focus:ring-cyan-400/15"
                ),
                "placeholder": "Ingresa tu usuario",
                "autofocus": True,
                "autocomplete": "username",
                "spellcheck": "false",
            }
        ),
    )

    password = forms.CharField(
        label="Contraseña",
        widget=forms.PasswordInput(
            attrs={
                "class": (
                    "w-full rounded-2xl border border-white/10 bg-white/5 "
                    "py-3.5 pl-12 pr-16 text-sm text-white placeholder:text-slate-400 "
                    "outline-none transition duration-200 "
                    "focus:border-cyan-400/70 focus:bg-white/10 focus:ring-4 focus:ring-cyan-400/15"
                ),
                "placeholder": "Ingresa tu contraseña",
                "autocomplete": "current-password",
            }
        ),
    )


class PerfilUsuarioForm(forms.Form):
    first_name = forms.CharField(label="Nombres", max_length=150, required=False)
    last_name = forms.CharField(label="Apellidos", max_length=150, required=False)
    email = forms.EmailField(label="Correo electrónico", required=False)
    telefono = forms.CharField(label="Teléfono", max_length=30, required=False)
    cargo_visible = forms.CharField(label="Cargo visible", max_length=120, required=False)
    bio = forms.CharField(
        label="Biografía breve",
        required=False,
        widget=forms.Textarea(attrs={"rows": 4}),
    )
    foto = forms.ImageField(label="Foto de perfil", required=False)
    remove_photo = forms.BooleanField(label="Quitar foto actual", required=False)

    def __init__(self, *args, user, profile, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.profile = profile

        self.fields["first_name"].initial = user.first_name
        self.fields["last_name"].initial = user.last_name
        self.fields["email"].initial = user.email
        self.fields["telefono"].initial = profile.telefono
        self.fields["cargo_visible"].initial = profile.cargo_visible
        self.fields["bio"].initial = profile.bio

        input_class = (
            "mt-2 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 "
            "text-sm text-slate-800 outline-none transition "
            "focus:border-cyan-400 focus:ring-4 focus:ring-cyan-100"
        )

        for field in self.fields.values():
            if isinstance(field.widget, forms.Textarea):
                field.widget.attrs.update(
                    {
                        "class": input_class,
                        "placeholder": "Agrega una descripción breve para tu perfil",
                    }
                )
            elif isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.update(
                    {
                        "class": "h-4 w-4 rounded border-slate-300 text-cyan-600 focus:ring-cyan-500",
                    }
                )
            elif isinstance(field.widget, forms.ClearableFileInput):
                field.widget.attrs.update(
                    {
                        "class": (
                            "mt-2 block w-full rounded-2xl border border-dashed border-slate-300 "
                            "bg-slate-50 px-4 py-3 text-sm text-slate-600 file:mr-4 file:rounded-xl "
                            "file:border-0 file:bg-slate-900 file:px-4 file:py-2 file:text-sm "
                            "file:font-semibold file:text-white hover:file:bg-slate-800"
                        ),
                        "accept": "image/*",
                    }
                )
            else:
                field.widget.attrs.update({"class": input_class})

    def clean_foto(self):
        foto = self.cleaned_data.get("foto")
        if foto and foto.content_type and not foto.content_type.startswith("image/"):
            raise forms.ValidationError("Debes subir un archivo de imagen válido.")
        return foto

    def save(self):
        self.user.first_name = self.cleaned_data["first_name"].strip()
        self.user.last_name = self.cleaned_data["last_name"].strip()
        self.user.email = self.cleaned_data["email"].strip()
        self.user.save(update_fields=["first_name", "last_name", "email"])

        self.profile.telefono = self.cleaned_data["telefono"].strip()
        self.profile.cargo_visible = self.cleaned_data["cargo_visible"].strip()
        self.profile.bio = self.cleaned_data["bio"].strip()

        if self.cleaned_data["remove_photo"] and self.profile.foto:
            self.profile.foto.delete(save=False)
            self.profile.foto = None

        foto = self.cleaned_data.get("foto")
        if foto:
            if self.profile.foto:
                self.profile.foto.delete(save=False)
            self.profile.foto = foto

        self.profile.save()
        return self.profile
