from django import forms

from .models import Proveedor


BASE_CLASS = (
    "w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm text-slate-900 "
    "shadow-sm outline-none transition duration-200 focus:border-cyan-500 focus:ring-4 focus:ring-cyan-100"
)


class ProveedorForm(forms.ModelForm):
    class Meta:
        model = Proveedor
        fields = [
            "tipo_proveedor", "tipo_identificacion", "identificacion", "razon_social",
            "nombre_comercial", "nombre_contacto", "correo_electronico", "telefono",
            "direccion", "ciudad", "pais", "observaciones",
        ]
        widgets = {"observaciones": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        etiquetas = {
            "tipo_proveedor": "Tipo de proveedor", "tipo_identificacion": "Tipo de identificacion",
            "identificacion": "Numero de identificacion", "razon_social": "Razon social",
            "nombre_comercial": "Nombre comercial", "nombre_contacto": "Nombre del contacto",
            "correo_electronico": "Correo electronico", "telefono": "Telefono",
            "direccion": "Direccion", "ciudad": "Ciudad", "pais": "Pais",
            "observaciones": "Observaciones",
        }
        for nombre, campo in self.fields.items():
            campo.label = etiquetas.get(nombre, campo.label)
            campo.widget.attrs["class"] = BASE_CLASS
        self.fields["identificacion"].help_text = "Se guardara sin espacios, puntos ni guiones."
        self.fields["pais"].help_text = "La longitud ecuatoriana solo se exige para Ecuador."
