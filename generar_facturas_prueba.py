# -*- coding: utf-8 -*-
"""
Script standalone para generar 2 PDFs de prueba que simulan facturas
del mismo proveedor ficticio, con el mismo producto pero precio distinto.
Uso: coloca este archivo en la raiz del proyecto y ejecuta:
    python generar_facturas_prueba.py
Esto crea 2 archivos en la carpeta actual: factura_prueba_1.pdf y factura_prueba_2.pdf
Subelos uno por uno (o en lote) al extractor para probar las alertas de precio.
"""

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


def generar_factura(nombre_archivo, numero_factura, fecha, precio_unitario, cantidad):
    c = canvas.Canvas(nombre_archivo, pagesize=letter)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, 750, "TECNO ACCESORIOS DEL NORTE SA DE CV")
    c.setFont("Helvetica", 10)
    c.drawString(50, 730, "RFC: TAN850612XY3")
    c.drawString(50, 715, "Direccion: Av. Insurgentes Sur 123, CDMX")

    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, 680, f"FACTURA No. {numero_factura}")
    c.setFont("Helvetica", 10)
    c.drawString(50, 660, f"Fecha de emision: {fecha}")
    c.drawString(50, 645, "Receptor: Nihilus Tech")
    c.drawString(50, 630, "RFC Receptor: XAXX010101000")
    c.drawString(50, 615, "Metodo de pago: Transferencia")
    c.drawString(50, 600, "Moneda: MXN")

    importe = precio_unitario * cantidad

    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, 560, "Descripcion")
    c.drawString(280, 560, "Cantidad")
    c.drawString(350, 560, "Precio Unit.")
    c.drawString(450, 560, "Importe")

    c.setFont("Helvetica", 10)
    c.drawString(50, 540, "Funda de silicon para iPhone 15 color negro")
    c.drawString(290, 540, str(cantidad))
    c.drawString(355, 540, f"${precio_unitario:.2f}")
    c.drawString(455, 540, f"${importe:.2f}")

    c.setFont("Helvetica-Bold", 10)
    c.drawString(350, 480, f"Subtotal: ${importe:.2f}")
    c.drawString(350, 465, f"IVA: ${importe * 0.16:.2f}")
    c.drawString(350, 450, f"TOTAL: ${importe * 1.16:.2f}")

    c.save()
    print(f"Generado: {nombre_archivo} (precio unitario: ${precio_unitario:.2f})")


if __name__ == "__main__":
    # Factura 1: precio normal
    generar_factura(
        "factura_prueba_1.pdf",
        numero_factura="A-1001",
        fecha="01/06/2026",
        precio_unitario=45.00,
        cantidad=20
    )

    # Factura 2: mismo producto, mismo proveedor, precio 30% mas alto
    generar_factura(
        "factura_prueba_2.pdf",
        numero_factura="A-1050",
        fecha="15/07/2026",
        precio_unitario=58.50,
        cantidad=15
    )

    print("\nListo. Sube primero factura_prueba_1.pdf, luego factura_prueba_2.pdf")
    print("La segunda deberia mostrar la alerta de precio (subio ~30%).")