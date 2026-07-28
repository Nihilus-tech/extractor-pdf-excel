# Imagen base de Python
FROM python:3.10-slim

# Instalar Tesseract OCR y el paquete de idioma español
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-spa \
    && rm -rf /var/lib/apt/lists/*

# Carpeta de trabajo dentro del contenedor
WORKDIR /app

# Copiar solo requirements primero (optimiza el cache de Docker)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto del codigo
COPY . .

# Crear carpetas necesarias que la app espera encontrar
RUN mkdir -p uploads data

# Cloud Run inyecta la variable PORT automaticamente
ENV PORT=8080
EXPOSE 8080

# Arrancar con Gunicorn, apuntando al puerto que Cloud Run espera
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 app:app