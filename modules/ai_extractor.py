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


# ── VALIDACIÓN POR REGLAS (Opción B) ──────────────────────────────────────────
import re

def validar_rfc(rfc):
    """RFC mexicano: 4 letras + 6 dígitos (fecha) + 3 caracteres homoclave."""
    if not rfc:
        return False
    patron = r'^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}$'
    return bool(re.match(patron, rfc.strip().upper()))


def validar_fecha(fecha_str):
    """Espera formato DD/MM/YYYY."""
    if not fecha_str:
        return False
    patron = r'^\d{2}/\d{2}/\d{4}$'
    return bool(re.match(patron, fecha_str.strip()))


def validar_monto(valor):
    """Un monto debe ser numérico y no negativo para la mayoría de campos."""
    if valor is None:
        return False
    if isinstance(valor, (int, float)):
        return valor >= 0
    return False


def calcular_confianza_por_reglas(datos):
    """
    Revisa cada campo del JSON extraído y le asigna un nivel:
    'alta', 'media', 'baja'.
    Esto ocurre DESPUÉS de que la IA ya extrajo los datos.
    """
    confianza = {}

    # Campos de texto simples: si existen y no están vacíos, alta; si no, baja
    for campo in ["tipo_documento", "numero_documento", "metodo_pago"]:
        valor = datos.get(campo)
        confianza[campo] = "alta" if valor else "baja"

    # Fechas: validamos formato
    for campo in ["fecha_emision", "fecha_vencimiento"]:
        valor = datos.get(campo)
        if not valor:
            confianza[campo] = "baja"
        elif validar_fecha(valor):
            confianza[campo] = "alta"
        else:
            confianza[campo] = "media"  # existe pero formato raro

    # RFC del emisor y receptor
    emisor_rfc = datos.get("emisor", {}).get("rfc") if datos.get("emisor") else None
    if not emisor_rfc:
        confianza["emisor_rfc"] = "baja"
    elif validar_rfc(emisor_rfc):
        confianza["emisor_rfc"] = "alta"
    else:
        confianza["emisor_rfc"] = "media"

    # Nombres de emisor y receptor: alta si existen, baja si no
    emisor_nombre = datos.get("emisor", {}).get("nombre") if datos.get("emisor") else None
    confianza["emisor_nombre"] = "alta" if emisor_nombre else "baja"

    receptor_nombre = datos.get("receptor", {}).get("nombre") if datos.get("receptor") else None
    confianza["receptor_nombre"] = "alta" if receptor_nombre else "media"

    # Montos: subtotal, impuestos, total
    for campo in ["subtotal", "impuestos", "total"]:
        valor = datos.get(campo)
        if validar_monto(valor):
            confianza[campo] = "alta"
        elif valor is None:
            confianza[campo] = "baja"
        else:
            confianza[campo] = "media"

    # Validación cruzada: si subtotal + impuestos != total, bajamos confianza del total
    subtotal = datos.get("subtotal")
    impuestos = datos.get("impuestos")
    total = datos.get("total")
    if all(isinstance(v, (int, float)) for v in [subtotal, impuestos, total]):
        suma_esperada = round(subtotal + impuestos, 2)
        if abs(suma_esperada - round(total, 2)) > 1.0:  # tolerancia de 1 peso
            confianza["total"] = "media"
            confianza["subtotal"] = "media"

    # Items: si hay al menos uno con descripción e importe, alta
    items = datos.get("items") or []
    if items and all(it.get("descripcion") and it.get("importe") is not None for it in items):
        confianza["items"] = "alta"
    elif items:
        confianza["items"] = "media"
    else:
        confianza["items"] = "baja"

    return confianza


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
5. En "confianza_ia", evalúa honestamente qué tan clara estaba la información en el texto para el total, el RFC del emisor y la fecha de emisión. Si el texto es confuso o el dato no aparece explícitamente, marca "baja".
6. Para "categoria_gasto", elige EXACTAMENTE una de estas opciones según lo que se compró o pagó, basándote en la descripción de los items o el giro del emisor:
   - "Insumos y materiales"
   - "Servicios (luz, agua, internet, telefono)"
   - "Renta"
   - "Nomina y personal"
   - "Transporte y logistica"
   - "Mantenimiento y reparaciones"
   - "Marketing y publicidad"
   - "Equipo y tecnologia"
   - "Impuestos y tramites"
   - "Comida y representacion"
   - "Otro"
   Usa "Otro" solo si genuinamente no encaja en ninguna categoria anterior.
   7. Para cada item, extrae ademas "categoria_producto", "modelo_dispositivo" y "material_o_variante" analizando la descripcion original. Estos campos sirven para identificar si dos productos de facturas distintas son exactamente el mismo, incluso si la redaccion de la descripcion varia. Se especifico y consistente: usa siempre las mismas palabras clave en minusculas y con guion bajo para el mismo tipo de producto (ej: siempre "iphone_15", nunca a veces "iphone15" y otras veces "iphone_quince"). Si el documento no es de productos fisicos (ej: un recibo de servicio), usa null en estos tres campos.
"""

    estructura_base = """{
  "tipo_documento": "<tipo>",
  "emisor": {"nombre": null, "rfc": null, "direccion": null},
  "receptor": {"nombre": null, "rfc": null},
  "fecha_emision": "DD/MM/YYYY o null",
  "fecha_vencimiento": "DD/MM/YYYY o null",
  "numero_documento": null,
  "moneda": "MXN",
   "items": [{
    "descripcion": null,
    "cantidad": null,
    "precio_unitario": null,
    "importe": null,
    "categoria_producto": "categoria general del producto, ej: funda, cargador, audifonos, cable, protector_pantalla, bateria_externa, otro",
    "modelo_dispositivo": "modelo especifico si aplica, ej: iphone_15, samsung_s24, universal, o null si no aplica",
    "material_o_variante": "material o variante que afecta el precio, ej: silicon, cuero, transparente, metal, o null"
  }],
  "subtotal": null,
  "impuestos": null,
  "total": null,
  "metodo_pago": null,
  "categoria_gasto": "una de las categorias listadas abajo",
  "notas": null,
  "confianza_ia": {
    "total": "alta o media o baja segun que tan seguro estas de este campo",
    "emisor_rfc": "alta o media o baja",
    "fecha_emision": "alta o media o baja"
  }
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
    4. Combina la confianza reportada por la IA con la validacion por reglas
    """
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    tipo_detectado = detectar_tipo(texto_pdf)
    prompt = construir_prompt(texto_pdf, tipo_detectado)

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=2000,
        temperature=0.1
    )

    respuesta_texto = response.choices[0].message.content.strip()
    respuesta_texto = (respuesta_texto
        .replace("```json", "")
        .replace("```", "")
        .strip())

    try:
        datos = json.loads(respuesta_texto)
        datos["_tipo_detectado"] = tipo_detectado

        # Confianza por reglas (Opcion B) - la base, mas confiable
        confianza_reglas = calcular_confianza_por_reglas(datos)

        # Confianza reportada por la IA (Opcion A) - contexto adicional
        confianza_ia = datos.pop("confianza_ia", {}) or {}

        # Combinar: si la IA dice "baja" en algo que las reglas dijeron "alta",
        # bajamos a "media" como precaucion. Las reglas nunca se sobrescriben a "alta"
        # solo por lo que diga la IA.
        confianza_final = dict(confianza_reglas)
        for campo, nivel_ia in confianza_ia.items():
            if campo in confianza_final:
                nivel_regla = confianza_final[campo]
                if nivel_ia == "baja" and nivel_regla == "alta":
                    confianza_final[campo] = "media"

        datos["_confianza"] = confianza_final

        return {"exito": True, "datos": datos}
    except json.JSONDecodeError as e:
        return {
            "exito": False,
            "error": f"Error al parsear JSON: {str(e)}",
            "respuesta_cruda": respuesta_texto
        }


def construir_clave_producto(item):
    """
    Construye una clave de comparacion a partir de los atributos
    estructurados de un item. Dos items son "el mismo producto"
    solo si tienen la misma categoria, modelo y material/variante.
    El color se ignora a proposito porque normalmente no afecta el precio.
    """
    categoria = item.get("categoria_producto")
    modelo = item.get("modelo_dispositivo")
    variante = item.get("material_o_variante")

    if not categoria:
        return None

    partes = [categoria]
    if modelo:
        partes.append(modelo)
    if variante:
        partes.append(variante)

    return "|".join(partes)        