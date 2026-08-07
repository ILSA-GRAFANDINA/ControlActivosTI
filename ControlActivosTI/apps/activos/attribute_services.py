from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.auditoria.models import RegistroAuditoria
from apps.auditoria.services import registrar_evento
from apps.catalogos.models import AtributoActivo, TipoActivoAtributo

from .encryption import encrypt_protected_text
from .models import Activo, ValorAtributoActivo


LEGACY_FIELD_BY_KEY = {
    "procesador": "cpu",
    "cpu": "cpu",
    "memoria_ram": "ram",
    "ram": "ram",
    "almacenamiento": "disco",
    "disco": "disco",
    "sistema_operativo": "sistema_operativo",
}


def configuraciones_para_tipo(tipo_activo_id, *, incluir_inactivas=False):
    queryset = (
        TipoActivoAtributo.objects.filter(tipo_activo_id=tipo_activo_id)
        .select_related("atributo")
        .prefetch_related("atributo__opciones")
        .order_by("orden", "atributo__nombre")
    )
    if not incluir_inactivas:
        queryset = queryset.filter(activo=True, atributo__activo=True)
    return queryset


def _valor_vacio(valor):
    return valor is None or valor == ""


def validar_valor(configuracion, valor):
    atributo = configuracion.atributo
    if _valor_vacio(valor):
        if configuracion.obligatorio:
            raise ValidationError(f"{atributo.nombre} es obligatorio.")
        return None

    tipo = atributo.tipo_dato
    if tipo in {
        AtributoActivo.TipoDato.TEXTO_CORTO,
        AtributoActivo.TipoDato.TEXTO_LARGO,
        AtributoActivo.TipoDato.TEXTO_PROTEGIDO,
    }:
        valor = str(valor).strip()
        maximo = configuracion.longitud_maxima
        if maximo and len(valor) > maximo:
            raise ValidationError(f"{atributo.nombre} admite maximo {maximo} caracteres.")
    elif tipo == AtributoActivo.TipoDato.ENTERO:
        if isinstance(valor, bool):
            raise ValidationError(f"{atributo.nombre} debe ser un numero entero.")
        try:
            valor = int(valor)
        except (TypeError, ValueError) as exc:
            mensaje = f"{atributo.nombre} debe ser un numero entero."
            if configuracion.unidad_efectiva:
                mensaje += f" Ingresa solo el valor, sin la unidad {configuracion.unidad_efectiva}."
            raise ValidationError(mensaje) from exc
    elif tipo == AtributoActivo.TipoDato.DECIMAL:
        try:
            valor = Decimal(str(valor))
        except (InvalidOperation, TypeError, ValueError) as exc:
            mensaje = f"{atributo.nombre} debe ser un numero decimal."
            if configuracion.unidad_efectiva:
                mensaje += f" Ingresa solo el valor, sin la unidad {configuracion.unidad_efectiva}."
            raise ValidationError(mensaje) from exc
    elif tipo == AtributoActivo.TipoDato.FECHA:
        if not isinstance(valor, date):
            raise ValidationError(f"{atributo.nombre} debe ser una fecha valida.")
    elif tipo == AtributoActivo.TipoDato.BOOLEANO:
        if not isinstance(valor, bool):
            raise ValidationError(f"{atributo.nombre} debe indicar Si o No.")
    elif tipo == AtributoActivo.TipoDato.LISTA:
        if getattr(valor, "atributo_id", None) != atributo.pk or not valor.activo:
            raise ValidationError(f"Selecciona una opcion valida para {atributo.nombre}.")

    if tipo in {AtributoActivo.TipoDato.ENTERO, AtributoActivo.TipoDato.DECIMAL}:
        if configuracion.valor_minimo is not None and Decimal(valor) < configuracion.valor_minimo:
            raise ValidationError(f"{atributo.nombre} no puede ser menor que {configuracion.valor_minimo}.")
        if configuracion.valor_maximo is not None and Decimal(valor) > configuracion.valor_maximo:
            raise ValidationError(f"{atributo.nombre} no puede ser mayor que {configuracion.valor_maximo}.")
    return valor


def _asignar_valor_tipado(instancia, valor):
    for campo in ValorAtributoActivo.CAMPOS_VALOR:
        setattr(instancia, campo, "" if campo == "valor_texto" else None)
    tipo = instancia.atributo.tipo_dato
    campo = {
        AtributoActivo.TipoDato.TEXTO_CORTO: "valor_texto",
        AtributoActivo.TipoDato.TEXTO_LARGO: "valor_texto",
        AtributoActivo.TipoDato.TEXTO_PROTEGIDO: "valor_texto",
        AtributoActivo.TipoDato.ENTERO: "valor_entero",
        AtributoActivo.TipoDato.DECIMAL: "valor_decimal",
        AtributoActivo.TipoDato.FECHA: "valor_fecha",
        AtributoActivo.TipoDato.BOOLEANO: "valor_booleano",
        AtributoActivo.TipoDato.LISTA: "valor_opcion",
    }[tipo]
    if tipo == AtributoActivo.TipoDato.TEXTO_PROTEGIDO:
        valor = encrypt_protected_text(valor)
    setattr(instancia, campo, valor)


def _legacy_text(configuracion, valor):
    if valor in (None, ""):
        return ""
    if isinstance(valor, bool):
        texto = "Si" if valor else "No"
    elif hasattr(valor, "nombre"):
        texto = valor.nombre
    elif isinstance(valor, date):
        texto = valor.isoformat()
    else:
        texto = str(valor)
    unidad = configuracion.unidad_efectiva
    return f"{texto} {unidad}".strip() if unidad else texto


@transaction.atomic
def guardar_valores_atributos(activo, valores_por_clave, *, usuario=None):
    configuraciones = list(configuraciones_para_tipo(activo.tipo_activo_id))
    claves_configuradas = {config.atributo.clave for config in configuraciones}
    desconocidas = set(valores_por_clave) - claves_configuradas
    if desconocidas:
        raise ValidationError(f"Atributos no permitidos para el tipo: {', '.join(sorted(desconocidas))}.")

    ValorAtributoActivo.objects.filter(activo=activo).exclude(
        atributo_id__in=[config.atributo_id for config in configuraciones]
    ).update(vigente=False)

    cambios_legacy = {}
    for configuracion in configuraciones:
        clave = configuracion.atributo.clave
        existente = ValorAtributoActivo.objects.filter(
            activo=activo, atributo=configuracion.atributo
        ).first()
        anterior = existente.valor_formateado if existente else ""
        valor_crudo = valores_por_clave.get(clave)
        if (
            configuracion.atributo.tipo_dato == AtributoActivo.TipoDato.TEXTO_PROTEGIDO
            and existente
            and _valor_vacio(valor_crudo)
        ):
            continue
        valor = validar_valor(configuracion, valor_crudo)
        if valor is None:
            if existente:
                detalle = {"atributo": clave, "anterior": anterior, "nuevo": ""}
                existente.delete()
                registrar_evento(
                    entidad="ValorAtributoActivo", objeto_id=activo.pk,
                    accion=RegistroAuditoria.Accion.MODIFICAR,
                    resumen=f"Se limpio {configuracion.atributo.nombre} de {activo.codigo}",
                    usuario=usuario, detalle=detalle,
                )
            continue

        instancia = existente or ValorAtributoActivo(
            activo=activo,
            atributo=configuracion.atributo,
            tipo_activo_origen=activo.tipo_activo,
            created_by=usuario if getattr(usuario, "is_authenticated", False) else None,
        )
        instancia.tipo_activo_origen = activo.tipo_activo
        instancia.vigente = True
        instancia.requiere_revision = False
        instancia.updated_by = usuario if getattr(usuario, "is_authenticated", False) else None
        _asignar_valor_tipado(instancia, valor)
        instancia.save()
        nuevo = instancia.valor_formateado
        if anterior != nuevo:
            registrar_evento(
                entidad="ValorAtributoActivo", objeto_id=activo.pk,
                accion=RegistroAuditoria.Accion.MODIFICAR,
                resumen=f"Se actualizo {configuracion.atributo.nombre} de {activo.codigo}",
                usuario=usuario,
                detalle={"atributo": clave, "anterior": anterior, "nuevo": nuevo},
            )
        campo_legacy = LEGACY_FIELD_BY_KEY.get(clave)
        if campo_legacy:
            cambios_legacy[campo_legacy] = _legacy_text(configuracion, valor)

    if cambios_legacy:
        Activo.objects.filter(pk=activo.pk).update(**cambios_legacy)
        for campo, valor in cambios_legacy.items():
            setattr(activo, campo, valor)
    return activo


def valores_visibles(activo, *, destino="detalle"):
    bandera = {
        "detalle": "mostrar_detalle",
        "actas": "mostrar_actas",
        "reportes": "mostrar_reportes",
    }[destino]
    configuraciones = {
        config.atributo_id: config
        for config in configuraciones_para_tipo(activo.tipo_activo_id)
        if getattr(config, bandera)
    }
    valores = []
    for valor in activo.valores_atributos.all():
        config = configuraciones.get(valor.atributo_id)
        if config:
            valor._configuracion_actual = config
        if config and valor.vigente and valor.valor_formateado:
            valores.append((config, valor))
    return sorted(valores, key=lambda item: (item[0].orden, item[0].atributo.nombre))


def atributos_para_detalle(activo):
    """Lista configuraciones visibles con su valor vigente, si existe."""
    configuraciones = [
        config
        for config in configuraciones_para_tipo(activo.tipo_activo_id)
        if config.mostrar_detalle
    ]
    valores = {
        valor.atributo_id: valor
        for valor in activo.valores_atributos.all()
        if valor.vigente
    }
    resultado = []
    for configuracion in configuraciones:
        valor = valores.get(configuracion.atributo_id)
        if valor:
            valor._configuracion_actual = configuracion
        resultado.append((configuracion, valor))
    return resultado


def caracteristicas_para_acta(activo):
    partes = []
    for configuracion, valor in valores_visibles(activo, destino="actas"):
        partes.append(f"{configuracion.atributo.nombre}: {valor.valor_formateado}")
    return partes


def instantanea_activo(activo):
    return {
        "id": activo.pk,
        "codigo": activo.codigo,
        "tipo": activo.tipo_activo.nombre,
        "marca": activo.marca,
        "modelo": activo.modelo,
        "serie": activo.serie,
        "valor": str(activo.valor) if activo.valor is not None else None,
        "atributos": [
            {
                "clave": config.atributo.clave,
                "nombre": config.atributo.nombre,
                "valor": valor.valor_formateado,
                "orden": config.orden,
            }
            for config, valor in valores_visibles(activo, destino="actas")
        ],
    }
