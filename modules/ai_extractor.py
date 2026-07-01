# -*- coding: utf-8 -*-
import os
import json
from groq import Groq


# ── DETECCIÓN DE TIPO POR PALABRAS CLAVE ──────────────────────────────────────
def detectar_tipo(texto):
    """
    Analiza el texto crudo del PDF y devuelve el tipo detectado.
    Esto ocurre ANTES de llamar a la IA, para darle contexto específico.
    """
    texto_lower = texto.lower()

    # CFDI mexicano
    if any(k in texto_lower for k in [
        "cfdi", "comprobante fiscal", "timbre fiscal", "uuid",
        "regimen fiscal", "uso de cfdi", "sat ", "receptor rfc"
    ]):
        return "cfdi"

    # Estado de cuenta bancario
    if any(k in texto_lower for k in [
        "estado de cuenta", "saldo anterior", "saldo final",
        "movimientos", "depositos", "retiros", "clabe",
        "numero de cuenta", "corte", "bbva", "banamex",
        "santander", "hsbc", "banorte", "scotiabank"
    ]):
        return "estado_cuenta"

    # Nómina
    if any(k in texto_lower for k in [
        "nomina", "nómina", "recibo de pago", "salario",
        "percepciones", "deducciones", "imss", "infonavit",
        "isr retenido", "sueldo", "quincena"
    ]):
        return "nomina"

    # Recibo de servicios
    if any(k in texto_lower for k in [
        "recibo", "servicio", "telmex", "telnor", "totalplay",
        "izzi", "megacable", "cfe ", "comision federal",
        "agua", "predial", "gas natural"
    ]):
        return "recibo_servicio"

    # Orden de compra / cotización
    if any(k in texto_lower for k in [
        "orden de compra", "purchase order", "cotizacion",
        "cotización", "presupuesto", "proforma", "quote"
    ]):
        return "orden_compra"

    # Factura genérica internacional
    if any(k in texto_lower for k in [
        "invoice", "bill to", "ship to", "payment terms",
        "due date", "amount due"
    ]):
        return "factura_internacional"

    return "documento_general"


# ── PROMPTS ESPECIALIZADOS POR TIPO ───────────────────────────────────────────
def construir_prompt(texto_pdf, tipo):
    """
    Devuelve un prompt optimizado según el tipo de documento detectado.
    Cada tipo tiene instrucciones específicas que mejoran la extracción.
    """

    base_instrucciones = """
INSTRUCCIONES CRÍTICAS:
1. Responde ÚNICAMENTE con un objeto JSON válido. Sin texto antes ni después.
2. Sin markdown, sin backticks, sin explicaciones.
3. Si un campo no existe, usa null.
4. Extrae TODOS los items o movimientos que encuentres.
"""

    estructura_base = """{
  "tipo_documento": "<tipo>",
  "emisor": {"nombre": null, "rfc": null, "direccion": null},
  "receptor": {"nombre": null, "rfc": null},
  "fecha_emision": "DD/MM/YYYY o null",
  "fecha_vencimiento": "DD/MM/YYYY o null",
  "numero_documento": null,
  "moneda": "MXN",
  "items": [{"descripcion": null, "cantidad": null, "precio_unitario": null, "importe": null}],
  "subtotal": null,
  "impuestos": null,
  "total": null,
  "metodo_pago": null,
  "notas": null
}"""

    if tipo == "cfdi":
        instrucciones_extra = """
DOCUMENTO TIPO: CFDI Mexicano
Campos prioritarios a extraer con precisión:
- UUID del timbre fiscal (ponlo en numero_documento)
- RFC del emisor y receptor (son obligatorios en CFDI)
- Régimen fiscal (ponlo en notas)
- Uso de CFDI (ponlo en notas junto al régimen)
- Forma de pago y método de pago SAT
- Todos los conceptos con clave SAT, descripción, cantidad, valor unitario e importe
- IVA trasladado separado del subtotal
"""
    elif tipo == "estado_cuenta":
        instrucciones_extra = """
DOCUMENTO TIPO: Estado de Cuenta Bancario
Campos prioritarios:
- Nombre del banco (emisor)
- Nombre del cuentahabiente (receptor)
- Número de cuenta o CLABE (numero_documento)
- Período del estado de cuenta (fecha_emision = inicio, fecha_vencimiento = fin)
- Saldo inicial y saldo final (ponlos en subtotal y total respectivamente)
- Lista de movimientos: cada cargo/abono es un item
  - descripcion = concepto del movimiento
  - importe = monto (negativo si es cargo, positivo si es abono)
- Total de cargos y total de abonos en notas
"""
    elif tipo == "nomina":
        instrucciones_extra = """
DOCUMENTO TIPO: Recibo de Nómina
Campos prioritarios:
- Empresa empleadora (emisor)
- Nombre del empleado (receptor)
- RFC de ambos
- Período de pago (fecha_emision = inicio período)
- Número de empleado o folio (numero_documento)
- Percepciones como items positivos (sueldo, bonos, horas extra)
- Deducciones como items negativos (ISR, IMSS, INFONAVIT)
- Total de percepciones en subtotal
- Total de deducciones en impuestos
- Neto a pagar en total
"""
    elif tipo == "recibo_servicio":
        instrucciones_extra = """
DOCUMENTO TIPO: Recibo de Servicio (luz, agua, teléfono, gas, etc.)
Campos prioritarios:
- Empresa prestadora del servicio (emisor)
- Nombre del cliente (receptor)
- Número de cuenta o contrato (numero_documento)
- Período de servicio en fecha_emision y fecha_vencimiento
- Desglose de servicios como items
- Fecha límite de pago en fecha_vencimiento
- Monto total a pagar en total
"""
    elif tipo == "orden_compra":
        instrucciones_extra = """
DOCUMENTO TIPO: Orden de Compra o Cotización
Campos prioritarios:
- Empresa que emite (emisor)
- Empresa o cliente receptor
- Número de orden o cotización (numero_documento)
- Fecha de emisión y fecha de vencimiento de la cotización
- Todos los productos/servicios cotizados como items con cantidad y precio unitario
- Condiciones de pago en notas
"""
    elif tipo == "factura_internacional":
        instrucciones_extra = """
DOCUMENTO TIPO: Factura Internacional (Invoice)
Campos prioritarios:
- Empresa vendedora (emisor) con dirección completa
- Empresa compradora (receptor)
- Invoice number (numero_documento)
- Invoice date y due date
- Todos los line items con quantity, unit price e amount
- Taxes separados del subtotal
- Currency (moneda) — puede ser USD, EUR u otra
- Payment terms en notas
"""
    else:
        instrucciones_extra = """
DOCUMENTO TIPO: Documento General
Extrae toda la información estructurada que puedas identificar.
"""

    prompt = f"""Eres un experto en extracción de datos de documentos financieros y fiscales mexicanos.

{instrucciones_extra}
{base_instrucciones}

TEXTO DEL DOCUMENTO:
{texto_pdf[:4000]}

ESTRUCTURA JSON REQUERIDA:
{estructura_base.replace('<tipo>', tipo)}"""

    return prompt


# ── FUNCIÓN PRINCIPAL ──────────────────────────────────────────────────────────
def extraer_datos(texto_pdf):
    """
    1. Detecta el tipo de documento por palabras clave
    2. Construye un prompt especializado para ese tipo
    3. Llama a Groq y parsea el JSON de respuesta
    """
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    # Paso 1: detectar tipo antes de llamar a la IA
    tipo_detectado = detectar_tipo(texto_pdf)

    # Paso 2: prompt especializado
    prompt = construir_prompt(texto_pdf, tipo_detectado)

    # Paso 3: llamar a Groq
    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=2000,
        temperature=0.1
    )

    respuesta_texto = response.choices[0].message.content.strip()

    # Limpiar posibles backticks residuales
    respuesta_texto = (respuesta_texto
        .replace("```json", "")
        .replace("```", "")
        .strip())

    try:
        datos = json.loads(respuesta_texto)
        # Agregar el tipo detectado localmente para confirmación
        datos["_tipo_detectado"] = tipo_detectado
        return {"exito": True, "datos": datos}
    except json.JSONDecodeError as e:
        return {
            "exito": False,
            "error": f"Error al parsear JSON: {str(e)}",
            "respuesta_cruda": respuesta_texto
        }