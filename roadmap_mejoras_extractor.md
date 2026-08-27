# Roadmap — 6 Mejoras Extractor PDF a Excel/Sheets con IA

Documento de referencia persistente. Este roadmap se actualiza marcando
bloques como completados conforme avanza el desarrollo. Si Claude pierde
contexto o hay riesgo de alucinación por conversación larga, este archivo
es la fuente de verdad.

**Contexto del proyecto:** Extractor de datos de PDFs/imágenes (facturas,
recibos, CFDIs) a Excel/Google Sheets usando Groq + LLaMA 3.1. Stack:
Flask, Firestore (migrado desde SQLite), pdfplumber, openpyxl, gspread.
Repo: extractor-pdf-excel. Deploy: Google Cloud Run.

**Regla de trabajo acordada:** ejecutar bloque por bloque, con
supervisión humana en cada paso. Si un bloque tiene varios pasos
livianos, se ejecutan juntos; si un paso individual es pesado en
código, se separa y se avisa explícitamente.

---

## FASE 1 — Extracción y estructura de datos (SKU + corrección IVA)

### Bloque 17 — ✅ COMPLETADO
**Archivo:** `modules/ai_extractor.py`
**Qué se hizo:**
- Se agregó el campo `sku` a la estructura JSON de cada item extraído
  (código de producto, SKU o código de barras, `null` si no aparece).
- Se agregó instrucción explícita al prompt: el campo `impuestos` debe
  capturar IVA/ISR/IEPS/retenciones aunque el documento no use
  literalmente la palabra "impuesto" (muy común en CFDIs mexicanos que
  solo dicen "IVA 16%").
- Decisión: el SKU NO lleva nivel de confianza en
  `calcular_confianza_por_reglas()` — no es campo crítico de validación
  cruzada, y el proyecto no es un sistema de control de inventario.

### Bloque 18 — SKU visible en TODO el pipeline (no solo Excel)
**Corrección importante:** el Bloque 18 original solo tocó el Excel
individual. El usuario aclaró que el SKU debe aparecer en:
1. El preview editable en HTML (modo individual)
2. La vista batch en HTML (preview + modal de edición)
3. El Excel individual
4. El Excel batch
5. Google Sheets (individual y batch)

Sub-bloques:
- **18a — ✅ COMPLETADO**: Excel individual (`excel_generator.py`,
  función `generar_excel()`). Columna SKU agregada a la tabla de items,
  anchos de columna reajustados, formato monetario reindexado a las
  nuevas posiciones de columna.
- **18b — ✅ COMPLETADO**: preview editable HTML modo individual.
  Archivo: `templates/index.html` (extractor PDF), función
  `renderSingle()` y `crearFilaItem()`. Agregar columna SKU editable
  (`<input class="cell-edit item-sku">`) en la tabla de items del
  preview, y agregar `sku` a `leerDatosEditados()` para que se incluya
  al descargar.
- **18c — ✅ COMPLETADO**: vista batch en HTML — tanto la tabla de
  preview normal como el modal de edición por documento
  (`crearFilaModal()`, `abrirModal()`, `guardarModal()`). Mismo
  tratamiento que 18b pero en el flujo de lote.
- **18d — Se resuelve dentro de la Fase 2** (Bloque 19b), porque el
  SKU en el batch vive naturalmente en la vista "por producto".

---

## FASE 2 — Resumen General completo del batch (Excel y Sheets)

**Contexto de la decisión:** el usuario señaló que el "Resumen General"
actual del batch solo trae: archivo, tipo, n° documento, emisor, fecha,
total, moneda — y para ver el resto (RFC, receptor, subtotal, impuestos,
método de pago) hay que entrar hoja por hoja, documento por documento.
Esto no cumple el objetivo de "una tabla lista para mandar al contador".

**Decisión de diseño (Opción A vs B):**
- Opción A = una fila por factura (resumen alto nivel)
- Opción B = una fila por línea de producto, repitiendo cabecera
  (detalle completo, permite filtrar/sumar por SKU o categoría)
- **Se implementan AMBAS**, con selector de modalidad en frontend.
  Recomendación de Claude adoptada: Opción B es el modo por defecto
  porque cumple el objetivo original de "una lista vertical lista para
  filtrar y enviar al contador"; Opción A queda como vista alterna
  rápida.

**Columnas requeridas en ambas modalidades (nivel factura/cabecera):**
tipo de documento, n° documento, fecha de emisión, emisor, RFC emisor,
receptor, subtotal, impuestos, total, moneda, método de pago.

**Columna adicional solo en modalidad detalle (Opción B):**
SKU, descripción del producto, cantidad, precio unitario, importe (por
línea de producto).

### Bloque 19a — ✅ COMPLETADO
**Archivo:** `modules/excel_generator.py`
**Qué hace:** modificar `generar_excel_batch()` (modalidad "por
factura", Opción A) para que la hoja "Resumen General" incluya todas
las columnas de cabecera listadas arriba (actualmente solo trae
archivo, tipo, n° documento, emisor, fecha, total, moneda).

### Bloque 19b — ✅ COMPLETADO
**Archivo:** `modules/excel_generator.py`
**Qué hace:** función NUEVA `generar_excel_batch_detallado()`
(modalidad "por producto", Opción B). Una fila por línea de producto,
repitiendo en cada fila los datos de cabecera de su factura de origen,
más las columnas propias del producto (SKU, descripción, cantidad,
precio unitario, importe).

### Bloque 20a — ✅ COMPLETADO
**Archivo:** `modules/sheets_exporter.py`
**Qué hace:** aplicar el mismo tratamiento del Bloque 19a a
`exportar_lote_a_sheets()` — modalidad "por factura" con columnas
completas.

### Bloque 20b — ✅ COMPLETADO
**Archivo:** `modules/sheets_exporter.py`
**Qué hace:** función nueva equivalente a 19b pero para Google Sheets —
modalidad "por producto" con SKU.

### Bloque 20c — ✅ COMPLETADO
**Archivo:** `templates/index.html` (sección modo batch)
**Qué hace:** agregar selector de modalidad (botón o dropdown: "Vista
por producto" / "Vista por factura") antes de los botones de descargar
Excel / exportar a Sheets, y conectar la selección con las funciones
correspondientes (19a/19b para Excel, 20a/20b para Sheets).

---

## FASE 3 — Bug fix: exportar a Sheets roto

### Bloque 21 — ✅ COMPLETADO
**Archivo:** `templates/index.html`, función `exportarSheetsSingle()`
**Error detectado:**
```
Uncaught (in promise) ReferenceError: Cannot access 'SHEET_URL' before initialization
at exportarSheetsSingle ((index):1414:5)
```
**Causa probable:** variable `SHEET_URL` declarada con `const` DESPUÉS
de ser usada dentro de la misma función (temporal dead zone de
JavaScript). Revisar también `exportarSheetsBatch()` por el mismo
patrón, ya que ambas funciones históricamente compartieron la misma
estructura de código.

---

## FASE 4 — Reportes consolidados por rango de tiempo

Rangos requeridos: semanal (7 días), quincenal (15 días), mensual (30
días), bimestral (60 días). Exportable a Excel o Google Sheets.

### Bloque 22 — ✅ COMPLETADO
**Archivo:** `modules/firestore_db.py`
**Qué hace:** los documentos de historial actualmente guardan `fecha`
como string `dd/mm/yyyy HH:MM`, útil para mostrar pero no para
comparar rangos de forma confiable. Agregar también un campo
`fecha_timestamp` (Firestore Timestamp / Python datetime) en
`guardar_extraccion()` y `guardar_lote()`, sin quitar el campo de texto
existente (no rompe nada de lo que ya funciona).

### Bloque 23 — ✅ COMPLETADO
**Archivo:** `modules/firestore_db.py`
**Qué hace:** nueva función `obtener_historial_por_rango(dias)` que
filtra documentos de historial cuya `fecha_timestamp` esté dentro de
los últimos N días, reutilizando el patrón de agregación en Python que
ya se usa en `obtener_metricas()`.

### Bloque 24 — ✅ COMPLETADO
**Archivos:** `app.py` (ruta nueva), `templates/index.html` (botones)
**Qué hace:** ruta Flask que reciba el rango deseado y devuelva el
Excel/Sheets consolidado del período, más los botones/selector en el
frontend (Semanal / Quincenal / Mensual / Bimestral).

---

## FASE 5 — Resiliencia del LLM

### Bloque 25 — ✅ COMPLETADO
**Archivo:** `modules/ai_extractor.py`
**Qué hace:** envolver la llamada actual a Groq con reintentos y
backoff exponencial: hasta 3 intentos ante error de red, 5xx o 429,
con espera progresiva entre intentos antes de fallar definitivamente.

### Bloque 26 — ✅ COMPLETADO
**Archivo:** `modules/ai_extractor.py`, `app.py`
**Qué hace:** clasificar errores específicos (PDF corrupto, timeout de
API, JSON malformado devuelto por la IA) y devolver mensajes claros y
estructurados al frontend en vez de un 500 genérico.

### Bloque 26 — fix adicional post-implementación
**Contexto:** al probar el Bloque 26 en el navegador, aparecieron
errores 500 no controlados. Diagnóstico reveló dos bugs de código
reales en `modules/ai_extractor.py`, dentro de `extraer_datos()`:
1. La línea `respuesta_texto = response.choices[0].message.content...`
   había quedado pegada al `}` de cierre del `return` del bloque
   `except`, y mal indentada dentro de ese mismo bloque — nunca se
   ejecutaba en el camino exitoso, causando `NameError`/
   `UnboundLocalError` en cada extracción.
2. En el bloque `except json.JSONDecodeError`, se llamaba a
   `_clasificar_error_extraccion()` pero el resultado (`clasificacion`)
   nunca se usaba — el `return` seguía devolviendo el mensaje genérico
   viejo en vez del mensaje clasificado.
Ambos corregidos y confirmados funcionando.

### Bloque 26.5 — Migración de modelo Groq (llama-3.1-8b-instant → openai/gpt-oss-20b)
**Contexto:** Groq deprecó sus modelos de chat Llama (incluyendo
`llama-3.1-8b-instant`, usado en este proyecto). Causaba error
`groq.NotFoundError: 404 model_not_found` en cada extracción — la
causa real detrás de una serie de errores 500/`error_desconocido_ia`
que parecían ser bugs de código.
**Solución:** modelo actualizado a `openai/gpt-oss-20b` (modelo de
pesos abiertos servido por la infraestructura de Groq, misma API key
gratuita, sin cambios de cuenta ni de `.env`).
**Archivo modificado:** `modules/ai_extractor.py`, dentro de
`_llamar_groq_con_reintentos()` — único lugar donde el nombre del
modelo estaba centralizado en este proyecto.
**⚠️ Impacto en otros proyectos del stack (misma API key):**
- `Analizador de Reportes con IA` → `modules/ai_engine.py` — **pendiente de aplicar el mismo cambio**
- `Agente de Ventas IA (GO4MORE)` → `agente.py` y `app.py` de ese
  proyecto — **pendiente de aplicar el mismo cambio**

### Bloque 26b — ✅ COMPLETADO
**Archivos:** `requirements.txt`, `modules/image_reader.py`,
`modules/xml_reader.py` (nuevo), `app.py`, `templates/index.html`
**Qué se hizo:**
- Se agregó soporte para HEIC/HEIF (fotos de iPhone), TIFF (escáneres
  de oficina), BMP, WEBP — mismo pipeline que JPG/PNG (Pillow + OCR
  Tesseract), vía `pillow-heif` para el registro de HEIC.
- Se creó `modules/xml_reader.py`, lector nuevo para CFDIs XML del
  SAT — aplana tags y atributos a texto plano (los CFDIs guardan la
  mayoría de sus datos como atributos XML, no como texto entre tags),
  sin pasar por OCR ya que es texto estructurado nativo.
- **Bug corregido:** el filtro de `/extract/batch` en `app.py` solo
  aceptaba archivos `.pdf`, descartando silenciosamente cualquier
  imagen o XML subido en modo lote aunque el frontend ya los
  permitiera seleccionar. Ahora usa `allowed_file()`, la misma
  validación que el modo individual — el lote ya admite mezclar
  PDF + imágenes + XML en una sola subida.
- Formato final soportado: PDF, JPG, JPEG, PNG, HEIC, HEIF, TIFF, TIF,
  BMP, WEBP, XML.

**Fuera de alcance (decisión explícita):** DOCX y XLSX/XLS quedan
fuera de este roadmap. Motivo: el pipeline actual asume que el
documento de entrada tiene la estructura de una factura/comprobante;
un DOCX o XLSX genérico (contrato, reporte, catálogo) no garantiza esa
estructura, y forzarlo por el mismo prompt de extracción de facturas
generaría datos "estructurados" pero potencialmente inventados, con
apariencia de confianza alta — peor que rechazar el archivo. Si se
retoma en el futuro, requiere su propio prompt especializado y su
propia lógica de lectura (`python-docx` / `openpyxl` en modo lectura),
no es una extensión de `ALLOWED_EXTENSIONS`.

### Bloque 27 — ✅ COMPLETADO (bug arrastrado de la migración a Firestore)
**Archivo:** `modules/firestore_db.py`,
función `buscar_precios_historicos_producto()`
**Contexto:** la alerta de cambio de precio (⚠️) dejó de dispararse
después de la migración de SQLite a Firestore. Se probó con
`generar_facturas_prueba.py` (factura 1 con precio base, factura 2 con
+30% de aumento simulado) y no aparece la alerta esperada. Sospecha
inicial: comparación de campos o tipos de dato distinta a la que tenía
la versión SQLite original. Pendiente de diagnóstico antes de corregir.

---


## FASE 6 — Fallback de proveedor de IA + Observabilidad

**Decisión estratégica ya tomada:** NO se integra LiteLLM ni
OpenRouter. Justificación: actualmente solo existe un punto de llamada
al LLM (`ai_extractor.py`, con Groq). Una librería de gateway agrega
complejidad y una dependencia nueva para un problema que se resuelve
con una función propia de ~40 líneas. Se reevaluará esta decisión si en
el futuro (ej. Proyecto 8, voz en tiempo real) existen 3+ puntos de
llamada a LLMs con necesidades distintas.

### Bloque 28 — ✅ COMPLETADO
**Archivo:** `modules/ai_extractor.py`
**Qué hace:** función propia de fallback — si el proveedor principal
(Groq) falla o excede rate limit después de los reintentos del Bloque
25, intentar automáticamente con un segundo proveedor configurado por
variable de entorno.

### Bloque 28 — ✅ COMPLETADO
**Archivos:** `modules/ai_extractor.py`, `requirements.txt`, `.env`
**Qué se hizo:**
- Se agregó fallback automático a Google Gemini cuando Groq falla.
  Proveedor elegido por decisión explícita: Gemini (capa gratuita,
  ya integrado en el stack vía GCP), sobre otra cuenta de Groq (no
  protege ante caída del proveedor completo) y sobre dejarlo sin
  configurar (se prefirió resiliencia real de una vez).
- SDK usado: `google-genai` (el nuevo) — se descartó
  `google-generativeai` por estar deprecado segun aviso oficial del
  propio paquete.
- Modelo elegido: `gemini-flash-latest` — alias que Google mantiene
  apuntando siempre al Flash estable mas reciente, evitando fijar una
  version especifica que eventualmente se deprecara (mismo problema
  que ya vivimos con `llama-3.1-8b-instant` en Groq).
- Clase `_RespuestaSimulada` normaliza la respuesta de Gemini
  (`response.text`) al mismo formato que usa Groq
  (`response.choices[0].message.content`), para que `extraer_datos()`
  no necesite saber cual proveedor respondio.
- **Decisión de diseño clave:** el fallback se dispara tanto en
  errores transitorios de Groq (rate limit, timeout, 5xx) como en
  errores de autenticacion (401/403) — se cambio el `raise` original
  por `break` dentro del ciclo de reintentos, para que el flujo
  siempre llegue al bloque de fallback sin importar el tipo de error,
  maximizando disponibilidad del sistema.
- Si Gemini también falla, se propaga el error original de Groq (no
  el de Gemini), para que `_clasificar_error_extraccion()` lo
  reconozca correctamente.
- Probado end-to-end con prompt real de produccion (no solo prueba
  aislada de mecanica): con key de Groq invalida a proposito, el
  fallback extrajo correctamente RFC, totales, items y categorizacion
  de un documento de prueba via Gemini, en formato JSON estricto sin
  markdown ni texto extra.

### Bloque 28.5 — Selección de proveedor de IA (admin + usuario final)
**Motivo:** además de preparar el terreno para una futura API de pago
(ver Bloque 28), el usuario final debe poder elegir entre los
proveedores ya disponibles (Groq / Gemini) — con una preferencia
guardada por default y la posibilidad de cambiarla puntualmente en
cada extracción. Se divide en 4 sub-bloques para mantener cada cambio
pequeño y verificable, tras el aprendizaje del Bloque 26 (los cambios
grandes de una sola vez son mas dificiles de depurar).

**Prioridad de resolución (mas especifico gana):**
selector en esa extraccion puntual > preferencia guardada del usuario
> `PROVEEDOR_IA_PRINCIPAL` en `.env` (default global del sistema).

- **28.5a — ✅ COMPLETADO**: extraer `_llamar_groq_con_reintentos()`,
  `_llamar_gemini_fallback()` y `_RespuestaSimulada` de
  `ai_extractor.py` hacia módulo nuevo `modules/ai_provider.py`
  (agnóstico de dominio — no sabe nada de facturas/PDFs). Nueva
  variable `PROVEEDOR_IA_PRINCIPAL=groq` en `.env`. `ai_extractor.py`
  importa desde el módulo nuevo. Sin cambios de comportamiento, solo
  reorganización.
- **28.5b — ✅ COMPLETADO**: la función despachadora en
  `ai_provider.py` acepta parámetro opcional `proveedor_forzado`.
  `extraer_datos()` en `ai_extractor.py` puede recibir y pasar ese
  parámetro hacia abajo. Backend listo para recibir la elección, sin
  tocar frontend ni Firestore todavía.
- **28.5c — ✅ COMPLETADO**: campo nuevo `proveedor_ia_preferido` en
  el documento de usuario en Firestore (mismo patrón que `sheet_url`).
  Nueva función en `firestore_db.py` para guardar/leer la preferencia.
  Ruta nueva `/perfil/proveedor-ia` en `app.py` (mismo patrón que
  `/perfil/sheet-url`).
- **28.5d — ✅ COMPLETADO**: selector visual en `templates/index.html`
  — botón "☰ Modelo de IA" (ícono de hamburguesa + texto, para que el
  usuario sepa qué hace antes de abrirlo) que despliega horizontalmente
  las opciones Groq/Gemini, con la opción activa resaltada (default:
  preferencia guardada del usuario, o si no tiene, el default global).
  Conectado a `/extract` y `/extract/batch` para mandar el override
  cuando el usuario lo elija explícitamente.

### Bloque 29 — captura de métricas del LLM
**Archivo:** `modules/ai_provider.py` (no `ai_extractor.py` —
la lógica de llamadas a proveedores vive ahí desde el Bloque 28.5),
`modules/firestore_db.py` 
**Qué hace:** captura por cada llamada a IA (desde el módulo
compartido, cubriendo tanto Groq como el fallback de Gemini): latencia
total, conteo de tokens de entrada/salida (expuestos en
`response.usage` para Groq; pendiente confirmar el equivalente exacto
en la respuesta de Gemini), y estimación de costo en USD/MXN según
tarifa del modelo. Guardado en Firestore — extender el documento de
historial o colección nueva `metricas_llm`, decidir según qué tan
pesado resulte para las lecturas normales del historial.

### Bloque 30 — Sin cambios respecto al plan original
**Archivos:** `templates/dashboard.html`, `app.py` (ruta `/dashboard`)
**Qué hace:** mostrar las métricas del Bloque 29 en el dashboard —
latencia promedio, tokens totales consumidos, costo acumulado
estimado, tasa de éxito/error de extracciones, y qué proporción de
llamadas usó el proveedor principal vs el fallback.

---

## Pendientes cosméticos (no bloquean nada)

- Borrar el usuario `prueba_firestore` que quedó de una prueba manual
  durante la migración a Firestore (colección `usuarios` en Firestore).

### Pendiente cosmético — Alerta de precio más visible
**Archivo:** `templates/index.html`, función `crearFilaItem()` (y su
equivalente en el modal de lote, `crearFilaModal()`)
**Qué hace:** hoy la alerta (⚠️) de cambio de precio solo se ve como
tooltip al pasar el mouse encima — fácil de pasar por alto. Cambiar a:
- Ícono ⚠️ + texto visible del porcentaje (ej. "⚠️ +30%") junto a la
  descripción del producto, no solo en el `title`.
- Fondo naranja sutil en esa celda/indicador para que resalte a
  simple vista sin necesidad de hover.
**Explícitamente fuera de alcance:** no tocar `categoria_producto`,
`variante_especifica`, `material_o_marca` ni su nivel de detalle — el
usuario los necesita completos y descriptivos tal como están (permiten
diferenciar, por ejemplo, la misma funda de teléfono por color o
material). Este cambio es solo visual, en la presentación de la
alerta, no en los datos ni en su granularidad.
---
#### Pendiente cosmetico  — Rediseño de UI/UX (paleta + dashboard)
**Contexto:** revisión visual tras completar el Bloque 28.5. Decisiones
de diseño ya tomadas con el usuario, listas para implementar cuando
se retome. Se divide en 4 sub-bloques para verificar cada uno por
separado, siguiendo el mismo criterio usado en bloques anteriores.

**Paleta de colores — decisiones finales:**
- Cian (`#00BCD4`): se mantiene como color de marca principal
  (titulo, drop-zone, acentos generales). Sin cambios.
- Verde (`#4CAF50`): se mantiene como "accion positiva" (Guardar,
  Extraer, exportar exitoso). Sin cambios.
- Morado (nuevo, tono por definir en implementacion): reemplaza el
  naranja actual. Aplica a: badge "Admin", boton "Ver historial", y
  todos los botones de navegacion encapsulados nuevos (ver tabla).
- Rojo (`#EF5350`, ya existente para errores): tambien para el boton
  "Cerrar sesion" en todas las pantallas, para reforzar su semantica
  de "accion de salida/precaucion".

**Botones a encapsular — TODOS los botones de navegacion del proyecto,
en las 3 pantallas, deben tener el mismo tratamiento visual que el
badge "Admin" actual (capsula con borde/fondo de color), no solo texto
con hover como estan Dashboard/Cerrar sesion hoy:**

| Pantalla | Botones a encapsular |
|---|---|
| `templates/index.html` | Admin (ya existe, cambia naranja→morado) · Dashboard (nuevo, morado) · Cerrar sesion (nuevo, rojo) |
| `templates/dashboard.html` | Dashboard (nuevo, morado) · Extractor (nuevo, morado) |
| `templates/admin.html` | Extractor (nuevo, morado) · Dashboard (nuevo, morado) · Cerrar sesion (nuevo, rojo) |

**Sub-bloques:**
- **UI-1 — 🔲 PENDIENTE**: nav encapsulado completo en las 3 pantallas
  (tabla de arriba), badge Admin de naranja a morado.
- **UI-2 — 🔲 PENDIENTE**: boton "Ver historial" (en `index.html`) a
  morado, mismo tratamiento que el resto de acentos morados nuevos.
- **UI-3 — 🔲 PENDIENTE**: rediseño de tarjetas de metricas en
  `dashboard.html` con gradiente morado fuerte, inspirado en
  referencias visuales aprobadas por el usuario (tarjetas tipo "Total
  Finance / Total Expense" con donut de progreso integrado). Mejor
  aprovechamiento del espacio horizontal — hoy hay mucho espacio negro
  vacio a la derecha de las graficas. Cambio mas grande de los 4,
  trabajar por separado del resto.
- **UI-4 — 🔲 PENDIENTE**: los campos "Mi Google Sheets" y "Proveedor
  de IA preferido" en el nav de `index.html` pasan de tamaño fijo a
  desplegables horizontales — solo el label visible por default, clic
  para expandir selector + boton guardar (mismo patron que el selector
  "☰ Modelo de IA" ya implementado en el Bloque 28.5d).

**Pendiente de definir en el momento de implementar:**
- Tono exacto del morado (no se fijo un hex especifico todavia).
- Diseño del icono/badge de "Admin" en si — el usuario buscara
  referencias visuales antes de ese sub-bloque.

**Prioridad:** cosmetico, no bloquea funcionalidad. Se retoma despues
de cerrar los bloques pendientes de la Fase 6 (Bloque 29 y 30).


### Pendiente funcional — Actualizar version de Python
**Contexto:** en cada arranque de `app.py`, aparece el aviso:
`FutureWarning: You are using a Python version (3.10.20) which Google
will stop supporting in new releases of google.api_core once it
reaches its end of life (2026-10-04). Please upgrade to the latest
Python version, or at least Python 3.11...`
**Qué hace:** no afecta el funcionamiento actual — es una advertencia,
no un error — pero Google dejara de dar soporte a `google.api_core`
para Python 3.10 a partir de esa fecha, lo cual eventualmente
afectaria las dependencias de Firestore (`google.cloud.firestore`).
**Alcance del cambio:** requiere recrear el entorno Conda con Python
3.11+ (`conda create --name extractor_pdf-env python=3.11 -y`, segun
la regla de Anaconda del proyecto), reinstalar todas las dependencias
de `requirements.txt`, y volver a probar el pipeline completo
(extraccion individual, lote, Firestore, exportacion a Sheets/Excel)
antes de dar el cambio por cerrado — no es un cambio de una sola
linea, es una migracion de entorno completa.
**Prioridad:** baja — no bloquea nada hoy. Vale la pena hacerlo antes
de la fecha limite (04/10/2026) mencionada en el propio aviso, no
como emergencia.

## Cómo usar este documento

Cuando se retome el desarrollo, revisar este archivo primero para saber
exactamente en qué bloque se quedó el trabajo, qué decisiones de diseño
ya se tomaron (para no volver a discutirlas desde cero), y qué archivos
específicos toca cada bloque. Marcar cada bloque como ✅ COMPLETADO
conforme se cierre y se pruebe.
