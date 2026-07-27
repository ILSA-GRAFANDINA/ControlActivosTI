from django import forms

from .models import Notificacion


class NotificacionFiltroForm(forms.Form):
    tipo = forms.ChoiceField(
        required=False,
        choices=[("", "Todos los tipos"), *Notificacion.Tipo.choices],
    )
    fecha_desde = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    fecha_hasta = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))

