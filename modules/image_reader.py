# -*- coding: utf-8 -*-
import os
import platform
import pytesseract
from PIL import Image
from pillow_heif import register_heif_opener

# Registers HEIC/HEIF support into Pillow's Image.open(), so the rest
# of this module does not need any HEIC-specific branching — Image.open()
# will transparently handle .heic files the same way it handles .jpg.
register_heif_opener()

# En Windows local, Tesseract esta en una ruta especifica.
# En el contenedor Docker (Linux/Cloud Run), esta en el PATH del sistema
# porque lo instalamos con apt-get, asi que no hace falta especificar ruta.
if platform.system() == "Windows":
    ruta_windows = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if os.path.exists(ruta_windows):
        pytesseract.pytesseract.tesseract_cmd = ruta_windows


def extraer_texto_imagen(filepath):
    """
    Usa OCR (Tesseract) para leer el texto de una imagen de ticket o recibo.
    Devuelve la misma estructura que extraer_texto_pdf para mantener
    compatibilidad con el resto del sistema.
    """
    imagen = Image.open(filepath)
    texto = pytesseract.image_to_string(imagen, lang='spa')

    return {
        "texto_completo": texto,
        "paginas": [{"numero": 1, "texto": texto}],
        "num_paginas": 1
    }