# -*- coding: utf-8 -*-
import pytesseract
from PIL import Image

# Ruta exacta donde se instaló Tesseract en Windows
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe" 

def extraer_texto_imagen(filepath):
    """
    Usa OCR (Tesseract) para leer el texto de una imagen de ticket o recibo.
    Devuelve la misma estructura que extraer_texto_pdf para mantener
    compatibilidad con el resto del sistema.
    """
    imagen = Image.open(filepath)

    # lang='spa' usa el paquete de idioma español que instalaste
    texto = pytesseract.image_to_string(imagen, lang='spa')

    return {
        "texto_completo": texto,
        "paginas": [{"numero": 1, "texto": texto}],
        "num_paginas": 1
    }