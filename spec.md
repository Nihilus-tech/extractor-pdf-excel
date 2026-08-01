# SPEC.md — Extractor de Datos PDF/Imagen a Excel/Google Sheets con IA

Documento de referencia técnica del estado ACTUAL del proyecto. A
diferencia de `roadmap_mejoras_extractor.md` (que documenta las 6
mejoras en curso, bloque por bloque), este archivo documenta cómo
está construido el sistema HOY, de punta a punta.

Si Claude o el desarrollador retoman este proyecto después de una
pausa, o si una sesión nueva de Claude necesita entender el sistema
sin releer toda la conversación, este es el documento que se lee
primero. El README.md del repositorio está desactualizado (todavía
describe SQLite y Railway) — este spec.md es la fuente de verdad.

---

## 1. Qué hace el proyecto

Aplicación web que permite a pequeños negocios (tiendas de abarrotes,
celulares, accesorios) subir facturas, recibos o CFDIs en PDF/imagen y
obtener los datos estructurados automáticamente, con revisión humana
editable antes de exportar a Excel o Google Sheets.

Target de usuario: dueños de comercio sin conocimientos contables
profundos, que necesitan mandarle datos limpios a su contador sin
capturar manualmente cada factura.

---

## 2. Stack tecnológico real (actualizado)

| Capa | Tecnología | Notas |
|---|---|---|
| Backend | Python 3.10 + Flask | |
| IA / extracción | Groq API + LLaMA 3.1 8B Instant | Único proveedor de LLM por ahora (ver sección 8) |
| Lectura de PDF | pdfplumber | |
| Lectura de imágenes | pytesseract + Pillow | OCR, español |
| Generación Excel | openpyxl | |
| Google Sheets | gspread + google-auth | Requiere `google_credentials.json` (no versionado) |
| Auth | Flask-Login + Flask-Bcrypt | |
| **Base de datos** | **Google Firestore (modo nativo)** | Migrado desde SQLite. Ver sección 5. |
| Frontend | HTML + CSS + JavaScript vanilla | Sin framework, todo en `templates/index.html` |
| Gráficas | Chart.js (CDN) | |
| Deploy | **Google Cloud Run** | Migrado desde Railway (Procfile del repo es residual, ya no se usa) |
| Proyecto GCP | `extractor-pdf-20` | Separado del proyecto `clasificador-leads` (Lead Classifier), misma cuenta de Google |

**Nota sobre el repo público:** el README.md, Procfile y la sección
"Base de datos: SQLite" del repositorio en GitHub están desactualizados
— documentan el estado anterior a la migración de Firestore. Pendiente
de actualizar el README como tarea de limpieza, no bloquea desarrollo.

---

## 3. Estructura de archivos (estado actual real)

```
extractor-pdf-excel/
│
├── app.py                        # Rutas Flask, auth, todas las integraciones
├── requirements.txt              # google-cloud-firestore agregado
├── Dockerfile                    # Deploy a Cloud Run
├── .dockerignore
├── .gitignore
├── test_firestore.py             # Script de prueba manual (no parte de la app)
├── generar_facturas_prueba.py    # Script para generar PDFs sintéticos de prueba
│                                    (usado para probar alertas de cambio de precio)
│
├── modules/
│   ├── pdf_reader.py              # Extracción de texto con pdfplumber
│   ├── image_reader.py            # OCR con pytesseract (detecta Windows/Linux)
│   ├── ai_extractor.py            # Detección de tipo + extracción con Groq
│   ├── excel_generator.py         # Generación de .xlsx con openpyxl
│   ├── sheets_exporter.py         # Exportación a Google Sheets
│   └── firestore_db.py            # ⚠️ REEMPLAZA a db_historial.py (SQLite, eliminado)
│                                    Historial + sistema de usuarios, todo en Firestore
│
├── templates/
│   ├── index.html                 # Interfaz principal (extractor + historial + batch)
│   ├── login.html
│   ├── dashboard.html             # Dashboard de métricas
│   └── admin.html                 # Panel de administración
│
├── screenshots/                   # Capturas para el README (desactualizadas)
├── uploads/                       # PDFs subidos temporalmente (ignorado por git)
│
├── Procfile                       # RESIDUAL — de cuando se planeaba usar Railway.
│                                    Ya no se usa, el deploy es Cloud Run vía Dockerfile.
```

**Archivo eliminado:** `modules/db_historial.py` (SQLite) — reemplazado
completamente por `modules/firestore_db.py`. Ya no existe en el repo.

---

## 4. Variables de entorno requeridas

```env
GROQ_API_KEY=...
SECRET_KEY=...
UPLOAD_FOLDER=uploads
FIRESTORE_DATABASE_ID=extractor-pdf-2-0
```

**Detalle importante sobre `FIRESTORE_DATABASE_ID`:** la base de datos
Firestore de este proyecto NO se llama `(default)` — se creó con el ID
personalizado `extractor-pdf-2-0`. El cliente de Python
(`firestore.Client()`) necesita este id explícito o falla con
`404 The database (default) does not exist`. Si se recrea el proyecto
desde cero alguna vez, considerar usar el nombre `(default)` para
evitar tener que pasar esta variable.

**Autenticación con GCP:**
- En local: `gcloud auth application-default login` (una vez por máquina)
- En Cloud Run: automática, vía cuenta de servicio del proyecto
  (`...-compute@developer.gserviceaccount.com`), con rol *Cloud
  Datastore User* sobre Firestore

---

## 5. Base de datos: Firestore (migrado desde SQLite)

### Por qué se migró
SQLite vivía como archivo local dentro del contenedor de Cloud Run.
Cloud Run destruye el sistema de archivos del contenedor en cada
reinicio (inactividad, nuevo deploy, etc.) — cualquier usuario o
historial creado se perdía sin aviso. Firestore es la base de datos
gestionada elegida sobre Cloud SQL porque: (a) el desarrollador ya
tenía experiencia con Firestore en otro proyecto (Lead Classifier),
(b) la estructura de datos es de documentos sueltos sin relaciones
complejas — encaja natural sin necesitar SQL, (c) capa gratuita más
generosa para este volumen de uso, (d) cero administración de servidor.

### Colecciones

**`usuarios`**
```
id (autogenerado, string)
username: string
password_hash: string
rol: "admin" | "usuario"
creado_en: string "dd/mm/yyyy HH:MM"
sheet_url: string (URL de Google Sheets propia del usuario, "" si no configurada)
```

**`historial`**
```
id (autogenerado, string)
fecha: string "dd/mm/yyyy HH:MM"
filename: string
tipo: string (tipo de documento detectado: cfdi, nomina, etc.)
emisor: string (nombre del emisor, extraído de datos.emisor.nombre)
receptor: string
total: number
moneda: string
categoria: string (categoria_gasto)
num_items: number
datos: dict (el JSON COMPLETO de la extracción, anidado nativo —
             a diferencia de SQLite que lo guardaba como texto JSON)
```

### Diferencias de comportamiento importantes vs SQLite (para no repetir errores ya corregidos)

1. **IDs son strings, no enteros.** Cualquier ruta Flask que reciba un
   id de usuario o de historial debe usar `<parametro>` en vez de
   `<int:parametro>`. Ya corregido en todas las rutas de `app.py`.
   Regla general para futuras rutas: solo usar `<int:...>` si el
   parámetro es un número real (ej. paginación), nunca si es un id de
   documento Firestore.

2. **IDs en JavaScript deben ir entre comillas.** Al generar HTML
   dinámico con `onclick="funcion(${item.id})"`, si `item.id` es un
   string de Firestore (no numérico), el HTML resultante rompe
   (`ReferenceError: xyz123 is not defined`) porque JS lo interpreta
   como nombre de variable. Debe ser `onclick="funcion('${item.id}')"`
   con comillas simples explícitas.

3. **No existe GROUP BY / SUM nativo.** `obtener_metricas()` en
   `firestore_db.py` trae todos los documentos de `historial` y agrega
   manualmente en Python (diccionarios por tipo/emisor/categoría).
   Funciona bien al volumen actual; si el historial crece a decenas de
   miles de documentos, reconsiderar con agregados pre-calculados.

4. **No existe LIKE / búsqueda de texto parcial nativa.** La búsqueda
   en `obtener_historial(busqueda=...)` trae más documentos de los
   pedidos y filtra con `.lower() in` en Python. Válido al volumen
   actual, no escalaría a miles de registros sin una herramienta de
   búsqueda dedicada.

5. **No hay ALTER TABLE / migraciones de esquema.** Cualquier campo
   nuevo se puede guardar en cualquier momento sin preparar nada. Las
   funciones `inicializar_db()`, `migrar_columna_categoria()`,
   `migrar_columna_sheet_url()` existen como no-ops (`pass`) solo por
   compatibilidad de nombres con el código viejo — no hacen nada real.

6. **`guardar_lote()` cambió de firma.** Antes recibía
   `(archivos_validos, resultados, errores)`, ahora recibe solo
   `(resultados)` — ya no filtra internamente, se le pasa la lista de
   éxitos ya filtrada. Usa `db.batch()` para escribir todos los
   documentos del lote en una sola operación de red (más rápido y
   atómico que un loop de `.set()` individuales).

---

## 6. Autenticación y roles

- Flask-Login + Flask-Bcrypt, sin cambios respecto al diseño original.
- Roles: `admin` (acceso a extractor + dashboard + panel de admin) y
  `usuario` (acceso a extractor + su propio historial).
- No hay registro público — el admin crea cuentas manualmente desde
  `/admin`.
- Admin inicial se crea automáticamente al arrancar si no existe:
  usuario `admin`, contraseña `admin1234` (cambiar en producción).
- **Google Sheets es por usuario:** cada usuario tiene su propio campo
  `sheet_url` en su documento de Firestore. Para usarlo, el usuario
  crea su propia hoja y la comparte como Editor con el `client_email`
  de la cuenta de servicio del proyecto (visible en
  `google_credentials.json` → campo `client_email`). El backend nunca
  ve el contenido de la hoja de nadie más que del usuario que la
  configuró — aislamiento real, no solo de interfaz.

---

## 7. Pipeline de extracción (estado actual, antes de las mejoras del roadmap)

1. Usuario sube PDF o imagen (jpg/jpeg/png) — individual o hasta 500
   en lote.
2. `pdf_reader.py` (o `image_reader.py` para imágenes) extrae texto
   crudo.
3. `ai_extractor.py`:
   - `detectar_tipo()` clasifica el documento por palabras clave
     (cfdi, estado_cuenta, nomina, recibo_servicio, orden_compra,
     factura_internacional, documento_general) ANTES de llamar a la IA,
     para darle un prompt especializado por tipo.
   - `construir_prompt()` arma el prompt específico según el tipo.
   - Llamada a Groq (`llama-3.1-8b-instant`), sin reintentos ni
     backoff todavía (pendiente: Fase 5 del roadmap de mejoras).
   - `calcular_confianza_por_reglas()` valida por reglas (RFC con
     regex, formato de fechas, montos numéricos, validación cruzada
     subtotal+impuestos vs total) y la combina con la confianza
     autorreportada por la IA — las reglas nunca se sobrescriben a
     "alta" solo por lo que diga la IA, solo pueden bajar de nivel.
4. Cálculo de alerta de cambio de precio por producto: compara el
   `precio_unitario` de cada item contra el promedio histórico del
   mismo emisor + mismo producto (clave compuesta de
   `categoria_producto` + `variante_especifica` + `material_o_marca`,
   función `construir_clave_producto()`). Si la variación es ≥15%,
   marca `item["alerta_precio"]`.
   **⚠️ BUG CONOCIDO, PENDIENTE DE DIAGNÓSTICO:** esta alerta dejó de
   dispararse después de la migración a Firestore. Sospecha inicial:
   algo en `buscar_precios_historicos_producto()` (comparación de
   campos o tipos de dato) no coincide con el comportamiento que tenía
   la versión SQLite original. Documentado como Bloque 27 en el
   roadmap de mejoras.
5. Se guarda en Firestore (`guardar_extraccion()` o `guardar_lote()`).
6. Preview editable se muestra en el frontend antes de exportar —
   todos los campos y la tabla de items son editables directamente
   (contenteditable / inputs), con indicador de confianza por campo
   (verde/naranja/rojo) y botón de restaurar original.

---

## 8. Estructura JSON de una extracción (campos principales)

```json
{
  "tipo_documento": "cfdi",
  "numero_documento": "...",
  "fecha_emision": "dd/mm/yyyy",
  "fecha_vencimiento": "dd/mm/yyyy o null",
  "emisor": {"nombre": "...", "rfc": "...", "direccion": "..."},
  "receptor": {"nombre": "...", "rfc": "..."},
  "moneda": "MXN",
  "metodo_pago": "...",
  "categoria_gasto": "una de 11 categorías cerradas",
  "subtotal": 0.0,
  "impuestos": 0.0,
  "total": 0.0,
  "notas": "...",
  "items": [
    {
      "descripcion": "...",
      "cantidad": 0,
      "precio_unitario": 0.0,
      "importe": 0.0,
      "categoria_producto": "materia_prima_o_insumo | mercancia_para_reventa | equipo_o_herramienta | consumible_operativo | refaccion_o_repuesto | servicio | otro",
      "variante_especifica": "talla/modelo/presentación o null",
      "material_o_marca": "material o marca si afecta precio, o null",
      "alerta_precio": {"tipo": "subida", "variacion_pct": 0.0, "precio_anterior_promedio": 0.0} | null
    }
  ],
  "_confianza": { "campo": "alta|media|baja", ... }
}
```

**Nota:** este JSON está DESACTUALIZADO respecto al roadmap en curso —
el Bloque 17 (completado) agregó el campo `sku` a cada item y
modificó las instrucciones del prompt para que `impuestos` capture IVA
aunque el documento no use la palabra "impuesto" literal. Ver
`roadmap_mejoras_extractor.md` para el detalle vivo de qué campos se
han agregado y cuáles siguen en construcción.

---

## 9. Decisiones de arquitectura ya tomadas (para no reabrir la discusión)

- **Firestore sobre Cloud SQL** — ver sección 5, justificación completa.
- **NO se integra LiteLLM ni OpenRouter** para el AI Gateway (Fase 6
  del roadmap de mejoras) — un solo punto de llamada al LLM hoy no
  justifica la complejidad de una librería externa. Se construye un
  fallback propio (~40 líneas). Se reevaluará si en el futuro (ej.
  Proyecto 8 del portafolio, con voz en tiempo real) existen 3+ puntos
  de llamada a LLMs con necesidades distintas.
- **Resumen General del batch: dos modalidades, no una sola** — el
  usuario pidió que la tabla de resumen del batch traiga TODOS los
  campos de cabecera (no solo los 7 que trae hoy), y además quiere
  poder ver el detalle por línea de producto (con SKU) sin tener que
  abrir hoja por hoja. Se acordó implementar ambas vistas con selector
  en frontend: "por factura" (una fila por documento, todas las
  columnas de cabecera) y "por producto" (una fila por línea de
  producto, repitiendo cabecera, incluye SKU). "Por producto" es el
  modo por defecto porque es el que cumple el objetivo original de
  "lista lista para filtrar y mandar al contador". Ver Fase 2 del
  roadmap de mejoras para el detalle de bloques.

---

## 10. Pendientes cosméticos (no bloquean desarrollo)

- Actualizar README.md del repositorio (todavía dice SQLite, Railway,
  estructura de archivos vieja).
- Eliminar `Procfile` del repositorio (residual de cuando se planeaba
  Railway, ya no se usa con Cloud Run + Dockerfile).
- Borrar el documento de usuario `prueba_firestore` en la colección
  `usuarios` de Firestore (quedó de una prueba manual durante la
  migración).

---

## 11. Dónde está el trabajo activo ahora mismo

El desarrollo activo está en `roadmap_mejoras_extractor.md` — 6 fases,
30 bloques, cubriendo: SKU en todo el pipeline, Resumen General
completo del batch con dos modalidades, fix del botón de exportar a
Sheets, reportes por rango de tiempo, resiliencia del LLM (retries +
fallback), y observabilidad (tokens/costos/latencia). Ese documento es
la fuente de verdad de QUÉ SIGUE; este spec.md es la fuente de verdad
de CÓMO ESTÁ CONSTRUIDO HOY. Revisar ambos al retomar el proyecto.
