# -*- coding: utf-8 -*-
"""
Firestore data layer for the Extractor PDF app.
Replaces the previous SQLite-based db_historial.py, since Cloud Run
containers do not persist local files across restarts.
"""
import os
from datetime import datetime, timedelta
from typing import Optional
from google.cloud import firestore
from flask_login import UserMixin

# Single shared Firestore client for the whole app.
# In Cloud Run this authenticates automatically via the default 
# service account. Locally it uses the credentials created by
# "gcloud auth application-default login".
#
# database_id is required here because this Firestore database was
# created with a custom id ("extractor-pdf-2-0") instead of the
# implicit "(default)" name. If a future project uses the default
# database, this argument can be omitted.
FIRESTORE_DATABASE_ID = os.getenv("FIRESTORE_DATABASE_ID", "extractor-pdf-2-0")
db = firestore.Client(database=FIRESTORE_DATABASE_ID)

USUARIOS_COLLECTION = "usuarios"
HISTORIAL_COLLECTION = "historial"


# ── MODELO DE USUARIO ──────────────────────────────────────────────────────

class Usuario(UserMixin):
    """
    Represents an app user.
    UserMixin gives Flask-Login the methods it needs:
    is_authenticated, is_active, get_id, etc.

    Note: unlike the SQLite version, "id" here is a Firestore
    auto-generated string (e.g. "aB3xY9kL2mN"), not an integer.
    """
    def __init__(
        self,
        id: str,
        username: str,
        password_hash: str,
        rol: str,
        creado_en: str = "",
        sheet_url: str = "",
        proveedor_ia_preferido: str = "groq"
    ):
        self.id = id
        self.username = username
        self.password_hash = password_hash
        self.rol = rol
        self.creado_en = creado_en
        self.sheet_url = sheet_url
        self.proveedor_ia_preferido = proveedor_ia_preferido

    def es_admin(self) -> bool:
        return self.rol == "admin"

    def get_id(self) -> str:
        """
        Flask-Login calls this to know how to store the user in the
        session cookie. Firestore ids are already strings, so no
        conversion is needed here (this overrides UserMixin's default,
        which just does str(self.id) — being explicit avoids confusion
        since we are no longer working with integer ids).
        """
        return str(self.id)


def _usuario_from_doc(doc) -> Optional[Usuario]:
    """
    Converts a Firestore document snapshot into a Usuario object.

    Args:
        doc: a Firestore DocumentSnapshot.

    Returns:
        Usuario instance, or None if the document does not exist.
    """
    if not doc.exists:
        return None
    data = doc.to_dict()
    return Usuario(
        id=doc.id,
        username=data.get("username", ""),
        password_hash=data.get("password_hash", ""),
        rol=data.get("rol", "usuario"),
        creado_en=data.get("creado_en", ""),
        sheet_url=data.get("sheet_url", ""),
        proveedor_ia_preferido=data.get("proveedor_ia_preferido", "groq")
    )


# ── OPERACIONES DE USUARIO ─────────────────────────────────────────────────

def crear_usuario(username: str, password_hash: str, rol: str = "usuario") -> bool:
    """
    Creates a new user document in Firestore.

    Args:
        username: unique username for login.
        password_hash: bcrypt hash of the password, never plain text.
        rol: either "admin" or "usuario".

    Returns:
        True if the user was created, False if the username already exists.
    """
    try:
        # Enforce uniqueness manually, since Firestore has no native
        # UNIQUE constraint like SQL does.
        existente = buscar_usuario_por_username(username)
        if existente:
            return False

        doc_ref = db.collection(USUARIOS_COLLECTION).document()
        doc_ref.set({
            "username": username,
            "password_hash": password_hash,
            "rol": rol,
            "creado_en": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "sheet_url": "",
            "proveedor_ia_preferido": "groq"
        })
        return True
    except Exception as e:
        print(f"[firestore_db] Error creating user: {e}")
        return False


def buscar_usuario_por_username(username: str) -> Optional[Usuario]:
    """
    Looks up a user by their username.

    Args:
        username: the username to search for.

    Returns:
        Usuario instance if found, otherwise None.
    """
    try:
        query = (
            db.collection(USUARIOS_COLLECTION)
            .where("username", "==", username)
            .limit(1)
        )
        resultados = list(query.stream())
        if not resultados:
            return None
        doc = resultados[0]
        data = doc.to_dict()
        return Usuario(
            id=doc.id,
            username=data.get("username", ""),
            password_hash=data.get("password_hash", ""),
            rol=data.get("rol", "usuario"),
            creado_en=data.get("creado_en", ""),
            sheet_url=data.get("sheet_url", ""),
            proveedor_ia_preferido=data.get("proveedor_ia_preferido", "groq")
        )
    except Exception as e:
        print(f"[firestore_db] Error searching user by username: {e}")
        return None


def buscar_usuario_por_id(user_id: str) -> Optional[Usuario]:
    """
    Looks up a user by their Firestore document id.
    Flask-Login calls this on every request to reload the logged-in user.

    Args:
        user_id: the Firestore document id (string).

    Returns:
        Usuario instance if found, otherwise None.
    """
    try:
        doc = db.collection(USUARIOS_COLLECTION).document(user_id).get()
        return _usuario_from_doc(doc)
    except Exception as e:
        print(f"[firestore_db] Error searching user by id: {e}")
        return None


def obtener_todos_usuarios() -> list:
    """
    Returns every user, most recently created first. Admin panel only.

    Returns:
        List of dicts with id, username, rol, creado_en.
    """
    try:
        docs = db.collection(USUARIOS_COLLECTION).stream()
        usuarios = []
        for doc in docs:
            data = doc.to_dict()
            usuarios.append({
                "id": doc.id,
                "username": data.get("username", ""),
                "rol": data.get("rol", "usuario"),
                "creado_en": data.get("creado_en", "")
            })
        # Sort in Python since Firestore ordering by a string date
        # field is not reliable without a proper timestamp type.
        usuarios.sort(key=lambda u: u["creado_en"], reverse=True)
        return usuarios
    except Exception as e:
        print(f"[firestore_db] Error listing users: {e}")
        return []


def eliminar_usuario(user_id: str) -> None:
    """
    Deletes a user document by id.

    Args:
        user_id: the Firestore document id (string) of the user to remove.
    """
    try:
        db.collection(USUARIOS_COLLECTION).document(user_id).delete()
    except Exception as e:
        print(f"[firestore_db] Error deleting user {user_id}: {e}")


def actualizar_sheet_url(user_id: str, sheet_url: str) -> None:
    """
    Updates the personal Google Sheets URL for a given user.

    Args:
        user_id: the Firestore document id (string) of the user.
        sheet_url: the full URL of the user's own Google Sheet.
    """
    try:
        db.collection(USUARIOS_COLLECTION).document(user_id).update({
            "sheet_url": sheet_url
        })
    except Exception as e:
        print(f"[firestore_db] Error updating sheet_url for {user_id}: {e}")

def actualizar_proveedor_preferido(user_id: str, proveedor: str) -> None:
    """
    Updates the user's preferred AI provider, used as the default
    choice for future extractions unless overridden per-extraction.

    Args:
        user_id: the Firestore document id (string) of the user.
        proveedor: "groq" or "gemini".
    """
    try:
        db.collection(USUARIOS_COLLECTION).document(user_id).update({
            "proveedor_ia_preferido": proveedor
        })
    except Exception as e:
        print(f"[firestore_db] Error updating proveedor_ia_preferido for {user_id}: {e}")

def inicializar_usuarios() -> None:
    """
    Placeholder kept for interface compatibility with the old SQLite
    module. Firestore collections do not need explicit creation —
    they are created automatically on first write. This function is
    intentionally a no-op.
    """
    pass


def inicializar_db() -> None:
    """
    Placeholder kept for interface compatibility with the old SQLite
    module. Firestore needs no schema setup. Intentionally a no-op.
    """
    pass


def migrar_columna_categoria() -> None:
    """
    Placeholder kept for interface compatibility with the old SQLite
    module. Firestore documents can hold arbitrary new fields without
    any migration step. Intentionally a no-op.
    """
    pass


def migrar_columna_sheet_url() -> None:
    """
    Placeholder kept for interface compatibility with the old SQLite
    module. Firestore documents can hold arbitrary new fields without
    any migration step. Intentionally a no-op.
    """
    pass


# ── OPERACIONES DE HISTORIAL ───────────────────────────────────────────────

def _extraer_nombre_emisor(datos: dict) -> Optional[str]:
    """
    Safely pulls the issuer name out of an extraction result, since
    "emisor" can sometimes be missing or not a dict depending on what
    the AI returned.

    Args:
        datos: the extraction result dict.

    Returns:
        The issuer name, or None if not available.
    """
    emisor = datos.get("emisor")
    if isinstance(emisor, dict):
        return emisor.get("nombre")
    return None


def _extraer_nombre_receptor(datos: dict) -> Optional[str]:
    """
    Safely pulls the recipient name out of an extraction result.

    Args:
        datos: the extraction result dict.

    Returns:
        The recipient name, or None if not available.
    """
    receptor = datos.get("receptor")
    if isinstance(receptor, dict):
        return receptor.get("nombre")
    return None


def guardar_extraccion(filename: str, datos: dict) -> None:
    """
    Saves a single PDF extraction result to the historial collection.

    Args:
        filename: the cleaned filename of the uploaded PDF.
        datos: the structured extraction result dict from the AI.
    """
    try:
        momento_actual = datetime.now()
        db.collection(HISTORIAL_COLLECTION).document().set({
            "fecha": momento_actual.strftime("%d/%m/%Y %H:%M"),
            # Real datetime for reliable range filtering (e.g. "last 15
            # days"), stored alongside the display-only text field above.
            "fecha_timestamp": momento_actual,
            "filename": filename,
            "tipo": datos.get("tipo_documento"),
            "emisor": _extraer_nombre_emisor(datos),
            "receptor": _extraer_nombre_receptor(datos),
            "total": datos.get("total"),
            "moneda": datos.get("moneda"),
            "categoria": datos.get("categoria_gasto"),
            "num_items": len(datos.get("items") or []),
            "datos": datos
        })
    except Exception as e:
        print(f"[firestore_db] Error saving extraction for {filename}: {e}")

def guardar_lote(resultados: list) -> None:
    """
    Saves every successful document from a batch extraction to the
    historial collection. Failed documents (in "errores") are not saved,
    matching the previous SQLite behavior.

    Args:
        resultados: list of dicts, each with "filename" and "datos" keys.
    """
    try:
        # Firestore batches let you write multiple documents in one
        # network round trip, which is both faster and safer than
        # looping with individual .set() calls for large batches.
        batch = db.batch()
        momento_actual = datetime.now()
        fecha_actual = momento_actual.strftime("%d/%m/%Y %H:%M")

        for resultado in resultados:
            datos = resultado.get("datos", {})
            doc_ref = db.collection(HISTORIAL_COLLECTION).document()
            batch.set(doc_ref, {
                "fecha": fecha_actual,
                # Real datetime for reliable range filtering, stored
                # alongside the display-only text field above.
                "fecha_timestamp": momento_actual,
                "filename": resultado.get("filename", ""),
                "tipo": datos.get("tipo_documento"),
                "emisor": _extraer_nombre_emisor(datos),
                "receptor": _extraer_nombre_receptor(datos),
                "total": datos.get("total"),
                "moneda": datos.get("moneda"),
                "categoria": datos.get("categoria_gasto"),
                "num_items": len(datos.get("items") or []),
                "datos": datos
            })

        batch.commit()
    except Exception as e:
        print(f"[firestore_db] Error saving batch: {e}")


def obtener_historial(limite: int = 50, busqueda: Optional[str] = None) -> list:
    """
    Returns the most recent historial entries, most recent first.

    Args:
        limite: maximum number of entries to return.
        busqueda: optional text filter applied in Python against
            filename and emisor, since Firestore has no native
            case-insensitive "LIKE" search.

    Returns:
        List of dicts with id, fecha, filename, tipo, emisor, total,
        moneda, num_items.
    """
    try:
        query = (
            db.collection(HISTORIAL_COLLECTION)
            .order_by("fecha", direction=firestore.Query.DESCENDING)
        )
        # Fetch more than needed when searching, since filtering happens
        # after retrieval — otherwise a search could return fewer than
        # "limite" matching results even if more exist further back.
        cantidad_a_traer = limite if not busqueda else max(limite * 5, 200)
        docs = query.limit(cantidad_a_traer).stream()

        registros = []
        busqueda_lower = busqueda.lower() if busqueda else None

        for doc in docs:
            data = doc.to_dict()
            filename = data.get("filename", "") or ""
            emisor = data.get("emisor", "") or ""

            if busqueda_lower:
                coincide = (
                    busqueda_lower in filename.lower()
                    or busqueda_lower in emisor.lower()
                )
                if not coincide:
                    continue

            registros.append({
                "id": doc.id,
                "fecha": data.get("fecha", ""),
                "filename": filename,
                "tipo": data.get("tipo"),
                "emisor": emisor,
                "total": data.get("total"),
                "moneda": data.get("moneda"),
                "num_items": data.get("num_items", 0)
            })

            if len(registros) >= limite:
                break

        return registros
    except Exception as e:
        print(f"[firestore_db] Error listing historial: {e}")
        return []


def obtener_detalle(registro_id: str) -> Optional[dict]:
    """
    Returns the full extraction data for a single historial entry.

    Args:
        registro_id: the Firestore document id of the historial entry.

    Returns:
        Dict with "filename" and "datos" keys, or None if not found.
    """
    try:
        doc = db.collection(HISTORIAL_COLLECTION).document(registro_id).get()
        if not doc.exists:
            return None
        data = doc.to_dict()
        return {
            "filename": data.get("filename", ""),
            "datos": data.get("datos", {})
        }
    except Exception as e:
        print(f"[firestore_db] Error getting detail for {registro_id}: {e}")
        return None


def eliminar_registro(registro_id: str) -> None:
    """
    Deletes a single historial entry by id.

    Args:
        registro_id: the Firestore document id of the historial entry.
    """
    try:
        db.collection(HISTORIAL_COLLECTION).document(registro_id).delete()
    except Exception as e:
        print(f"[firestore_db] Error deleting historial entry {registro_id}: {e}")


def obtener_historial_completo() -> list:
    """
    Returns every historial entry with full extraction data, used to
    export the complete historial as an Excel file.

    Returns:
        List of dicts with filename, fecha, and datos.
    """
    try:
        docs = (
            db.collection(HISTORIAL_COLLECTION)
            .order_by("fecha", direction=firestore.Query.DESCENDING)
            .stream()
        )
        return [
            {
                "filename": doc.to_dict().get("filename", ""),
                "fecha": doc.to_dict().get("fecha", ""),
                "datos": doc.to_dict().get("datos", {})
            }
            for doc in docs
        ]
    except Exception as e:
        print(f"[firestore_db] Error getting full historial: {e}")
        return []


def obtener_metricas() -> dict:
    """
    Computes dashboard metrics: totals by issuer, by document type,
    and by expense category.

    Firestore has no native GROUP BY/SUM, so all historial documents
    are fetched once and aggregated here in Python. This is fine at
    the data volumes this app handles; if historial grows into the
    tens of thousands of documents, this should move to scheduled
    aggregation writes instead of computing on every dashboard load.

    Returns:
        Dict with total_docs, total_monto, por_tipo, por_emisor,
        por_categoria.
    """
    try:
        docs = list(db.collection(HISTORIAL_COLLECTION).stream())

        total_docs = len(docs)
        total_monto = 0.0
        por_tipo: dict = {}
        por_emisor: dict = {}
        por_categoria: dict = {}

        for doc in docs:
            data = doc.to_dict()
            total = data.get("total")
            monto = total if isinstance(total, (int, float)) else 0.0
            total_monto += monto

            tipo = data.get("tipo")
            if tipo:
                if tipo not in por_tipo:
                    por_tipo[tipo] = {"tipo": tipo, "cantidad": 0, "monto": 0.0}
                por_tipo[tipo]["cantidad"] += 1
                por_tipo[tipo]["monto"] += monto

            emisor = data.get("emisor")
            if emisor:
                if emisor not in por_emisor:
                    por_emisor[emisor] = {"emisor": emisor, "cantidad": 0, "monto": 0.0}
                por_emisor[emisor]["cantidad"] += 1
                por_emisor[emisor]["monto"] += monto

            categoria = data.get("categoria")
            if categoria:
                if categoria not in por_categoria:
                    por_categoria[categoria] = {"categoria": categoria, "cantidad": 0, "monto": 0.0}
                por_categoria[categoria]["cantidad"] += 1
                por_categoria[categoria]["monto"] += monto

        lista_por_tipo = sorted(
            por_tipo.values(), key=lambda x: x["cantidad"], reverse=True
        )
        lista_por_emisor = sorted(
            por_emisor.values(), key=lambda x: x["monto"], reverse=True
        )[:10]
        lista_por_categoria = sorted(
            por_categoria.values(), key=lambda x: x["monto"], reverse=True
        )

        return {
            "total_docs": total_docs,
            "total_monto": total_monto,
            "por_tipo": lista_por_tipo,
            "por_emisor": lista_por_emisor,
            "por_categoria": lista_por_categoria
        }
    except Exception as e:
        print(f"[firestore_db] Error computing metrics: {e}")
        return {
            "total_docs": 0,
            "total_monto": 0.0,
            "por_tipo": [],
            "por_emisor": [],
            "por_categoria": []
        }


def buscar_precios_historicos_producto(
    emisor: str,
    clave_producto: str,
    excluir_registro_id: Optional[str] = None
) -> list:
    """
    Searches past historial entries from the same issuer for items
    matching the same product key, to support the price-change alert
    feature.

    Args:
        emisor: the issuer name to match.
        clave_producto: the composite product key built from
            categoria_producto + variante_especifica + material_o_marca.
        excluir_registro_id: optional historial id to skip (the current
            document being processed, so it doesn't compare against itself).

    Returns:
        List of historical unit prices (floats) found for that product.
    """
    try:
        query = (
            db.collection(HISTORIAL_COLLECTION)
            .where("emisor", "==", emisor)
            .order_by("fecha", direction=firestore.Query.DESCENDING)
            .limit(100)
        )
        docs = query.stream()

        precios = []
        for doc in docs:
            if excluir_registro_id and doc.id == excluir_registro_id:
                continue

            data = doc.to_dict()
            datos = data.get("datos", {})
            items = datos.get("items") or []

            for item in items:
                categoria = item.get("categoria_producto", "")
                variante = item.get("variante_especifica", "")
                material = item.get("material_o_marca", "")
                clave_item = f"{categoria}|{variante}|{material}"

                if clave_item == clave_producto:
                    precio = item.get("precio_unitario")
                    if isinstance(precio, (int, float)):
                        precios.append(precio)

        return precios
    except Exception as e:
        print(f"[firestore_db] Error searching historical prices: {e}")
        return []
        


def obtener_historial_por_rango(dias: int) -> list:
    """
    Returns every historial entry from the last N days, based on the
    real fecha_timestamp field (not the display-only text field).

    Documents saved before fecha_timestamp existed (see Bloque 22)
    will not appear here, since they have no timestamp to compare
    against.

    Args:
        dias: how many days back to include (e.g. 7, 15, 30, 60).

    Returns:
        List of dicts with filename, fecha, and datos — same shape as
        obtener_historial_completo(), ready to feed into the existing
        Excel/Sheets batch export functions.
    """
    try:
        fecha_limite = datetime.now() - timedelta(days=dias)

        query = (
            db.collection(HISTORIAL_COLLECTION)
            .where("fecha_timestamp", ">=", fecha_limite)
            .order_by("fecha_timestamp", direction=firestore.Query.DESCENDING)
        )
        docs = query.stream()

        return [
            {
                "filename": doc.to_dict().get("filename", ""),
                "fecha": doc.to_dict().get("fecha", ""),
                "datos": doc.to_dict().get("datos", {})
            }
            for doc in docs
        ]
    except Exception as e:
        print(f"[firestore_db] Error getting historial by range ({dias} days): {e}")
        return []

