# -*- coding: utf-8 -*-
import os
from datetime import datetime

try:
    import gspread
    from google.oauth2.service_account import Credentials
    GSPREAD_DISPONIBLE = True
except ImportError:
    GSPREAD_DISPONIBLE = False

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

CREDENTIALS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "google_credentials.json"
)


def valor_simple(val):
    """Convierte cualquier valor a algo que Sheets pueda escribir."""
    if val is None:
        return 0
    if isinstance(val, (int, float)):
        return val
    if isinstance(val, dict):
        for v in val.values():
            if isinstance(v, (int, float)):
                return v
        return 0
    if isinstance(val, str):
        try:
            return float(val.replace(',', '').replace('$', ''))
        except Exception:
            return val
    return val


def credentials_disponibles():
    return GSPREAD_DISPONIBLE and os.path.exists(CREDENTIALS_PATH)


def get_client():
    creds = Credentials.from_service_account_file(CREDENTIALS_PATH, scopes=SCOPES)
    return gspread.authorize(creds)


def exportar_a_sheets(datos, filename, sheet_url=None):
    if not credentials_disponibles():
        raise Exception("Credenciales de Google no configuradas.")
    if not sheet_url:
        raise Exception("Debes proporcionar la URL de tu hoja de Google Sheets.")

    client = get_client()
    sh = client.open_by_url(sheet_url)

    nombre_tab = filename[:28]
    try:
        ws = sh.add_worksheet(title=nombre_tab, rows=200, cols=10)
    except Exception:
        ws = sh.add_worksheet(
            title=nombre_tab[:22] + f"_{datetime.now().strftime('%H%M')}",
            rows=200, cols=10
        )

    campos = [
        ["Campo",         "Valor"],
        ["Tipo",          datos.get("tipo_documento") or "—"],
        ["N Documento",   datos.get("numero_documento") or "—"],
        ["Fecha emision", datos.get("fecha_emision") or "—"],
        ["Emisor",        datos.get("emisor", {}).get("nombre") or "—"],
        ["RFC Emisor",    datos.get("emisor", {}).get("rfc") or "—"],
        ["Receptor",      datos.get("receptor", {}).get("nombre") or "—"],
        ["Moneda",        datos.get("moneda") or "MXN"],
        ["Subtotal",      valor_simple(datos.get("subtotal"))],
        ["Impuestos",     valor_simple(datos.get("impuestos"))],
        ["TOTAL",         valor_simple(datos.get("total"))],
    ]
    ws.update("A1", campos)

    items = datos.get("items") or []
    if items:
        encabezado = [["#", "Descripcion", "Cantidad", "Precio Unit.", "Importe"]]
        filas = [
            [
                i + 1,
                it.get("descripcion", ""),
                valor_simple(it.get("cantidad")),
                valor_simple(it.get("precio_unitario")),
                valor_simple(it.get("importe"))
            ]
            for i, it in enumerate(items)
        ]
        ws.update("A13", encabezado)
        ws.update("A14", filas)

    return {"url": sheet_url, "nombre": nombre_tab}


def exportar_lote_a_sheets(resultados, sheet_url=None, nombre_lote=None):
    if not credentials_disponibles():
        raise Exception("Credenciales de Google no configuradas.")
    if not sheet_url:
        raise Exception("Debes proporcionar la URL de tu hoja de Google Sheets.")

    client = get_client()
    sh = client.open_by_url(sheet_url)

    # Pestana resumen
    nombre_resumen = f"Resumen {datetime.now().strftime('%d/%m %H:%M')}"
    try:
        ws_resumen = sh.add_worksheet(title=nombre_resumen, rows=200, cols=10)
    except Exception:
        ws_resumen = sh.add_worksheet(
            title=f"Resumen_{datetime.now().strftime('%H%M')}",
            rows=200, cols=10
        )

    # Full header-level columns, mirroring the Excel "Resumen General" sheet
    encabezado_resumen = [[
        "#", "Archivo", "Tipo", "N° Documento", "Fecha Emisión",
        "Emisor", "RFC Emisor", "Receptor", "Subtotal", "Impuestos",
        "Total", "Moneda", "Método Pago"
    ]]
    ws_resumen.update("A1", encabezado_resumen)

    total_global = 0
    filas_resumen = []
    for i, r in enumerate(resultados):
        d = r.get("datos", {})
        total = valor_simple(d.get("total"))
        if isinstance(total, (int, float)):
            total_global += total

        # emisor/receptor can be missing or malformed in the AI response,
        # so default to an empty dict before reading nested fields
        emisor_dict = d.get("emisor") if isinstance(d.get("emisor"), dict) else {}
        receptor_dict = d.get("receptor") if isinstance(d.get("receptor"), dict) else {}

        filas_resumen.append([
            i + 1,
            r.get("filename", ""),
            d.get("tipo_documento") or "—",
            d.get("numero_documento") or "—",
            d.get("fecha_emision") or "—",
            emisor_dict.get("nombre") or "—",
            emisor_dict.get("rfc") or "—",
            receptor_dict.get("nombre") or "—",
            valor_simple(d.get("subtotal")),
            valor_simple(d.get("impuestos")),
            total,
            d.get("moneda") or "MXN",
            d.get("metodo_pago") or "—",
        ])

    if filas_resumen:
        ws_resumen.update("A2", filas_resumen)

    fila_total = len(filas_resumen) + 3
    ws_resumen.update(f"A{fila_total}", [["TOTAL GLOBAL", total_global]])

    # Pestana por documento
    for r in resultados:
        d = r.get("datos", {})
        nombre_tab = r.get("filename", "doc")[:26]
        try:
            ws = sh.add_worksheet(title=nombre_tab, rows=200, cols=10)
        except Exception:
            ws = sh.add_worksheet(
                title=nombre_tab[:20] + f"_{datetime.now().strftime('%H%M')}",
                rows=200, cols=10
            )

        emisor_nombre = "—"
        emisor_rfc = "—"
        receptor_nombre = "—"
        if d.get("emisor") and isinstance(d.get("emisor"), dict):
            emisor_nombre = d["emisor"].get("nombre") or "—"
            emisor_rfc = d["emisor"].get("rfc") or "—"
        if d.get("receptor") and isinstance(d.get("receptor"), dict):
            receptor_nombre = d["receptor"].get("nombre") or "—"

        campos = [
            ["Campo",         "Valor"],
            ["Tipo",          d.get("tipo_documento") or "—"],
            ["N Documento",   d.get("numero_documento") or "—"],
            ["Fecha emision", d.get("fecha_emision") or "—"],
            ["Emisor",        emisor_nombre],
            ["RFC Emisor",    emisor_rfc],
            ["Receptor",      receptor_nombre],
            ["Moneda",        d.get("moneda") or "MXN"],
            ["Subtotal",      valor_simple(d.get("subtotal"))],
            ["Impuestos",     valor_simple(d.get("impuestos"))],
            ["TOTAL",         valor_simple(d.get("total"))],
        ]
        ws.update("A1", campos)

        items = d.get("items") or []
        if items:
            ws.update("A13", [["#", "Descripcion", "Cantidad", "Precio Unit.", "Importe"]])
            ws.update("A14", [
                [
                    i + 1,
                    it.get("descripcion", ""),
                    valor_simple(it.get("cantidad")),
                    valor_simple(it.get("precio_unitario")),
                    valor_simple(it.get("importe"))
                ]
                for i, it in enumerate(items)
            ])

    return {"url": sheet_url, "nombre": nombre_resumen}


def exportar_lote_a_sheets_detallado(resultados: list[dict], sheet_url: str = None) -> dict:
    """
    Exports a batch of processed documents to Google Sheets as a
    product-level consolidated table: one row per product line item,
    repeating the parent invoice's header data on every row. Mirrors
    generar_excel_batch_detallado() but writes to Sheets instead of
    an .xlsx file.

    Args:
        resultados: list of dicts, each with "filename" and "datos"
            keys, where "datos" is the structured extraction result.
        sheet_url: URL of the user's own Google Sheet.

    Returns:
        Dict with "url" and "nombre" keys pointing to the created tab.

    Raises:
        Exception: if Google credentials are not configured, or if
            sheet_url is missing.
    """
    if not credentials_disponibles():
        raise Exception("Credenciales de Google no configuradas.")
    if not sheet_url:
        raise Exception("Debes proporcionar la URL de tu hoja de Google Sheets.")

    client = get_client()
    sh = client.open_by_url(sheet_url)

    nombre_tab = f"Detalle {datetime.now().strftime('%d/%m %H:%M')}"
    try:
        ws = sh.add_worksheet(title=nombre_tab, rows=1000, cols=20)
    except Exception:
        ws = sh.add_worksheet(
            title=f"Detalle_{datetime.now().strftime('%H%M')}",
            rows=1000, cols=20
        )

    encabezados = [
        "#", "Archivo", "Tipo", "N° Documento", "Fecha Emisión",
        "Emisor", "RFC Emisor", "Receptor", "Método Pago",
        "Descripción", "SKU", "Cantidad", "Precio Unitario", "Importe",
        "Subtotal Factura", "Impuestos Factura", "Total Factura", "Moneda"
    ]
    filas_completas = [encabezados]

    contador_linea = 1
    total_global = 0.0

    for resultado in resultados:
        d = resultado.get("datos", {})
        filename = resultado.get("filename", "")

        # emisor/receptor can be missing or malformed in the AI response,
        # so default to an empty dict before reading nested fields
        emisor_dict = d.get("emisor") if isinstance(d.get("emisor"), dict) else {}
        receptor_dict = d.get("receptor") if isinstance(d.get("receptor"), dict) else {}
        items = d.get("items") or []

        subtotal_doc = valor_simple(d.get("subtotal"))
        impuestos_doc = valor_simple(d.get("impuestos"))
        total_doc = valor_simple(d.get("total"))
        if isinstance(total_doc, (int, float)):
            total_global += total_doc

        # Header fields shared by this invoice, computed once and
        # repeated on every product row below
        cabecera = [
            filename,
            d.get("tipo_documento") or "—",
            d.get("numero_documento") or "—",
            d.get("fecha_emision") or "—",
            emisor_dict.get("nombre") or "—",
            emisor_dict.get("rfc") or "—",
            receptor_dict.get("nombre") or "—",
            d.get("metodo_pago") or "—",
        ]

        # If the AI found no items, still emit one row so the invoice
        # is not silently dropped from the consolidated view
        filas_producto = items if items else [{}]

        for item in filas_producto:
            fila = [
                contador_linea,
                *cabecera,
                item.get("descripcion", ""),
                item.get("sku") or "—",
                valor_simple(item.get("cantidad")),
                valor_simple(item.get("precio_unitario")),
                valor_simple(item.get("importe")),
                subtotal_doc,
                impuestos_doc,
                total_doc,
                d.get("moneda") or "MXN",
            ]
            filas_completas.append(fila)
            contador_linea += 1

    ws.update("A1", filas_completas)

    fila_total = len(filas_completas) + 2
    ws.update(f"A{fila_total}", [["TOTAL GLOBAL", total_global]])

    return {"url": sheet_url, "nombre": nombre_tab}    