from django import forms
from django.db.models import Max
from django.forms import inlineformset_factory

from .models import AtributoActivo, OpcionAtributoActivo, TipoActivo, TipoActivoAtributo


def aplicar_estilo_admin2(form):
    for field in form.fields.values():
        if isinstance(field.widget, forms.CheckboxInput):
            field.widget.attrs["class"] = "admin2-checkbox"
        elif isinstance(field.widget, forms.Textarea):
            field.widget.attrs["class"] = "admin2-textarea"
        else:
            field.widget.attrs["class"] = "admin2-input"
    return form


class AtributoActivoAdmin2Form(forms.ModelForm):
    clave = forms.CharField(
        max_length=80,
        help_text="Se normaliza a minusculas y guiones bajos; no cambia al editar el nombre.",
    )

    class Meta:
        model = AtributoActivo
        fields = ("nombre", "clave", "descripcion", "tipo_dato", "unidad", "activo")
        widgets = {"descripcion": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        aplicar_estilo_admin2(self)

    def clean_clave(self):
        return AtributoActivo.normalizar_clave(self.cleaned_data["clave"])


class OpcionAtributoActivoAdmin2Form(forms.ModelForm):
    class Meta:
        model = OpcionAtributoActivo
        fields = ("clave", "nombre", "orden", "activo")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        aplicar_estilo_admin2(self)

    def has_changed(self):
        # Los valores predeterminados de orden/activo no convierten una fila extra vacia en obligatoria.
        if not self.instance.pk and not self.data.get(self.add_prefix("clave"), "").strip() and not self.data.get(self.add_prefix("nombre"), "").strip():
            return False
        return super().has_changed()


OpcionAtributoActivoAdmin2FormSet = inlineformset_factory(
    AtributoActivo,
    OpcionAtributoActivo,
    form=OpcionAtributoActivoAdmin2Form,
    extra=2,
    can_delete=False,
)


class TipoActivoAtributoAdmin2Form(forms.ModelForm):
    class Meta:
        model = TipoActivoAtributo
        fields = (
            "tipo_activo", "atributo", "orden", "obligatorio",
            "valor_predeterminado", "texto_ayuda", "unidad",
            "mostrar_detalle", "mostrar_actas", "mostrar_reportes",
            "activo", "longitud_maxima", "valor_minimo",
            "valor_maximo", "validaciones",
        )
        widgets = {
            "texto_ayuda": forms.Textarea(attrs={"rows": 3}),
            "valor_predeterminado": forms.Textarea(attrs={"rows": 2}),
            "validaciones": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        self.creando = kwargs.pop("creando", not bool(kwargs.get("instance") and kwargs["instance"].pk))
        super().__init__(*args, **kwargs)
        if self.creando:
            self.fields.pop("orden", None)
        else:
            self.fields["tipo_activo"].disabled = True
            self.fields["atributo"].disabled = True
        self.fields["tipo_activo"].queryset = TipoActivo.objects.filter(activo=True).order_by("nombre")
        atributos = AtributoActivo.objects.filter(activo=True)
        if self.instance.pk:
            atributos = AtributoActivo.objects.filter(pk=self.instance.atributo_id) | atributos
        self.fields["atributo"].queryset = atributos.distinct().order_by("nombre")
        self.fields["valor_predeterminado"].help_text = (
            "Opcional. Debe respetar el tipo de dato; para listas use el ID de la opcion."
        )
        self.fields["validaciones"].help_text = "Objeto JSON opcional. Ejemplo: {}"
        aplicar_estilo_admin2(self)

    def clean(self):
        cleaned = super().clean()
        if self.creando:
            tipo_activo = cleaned.get("tipo_activo")
            if tipo_activo:
                ultimo = (
                    TipoActivoAtributo.objects.filter(tipo_activo=tipo_activo, activo=True)
                    .aggregate(maximo=Max("orden"))["maximo"]
                    or 0
                )
                self.instance.orden = ultimo + 1
        return cleaned


class CriterioBusquedaActivoForm(forms.Form):
    criterios = forms.ModelMultipleChoiceField(
        queryset=TipoActivoAtributo.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Atributos incluidos en la busqueda",
        help_text=(
            "La busqueda de /activos consultara el valor de los atributos seleccionados. "
            "La seleccion se configura de forma independiente para cada tipo de activo."
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        queryset = (
            TipoActivoAtributo.objects.filter(
                activo=True,
                tipo_activo__activo=True,
                atributo__activo=True,
            )
            .exclude(atributo__tipo_dato=AtributoActivo.TipoDato.TEXTO_PROTEGIDO)
            .select_related("tipo_activo", "atributo")
            .order_by("tipo_activo__nombre", "orden", "atributo__nombre")
        )
        self.fields["criterios"].queryset = queryset
        if not self.is_bound:
            self.initial["criterios"] = queryset.filter(filtrable=True)
