# modules/pdf_reader.py
import pdfplumber

def extraer_texto_pdf(filepath):
    """
    Lee todas las páginas del PDF y devuelve:
    - texto_completo: todo el texto concatenado
    - paginas: lista con el texto de cada página por separado
    - num_paginas: cuántas páginas tiene el PDF
    """
    texto_completo = ""
    paginas = []

    with pdfplumber.open(filepath) as pdf:
        num_paginas = len(pdf.pages)

        for i, pagina in enumerate(pdf.pages):
            texto_pagina = pagina.extract_text() or ""
            paginas.append({
                "numero": i + 1,
                "texto": texto_pagina
            })
            texto_completo += f"\n--- PÁGINA {i+1} ---\n{texto_pagina}"

    return {
        "texto_completo": texto_completo,
        "paginas": paginas,
        "num_paginas": num_paginas
    }