# 📄 Extractor de Datos PDF → Excel con IA

Aplicación web empresarial que permite a pequeños negocios (tiendas de abarrotes, celulares, accesorios) subir facturas, recibos y estados de cuenta en PDF o imagen y obtener automáticamente los datos estructurados en Excel o Google Sheets, con revisión humana antes de exportar.

![Python](https://img.shields.io/badge/Python-3.10-blue)
![Flask](https://img.shields.io/badge/Flask-3.1-lightgrey)
![Groq](https://img.shields.io/badge/Groq-LLaMA_3.1-orange)
![Firestore](https://img.shields.io/badge/Database-Firestore-yellow)
![License](https://img.shields.io/badge/License-MIT-green)

---

## ✨ Funcionalidades

- **Extracción inteligente con IA** — Groq + LLaMA 3.1 detecta automáticamente el tipo de documento (CFDI mexicano, estado de cuenta, nómina, recibo de servicios, orden de compra, factura internacional) y extrae los datos clave con prompts especializados por tipo
- **Procesamiento por lotes** — sube hasta 500 PDFs de una sola vez con cola visual y procesamiento en secuencia
- **Revisión humana editable** — preview interactivo antes de descargar: todos los campos y la tabla de items son editables directamente en la interfaz, con indicador de confianza por campo y botón para restaurar el original
- **Edición por lote con modal** — en modo lote, cada documento tiene un botón "Editar" que abre un modal completo para corregir datos antes de generar el Excel consolidado
- **Alertas de cambio de precio** — compara el precio unitario de cada producto contra su historial con el mismo proveedor y avisa si subió 15% o más
- **Exportación a Excel** — archivo .xlsx profesional con hoja de resumen + hoja por documento, totales automáticos y formato de moneda
- **Exportación a Google Sheets por usuario** — cada usuario configura su propia hoja de cálculo; los datos nunca se mezclan entre cuentas
- **Historial en Firestore** — cada extracción se guarda automáticamente con búsqueda por proveedor o nombre de archivo y recarga de extracciones anteriores
- **Dashboard de métricas** — total procesado por proveedor, documentos por tipo, por categoría de gasto, monto global acumulado y gráficas con Chart.js
- **Sistema de usuarios** — login seguro con Flask-Login y contraseñas encriptadas con Bcrypt, roles admin y usuario, panel de administración para gestionar cuentas
- **OCR para imágenes** — soporta tickets y recibos fotografiados (JPG/PNG), no solo PDFs

---

## 🛠️ Stack tecnológico

| Capa | Tecnología |
|------|-----------|
| Backend | Python 3.10 + Flask |
| IA | Groq API + LLaMA 3.1 8B Instant |
| Extracción PDF | pdfplumber |
| OCR de imágenes | pytesseract + Pillow |
| Excel | openpyxl |
| Google Sheets | gspread + google-auth |
| Auth | Flask-Login + Flask-Bcrypt |
| Base de datos | **Google Firestore** (modo nativo) |
| Frontend | HTML + CSS + JavaScript vanilla |
| Gráficas | Chart.js (CDN) |
| Deploy | **Google Cloud Run** (Docker) |

---

## 🚀 Instalación local

### Requisitos previos

- Python 3.10
- Miniconda o Anaconda
- Cuenta en [Groq Cloud](https://console.groq.com) para obtener tu API key
- Cuenta de Google Cloud con un proyecto y una base de datos Firestore creada (modo nativo)
- (Opcional) Credenciales de cuenta de servicio para exportación a Google Sheets

### 1. Clona el repositorio

```bash
git clone https://github.com/Nihilus-tech/extractor-pdf-excel.git
cd extractor-pdf-excel
```

### 2. Crea y activa el entorno Conda

```bash
conda create -n extractor_pdf python=3.10
conda activate extractor_pdf
```

### 3. Instala las dependencias

```bash
pip install -r requirements.txt
```

### 4. Configura las variables de entorno

Crea un archivo `.env` en la raíz del proyecto:

```env
GROQ_API_KEY=tu_api_key_de_groq_aqui
SECRET_KEY=una_clave_secreta_larga_y_random
UPLOAD_FOLDER=uploads
FIRESTORE_DATABASE_ID=nombre_de_tu_base_de_datos_firestore
```

> El `FIRESTORE_DATABASE_ID` es necesario si tu base de datos no usa el nombre por defecto `(default)`. Revisa el ID exacto en la consola de Firestore de tu proyecto GCP.

### 5. Autentica tu máquina local con Google Cloud

```bash
gcloud auth application-default login
```

Esto permite que la app se conecte a Firestore desde tu computadora sin necesitar un archivo de credenciales aparte. En producción (Cloud Run), esto se resuelve automáticamente con la cuenta de servicio del proyecto.

### 6. (Opcional) Configura Google Sheets

Si quieres usar la exportación a Google Sheets:

1. Crea un proyecto en [Google Cloud Console](https://console.cloud.google.com) (puede ser el mismo que usas para Firestore)
2. Activa las APIs de Google Sheets y Google Drive
3. Crea una cuenta de servicio y descarga el archivo JSON de credenciales
4. Renómbralo `google_credentials.json` y colócalo en la raíz del proyecto
5. Cada usuario de la app deberá crear su propia hoja de Google Sheets y compartirla como Editor con el `client_email` de ese archivo de credenciales (visible dentro del JSON, o corriendo `python -c "import json; print(json.load(open('google_credentials.json'))['client_email'])"`)
6. La URL de la hoja se configura desde dentro de la app, en el perfil de cada usuario — no es una URL global compartida

### 7. Ejecuta la aplicación

```bash
python app.py
```

Abre tu navegador en `http://127.0.0.1:5000`

### 8. Credenciales iniciales

Al iniciar por primera vez se crea automáticamente el usuario administrador:

```
Usuario: admin
Contraseña: admin1234
```

> ⚠️ Cambia la contraseña desde el Panel de Administración antes de usar en producción.

---

## 📁 Estructura del proyecto

```
extractor-pdf-excel/
│
├── app.py                        # Rutas Flask, auth, todas las integraciones
├── requirements.txt              # Dependencias del proyecto
├── Dockerfile                    # Imagen para deploy en Cloud Run
├── .env                          # Variables de entorno (no incluido en repo)
├── google_credentials.json       # Credenciales Google (no incluido en repo)
│
├── modules/
│   ├── pdf_reader.py              # Extracción de texto con pdfplumber
│   ├── image_reader.py            # OCR con pytesseract
│   ├── ai_extractor.py            # Detección de tipo + extracción con Groq
│   ├── excel_generator.py         # Generación de .xlsx con openpyxl
│   ├── sheets_exporter.py         # Exportación a Google Sheets
│   └── firestore_db.py            # Historial + sistema de usuarios (Firestore)
│
├── templates/
│   ├── index.html                 # Interfaz principal (extractor + historial + batch)
│   ├── login.html                 # Página de inicio de sesión
│   ├── dashboard.html             # Dashboard de métricas
│   └── admin.html                 # Panel de administración
│
├── screenshots/                   # Capturas para el README
└── uploads/                       # Archivos subidos temporalmente (ignorado por git)
```

---

## 🔐 Sistema de autenticación

- **Admin** — acceso completo: extractor + dashboard + panel de administración
- **Usuario** — acceso al extractor y su historial personal

El admin crea las cuentas manualmente desde el panel. No hay registro público.

---

## 📊 Tipos de documentos soportados

| Tipo | Detección | Campos especializados |
|------|-----------|----------------------|
| CFDI Mexicano | ✅ Automática | UUID, RFC emisor/receptor, régimen fiscal, IVA |
| Estado de cuenta | ✅ Automática | Banco, CLABE, saldo inicial/final, movimientos |
| Nómina | ✅ Automática | Percepciones, deducciones, ISR, IMSS, neto |
| Recibo de servicios | ✅ Automática | Proveedor, número de contrato, período |
| Orden de compra | ✅ Automática | Número de orden, condiciones de pago |
| Factura internacional | ✅ Automática | Invoice number, due date, currency |
| Documento general | ✅ Fallback | Extracción genérica de campos comunes |

---

## ☁️ Deploy en producción

Este proyecto está desplegado en **Google Cloud Run**, usando el `Dockerfile` incluido:

```bash
gcloud run deploy extractor-pdf-excel --source . --region us-central1
```

La base de datos (Firestore) y las credenciales en producción se resuelven automáticamente a través de la cuenta de servicio del proyecto — no requiere configuración adicional de credenciales en Cloud Run.

---

## 🔗 Proyectos relacionados

- [agente-ventas-ia](https://github.com/Nihilus-tech/agente-ventas-ia) — Agente RAG de ventas con Flask, LangChain y ChromaDB
- [analizador-reportes-ia](https://github.com/Nihilus-tech/analizador-reportes-ia) — Analizador de reportes Excel/CSV con insights en lenguaje natural
- [lead-classifier](https://github.com/Nihilus-tech) — Clasificador de leads cloud-native con FastAPI + Firestore + Cloud Run

---

## 📄 Licencia

MIT License — libre para uso personal y comercial.

---

**Desarrollado por [Nihilus](https://github.com/Nihilus-tech)**