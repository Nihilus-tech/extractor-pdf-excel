# -*- coding: utf-8 -*-
import sqlite3
import os
import json
from datetime import datetime, timedelta

DB_PATH = os.path.join("data", "historial.db")

def get_connection():
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def inicializar_db():
    """Crea la tabla si no existe. Se llama al arrancar la app."""
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS historial (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha       TEXT NOT NULL,
            filename    TEXT NOT NULL,
            tipo        TEXT,
            emisor      TEXT,
            receptor    TEXT,
            total       REAL,
            moneda      TEXT,
            num_items   INTEGER,
            categoria   TEXT,
            datos_json  TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

def migrar_columna_categoria():
    """
    Agrega la columna 'categoria' a una tabla historial que ya existia
    antes de esta actualizacion. Se puede llamar de forma segura multiples
    veces, no falla si la columna ya existe.
    """
    conn = get_connection()
    try:
        conn.execute("ALTER TABLE historial ADD COLUMN categoria TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        # La columna ya existe, no hay nada que hacer
        pass
    conn.close()    

def guardar_extraccion(filename, datos):
    """
    Guarda una extracción individual en el historial.
    datos es el dict que devuelve la IA.
    """
    conn = get_connection()
    conn.execute("""
        INSERT INTO historial
            (fecha, filename, tipo, emisor, receptor, total, moneda, num_items, categoria, datos_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        datetime.now().strftime("%d/%m/%Y %H:%M"),
        filename,
        datos.get("tipo_documento"),
        datos.get("emisor", {}).get("nombre") if datos.get("emisor") else None,
        datos.get("receptor", {}).get("nombre") if datos.get("receptor") else None,
        datos.get("total"),
        datos.get("moneda"),
        len(datos.get("items") or []),
        datos.get("categoria_gasto"),
        json.dumps(datos, ensure_ascii=False)
    ))
    conn.commit()
    conn.close()

def guardar_lote(archivos_validos, resultados, errores):
    """
    Guarda solo los documentos exitosos del lote.
    archivos_validos y errores se reciben pero no se guardan
    en historial — solo los que procesaron bien.
    """
    conn = get_connection()
    for r in resultados:
        datos = r.get("datos", {})
        conn.execute("""
            INSERT INTO historial
                (fecha, filename, tipo, emisor, receptor, total, moneda, num_items, categoria, datos_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().strftime("%d/%m/%Y %H:%M"),
            r.get("filename", ""),
            datos.get("tipo_documento"),
            datos.get("emisor", {}).get("nombre") if datos.get("emisor") else None,
            datos.get("receptor", {}).get("nombre") if datos.get("receptor") else None,
            datos.get("total"),
            datos.get("moneda"),
            len(datos.get("items") or []),
            datos.get("categoria_gasto"),
            json.dumps(datos, ensure_ascii=False)
        ))
    conn.commit()
    conn.close()

def obtener_historial(limite=50, busqueda=None):
    """
    Devuelve los últimos registros.
    Si busqueda tiene texto, filtra por filename o emisor.
    """
    conn = get_connection()
    if busqueda:
        rows = conn.execute("""
            SELECT id, fecha, filename, tipo, emisor, total, moneda, num_items
            FROM historial
            WHERE filename LIKE ? OR emisor LIKE ?
            ORDER BY id DESC LIMIT ?
        """, (f"%{busqueda}%", f"%{busqueda}%", limite)).fetchall()
    else:
        rows = conn.execute("""
            SELECT id, fecha, filename, tipo, emisor, total, moneda, num_items
            FROM historial
            ORDER BY id DESC LIMIT ?
        """, (limite,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def obtener_detalle(registro_id):
    """Devuelve los datos JSON completos de un registro."""
    conn = get_connection()
    row = conn.execute(
        "SELECT datos_json, filename FROM historial WHERE id = ?", (registro_id,)
    ).fetchone()
    conn.close()
    if row:
        return {"filename": row["filename"], "datos": json.loads(row["datos_json"])}
    return None

def obtener_historial_completo():
    """
    Devuelve TODOS los registros del historial con sus datos completos,
    listos para generar un Excel consolidado de todo lo procesado.
    """
    conn = get_connection()
    rows = conn.execute("""
        SELECT filename, datos_json
        FROM historial
        ORDER BY id ASC
    """).fetchall()
    conn.close()

    resultados = []
    for r in rows:
        resultados.append({
            "filename": r["filename"],
            "datos": json.loads(r["datos_json"])
        })
    return resultados    

def buscar_precios_historicos_producto(emisor, clave_producto, excluir_filename=None):
    """
    Busca en TODO el historial los precios unitarios anteriores
    de un producto especifico (misma clave) del mismo proveedor.
    Devuelve una lista de precios unitarios encontrados.
    """
    if not emisor or not clave_producto:
        return []

    conn = get_connection()
    rows = conn.execute("""
        SELECT filename, datos_json FROM historial
        WHERE emisor = ?
        ORDER BY id ASC
    """, (emisor,)).fetchall()
    conn.close()

    precios = []
    for row in rows:
        if excluir_filename and row["filename"] == excluir_filename:
            continue
        datos = json.loads(row["datos_json"])
        for item in datos.get("items") or []:
            categoria = item.get("categoria_producto")
            modelo = item.get("modelo_dispositivo")
            variante = item.get("material_o_variante")
            if not categoria:
                continue
            partes = [categoria]
            if modelo:
                partes.append(modelo)
            if variante:
                partes.append(variante)
            clave_item = "|".join(partes)

            if clave_item == clave_producto:
                precio = item.get("precio_unitario")
                if isinstance(precio, (int, float)):
                    precios.append(precio)

    return precios


def eliminar_registro(registro_id):
    """Elimina un registro del historial."""
    conn = get_connection()
    conn.execute("DELETE FROM historial WHERE id = ?", (registro_id,))
    conn.commit()
    conn.close()

def obtener_metricas():
    """Métricas globales para el dashboard (lo usaremos en el paso 6)."""
    conn = get_connection()
    total_docs = conn.execute("SELECT COUNT(*) FROM historial").fetchone()[0]
    total_monto = conn.execute(
        "SELECT COALESCE(SUM(total), 0) FROM historial WHERE total IS NOT NULL"
    ).fetchone()[0]
    por_tipo = conn.execute("""
        SELECT tipo, COUNT(*) as cantidad, COALESCE(SUM(total), 0) as monto
        FROM historial
        WHERE tipo IS NOT NULL
        GROUP BY tipo ORDER BY cantidad DESC
    """).fetchall()
    por_emisor = conn.execute("""
        SELECT emisor, COUNT(*) as cantidad, COALESCE(SUM(total), 0) as monto
        FROM historial
        WHERE emisor IS NOT NULL
        GROUP BY emisor ORDER BY monto DESC LIMIT 10
    """).fetchall()
    por_categoria = conn.execute("""
        SELECT categoria, COUNT(*) as cantidad, COALESCE(SUM(total), 0) as monto
        FROM historial
        WHERE categoria IS NOT NULL
        GROUP BY categoria ORDER BY monto DESC
    """).fetchall()
    conn.close()
    return {
        "total_docs": total_docs,
        "total_monto": total_monto,
        "por_tipo": [dict(r) for r in por_tipo],
        "por_emisor": [dict(r) for r in por_emisor],
        "por_categoria": [dict(r) for r in por_categoria]
    }


def obtener_estadisticas_ultimos_meses():
    """Estadísticas de los últimos 6 meses."""
    conn = get_connection()
    ultimos_6_meses = datetime.now() - timedelta(days=180)
    rows = conn.execute("""
        SELECT strftime('%Y-%m', fecha) as mes, COUNT(*) as cantidad, COALESCE(SUM(total), 0) as monto
        FROM historial
        WHERE fecha >= ?
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]      



# ── SISTEMA DE USUARIOS ────────────────────────────────────────────────────────
from flask_login import UserMixin

class Usuario(UserMixin):
    """
    Representa un usuario de la app.
    UserMixin le da a Flask-Login los métodos que necesita:
    is_authenticated, is_active, get_id, etc.
    """
    def __init__(self, id, username, password_hash, rol):
        self.id = id
        self.username = username
        self.password_hash = password_hash
        self.rol = rol

    def es_admin(self):
        return self.rol == "admin"


def inicializar_usuarios():
    """Crea la tabla de usuarios si no existe."""
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            rol           TEXT NOT NULL DEFAULT 'usuario',
            creado_en     TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def crear_usuario(username, password_hash, rol="usuario"):
    """Inserta un usuario nuevo. Devuelve True si OK, False si ya existe."""
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO usuarios (username, password_hash, rol, creado_en) VALUES (?, ?, ?, ?)",
            (username, password_hash, rol, datetime.now().strftime("%d/%m/%Y %H:%M"))
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def buscar_usuario_por_username(username):
    """Busca usuario por nombre. Devuelve objeto Usuario o None."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM usuarios WHERE username = ?", (username,)
    ).fetchone()
    conn.close()
    if row:
        return Usuario(row["id"], row["username"], row["password_hash"], row["rol"])
    return None


def buscar_usuario_por_id(user_id):
    """Flask-Login necesita esto para reconstruir el usuario desde la sesión."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM usuarios WHERE id = ?", (user_id,)
    ).fetchone()
    conn.close()
    if row:
        return Usuario(row["id"], row["username"], row["password_hash"], row["rol"])
    return None


def obtener_todos_usuarios():
    """Lista todos los usuarios. Solo para el admin."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, username, rol, creado_en FROM usuarios ORDER BY creado_en DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def eliminar_usuario(user_id):
    """Elimina un usuario por ID."""
    conn = get_connection()
    conn.execute("DELETE FROM usuarios WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()

    