# -*- coding: utf-8 -*-
"""
Quick manual test script for firestore_db.py.
Not part of the app — run it directly to verify the Firestore
connection and basic user operations work before wiring it into app.py.
"""
from modules.firestore_db import (
    crear_usuario, buscar_usuario_por_username,
    buscar_usuario_por_id, obtener_todos_usuarios,
    actualizar_sheet_url
)

print("1) Creando usuario de prueba...")
creado = crear_usuario("prueba_firestore", "hash_falso_123", rol="usuario")
print(f"   Resultado: {creado}")

print("\n2) Buscando por username...")
usuario = buscar_usuario_por_username("prueba_firestore")
if usuario:
    print(f"   Encontrado: id={usuario.id}, username={usuario.username}, rol={usuario.rol}")
else:
    print("   ERROR: no se encontro el usuario")

print("\n3) Buscando por id...")
if usuario:
    usuario_por_id = buscar_usuario_por_id(usuario.id)
    print(f"   Encontrado: username={usuario_por_id.username}")

print("\n4) Actualizando sheet_url...")
if usuario:
    actualizar_sheet_url(usuario.id, "https://docs.google.com/prueba")
    usuario_actualizado = buscar_usuario_por_id(usuario.id)
    print(f"   sheet_url ahora es: {usuario_actualizado.sheet_url}")

print("\n5) Listando todos los usuarios...")
todos = obtener_todos_usuarios()
for u in todos:
    print(f"   - {u['username']} ({u['rol']}) creado {u['creado_en']}")

print("\nPrueba terminada.")

print("\n--- PRUEBA DE HISTORIAL ---")

from modules.firestore_db import (
    guardar_extraccion, obtener_historial, obtener_detalle,
    eliminar_registro, obtener_metricas
)

print("\n6) Guardando extraccion de prueba...")
datos_prueba = {
    "tipo_documento": "cfdi",
    "emisor": {"nombre": "Proveedor de Prueba SA"},
    "receptor": {"nombre": "Cliente de Prueba"},
    "total": 1500.50,
    "moneda": "MXN",
    "categoria_gasto": "Insumos y materiales",
    "items": [
        {"descripcion": "Producto de prueba", "cantidad": 2, "precio_unitario": 750.25, "importe": 1500.50}
    ]
}
guardar_extraccion("factura_prueba.pdf", datos_prueba)
print("   Guardado (revisa el resultado en el paso 7)")

print("\n7) Listando historial reciente...")
historial = obtener_historial(limite=5)
for h in historial:
    print(f"   - id={h['id']} | {h['filename']} | {h['emisor']} | ${h['total']}")

if historial:
    primer_id = historial[0]["id"]

    print(f"\n8) Obteniendo detalle de {primer_id}...")
    detalle = obtener_detalle(primer_id)
    print(f"   Filename: {detalle['filename']}")
    print(f"   Total en datos: {detalle['datos'].get('total')}")

    print("\n9) Calculando metricas del dashboard...")
    metricas = obtener_metricas()
    print(f"   Total docs: {metricas['total_docs']}")
    print(f"   Total monto: {metricas['total_monto']}")
    print(f"   Por tipo: {metricas['por_tipo']}")
    print(f"   Por emisor: {metricas['por_emisor']}")

    print(f"\n10) Eliminando registro de prueba {primer_id}...")
    eliminar_registro(primer_id)
    print("   Eliminado")

print("\nPrueba de historial terminada.")