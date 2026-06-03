from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter


EXPORT_HEADERS = [
    "Codigo",
    "Tipo de activo",
    "Empresa",
    "Marca",
    "Modelo",
    "Serie",
    "Codigo SAP",
    "CPU",
    "RAM",
    "Disco",
    "Sistema operativo",
    "Fecha de compra",
    "Valor de Compra",
    "Estado del activo",
    "Activo en inventario",
    "Observaciones",
    "Creado el",
    "Actualizado el",
]


def _activo_to_row(activo):
    return [
        activo.codigo,
        activo.tipo_activo.nombre if activo.tipo_activo_id else "",
        activo.empresa.nombre if activo.empresa_id else "",
        activo.marca,
        activo.modelo,
        activo.serie,
        activo.codigo_sap or "",
        activo.cpu,
        activo.ram,
        activo.disco,
        activo.sistema_operativo,
        activo.fecha_compra,
        activo.valor,
        activo.estado_activo.nombre if activo.estado_activo_id else "",
        "Si" if activo.activo else "No",
        activo.observaciones,
        activo.created_at.replace(tzinfo=None) if activo.created_at else None,
        activo.updated_at.replace(tzinfo=None) if activo.updated_at else None,
    ]


def build_activos_export_workbook(activos):
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Activos"
    worksheet.freeze_panes = "A2"
    worksheet.append(EXPORT_HEADERS)

    header_fill = PatternFill(fill_type="solid", fgColor="0F766E")
    header_font = Font(color="FFFFFF", bold=True)

    for cell in worksheet[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for activo in activos:
        worksheet.append(_activo_to_row(activo))

    for row in worksheet.iter_rows(min_row=2, max_row=worksheet.max_row):
        row[11].number_format = "dd/mm/yyyy"
        row[12].number_format = '#,##0.00'
        row[16].number_format = "dd/mm/yyyy hh:mm"
        row[17].number_format = "dd/mm/yyyy hh:mm"

    for index, header in enumerate(EXPORT_HEADERS, start=1):
        max_length = len(header)
        for cell in worksheet.iter_cols(min_col=index, max_col=index, min_row=2, max_row=worksheet.max_row):
            for inner_cell in cell:
                cell_value = "" if inner_cell.value is None else str(inner_cell.value)
                max_length = max(max_length, len(cell_value))
        worksheet.column_dimensions[get_column_letter(index)].width = min(max_length + 2, 28)

    worksheet.auto_filter.ref = worksheet.dimensions
    return workbook
