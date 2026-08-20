# -*- coding: utf-8 -*-
"""
Reads text content from XML files, primarily targeting Mexican CFDI
invoices. Unlike PDF/image readers, XML is already structured text,
so no OCR or layout parsing is needed — we extract the raw text
content so the existing AI prompt pipeline can process it the same
way it processes PDF-extracted text.
"""
import xml.etree.ElementTree as ET


def extraer_texto_xml(filepath: str) -> dict:
    """
    Parses an XML file and flattens its tags and attributes into a
    single text block, so it can be fed into the same AI extraction
    prompt used for PDF/image text.

    Args:
        filepath: path to the .xml file on disk.

    Returns:
        A dict with the same shape as extraer_texto_pdf() /
        extraer_texto_imagen(), for pipeline compatibility:
        {"texto_completo": str, "paginas": list, "num_paginas": int}.

    Raises:
        ET.ParseError: if the file is not valid XML.
    """
    tree = ET.parse(filepath)
    root = tree.getroot()

    lineas_texto = []

    # Recursively walk every element, capturing both attributes (where
    # CFDI stores most of its data, e.g. <cfdi:Comprobante Total="1160.00">)
    # and any inline text content.
    def recorrer_elemento(elemento):
        tag_limpio = elemento.tag.split("}")[-1]  # strip XML namespace prefix

        if elemento.attrib:
            atributos_texto = ", ".join(f"{k}={v}" for k, v in elemento.attrib.items())
            lineas_texto.append(f"{tag_limpio}: {atributos_texto}")

        if elemento.text and elemento.text.strip():
            lineas_texto.append(f"{tag_limpio}: {elemento.text.strip()}")

        for hijo in elemento:
            recorrer_elemento(hijo)

    recorrer_elemento(root)
    texto_completo = "\n".join(lineas_texto)

    return {
        "texto_completo": texto_completo,
        "paginas": [{"numero": 1, "texto": texto_completo}],
        "num_paginas": 1
    }