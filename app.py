# app.py
from modules.db_historial import (
    inicializar_db, guardar_extraccion, guardar_lote,
    obtener_historial, obtener_detalle, eliminar_registro
)
from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for, flash
from dotenv import load_dotenv
import os
import re
from datetime import datetime
from modules.pdf_reader import extraer_texto_pdf
from modules.ai_extractor import extraer_datos
from modules.excel_generator import generar_excel
from modules.excel_generator import generar_excel, generar_excel_batch
from modules.sheets_exporter import (
    exportar_a_sheets, exportar_lote_a_sheets, credentials_disponibles
)

from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_bcrypt import Bcrypt
from modules.db_historial import (
    inicializar_db, guardar_extraccion, guardar_lote,
    obtener_historial, obtener_detalle, eliminar_registro,
    inicializar_usuarios, crear_usuario, buscar_usuario_por_username,
    buscar_usuario_por_id, obtener_todos_usuarios, eliminar_usuario
)




load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "clave_secreta_extractor_2026")
bcrypt = Bcrypt(app)

login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Inicia sesion para acceder."

@login_manager.user_loader
def load_user(user_id):
    return buscar_usuario_por_id(int(user_id))

UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True) 
inicializar_db()
inicializar_usuarios()
def crear_admin_inicial():
    admin = buscar_usuario_por_username("admin")
    if not admin:
        password_hash = bcrypt.generate_password_hash("admin1234").decode("utf-8")
        crear_usuario("admin", password_hash, rol="admin")
        print(">>> Admin creado: usuario=admin contrasena=admin1234")

crear_admin_inicial()

ALLOWED_EXTENSIONS = {"pdf"}

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route("/")
@login_required
def index():
    return render_template("index.html")


@app.route("/extract", methods=["POST"])
@login_required
def extract():
    if "file" not in request.files:
        return jsonify({"error": "No se recibió ningún archivo"}), 400

    file = request.files["file"]

    if file.filename == "" or not allowed_file(file.filename):
        return jsonify({"error": "Solo se aceptan archivos PDF"}), 400

    filename_clean = re.sub(r'[^a-zA-Z0-9._-]', '_', file.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename_clean)
    file.save(filepath)

    try:
        # Paso 1: extraer texto del PDF
        resultado_pdf = extraer_texto_pdf(filepath)

        if not resultado_pdf["texto_completo"].strip():
            return jsonify({"error": "El PDF no contiene texto extraíble. Puede ser una imagen escaneada."}), 400

        # Paso 2: la IA extrae los datos estructurados
        resultado_ia = extraer_datos(resultado_pdf["texto_completo"])

        if not resultado_ia["exito"]:
            return jsonify({"error": "La IA no pudo extraer datos estructurados.", "detalle": resultado_ia.get("error")}), 500

        datos = resultado_ia["datos"]
        guardar_extraccion(filename_clean, datos)

        return jsonify({
            "exito": True,
            "filename": filename_clean,
            "num_paginas": resultado_pdf["num_paginas"],
            "datos": datos
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/download/excel", methods=["POST"])
@login_required
def download_excel():
    data = request.get_json()
    if not data or "datos" not in data:
        return jsonify({"error": "No se recibieron datos"}), 400

    try:
        buffer = generar_excel(data["datos"])
        nombre = f"extraccion_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        return send_file(
            buffer,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=nombre
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/extract/batch", methods=["POST"])
@login_required
def extract_batch():
    if "files" not in request.files:
        return jsonify({"error": "No se recibieron archivos"}), 400

    files = request.files.getlist("files")
    
    # Filtrar solo PDFs válidos
    archivos_validos = [f for f in files if f.filename.lower().endswith(".pdf")]
    
    if not archivos_validos:
        return jsonify({"error": "Ningún archivo PDF válido recibido"}), 400

    if len(archivos_validos) > 500:
        return jsonify({"error": "Máximo 500 archivos por lote"}), 400

    resultados = []
    errores = []

    for file in archivos_validos:
        filename_clean = re.sub(r'[^a-zA-Z0-9._-]', '_', file.filename)
        filepath = os.path.join(UPLOAD_FOLDER, filename_clean)
        file.save(filepath)

        try:
            resultado_pdf = extraer_texto_pdf(filepath)

            if not resultado_pdf["texto_completo"].strip():
                errores.append({
                    "filename": filename_clean,
                    "error": "PDF sin texto extraíble (posible imagen escaneada)"
                })
                continue

            resultado_ia = extraer_datos(resultado_pdf["texto_completo"])

            if not resultado_ia["exito"]:
                errores.append({
                    "filename": filename_clean,
                    "error": resultado_ia.get("error", "Error de extracción")
                })
                continue

            resultados.append({
                "filename": filename_clean,
                "num_paginas": resultado_pdf["num_paginas"],
                "datos": resultado_ia["datos"]
            })

        except Exception as e:
            errores.append({"filename": filename_clean, "error": str(e)})

    guardar_lote(archivos_validos, resultados, errores)

    return jsonify({
        "exito": True,
        "total_procesados": len(resultados),
        "total_errores": len(errores),
        "resultados": resultados,
        "errores": errores
    })


@app.route("/download/excel/batch", methods=["POST"])
@login_required
def download_excel_batch():
    data = request.get_json()
    if not data or "resultados" not in data:
        return jsonify({"error": "No se recibieron datos"}), 400

    try:
        buffer = generar_excel_batch(data["resultados"])
        nombre = f"lote_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        return send_file(
            buffer,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=nombre
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/historial", methods=["GET"])
@login_required
def get_historial():
    busqueda = request.args.get("q", "").strip()
    registros = obtener_historial(limite=50, busqueda=busqueda if busqueda else None)
    return jsonify(registros)


@app.route("/historial/<int:registro_id>", methods=["GET"])
@login_required
def get_detalle_historial(registro_id):
    detalle = obtener_detalle(registro_id)
    if not detalle:
        return jsonify({"error": "Registro no encontrado"}), 404
    return jsonify(detalle)


@app.route("/historial/<int:registro_id>", methods=["DELETE"])
@login_required
def delete_historial(registro_id):
    eliminar_registro(registro_id)
    return jsonify({"ok": True})



@app.route("/export/sheets", methods=["POST"])
@login_required
def export_sheets():
    data = request.get_json()
    if not data or "datos" not in data:
        return jsonify({"error": "No se recibieron datos"}), 400
    if not credentials_disponibles():
        return jsonify({"error": "Google Sheets no configurado en este servidor"}), 503
    try:
        resultado = exportar_a_sheets(
            datos=data["datos"],
            filename=data.get("filename", "documento"),
            sheet_url=data.get("sheet_url")
        )
        return jsonify(resultado)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/export/sheets/batch", methods=["POST"])
@login_required
def export_sheets_batch():
    data = request.get_json()
    if not data or "resultados" not in data:
        return jsonify({"error": "No se recibieron datos"}), 400
    if not credentials_disponibles():
        return jsonify({"error": "Google Sheets no configurado"}), 503
    try:
        resultado = exportar_lote_a_sheets(
            resultados=data["resultados"],
            sheet_url=data.get("sheet_url"),
            nombre_lote=data.get("nombre_lote")
        )
        return jsonify(resultado)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/dashboard")
@login_required
def dashboard():
    from modules.db_historial import obtener_metricas
    metricas = obtener_metricas()
    return render_template("dashboard.html", metricas=metricas)


# ── AUTENTICACIÓN ──────────────────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        usuario = buscar_usuario_por_username(username)
        if usuario and bcrypt.check_password_hash(usuario.password_hash, password):
            login_user(usuario)
            return redirect(url_for("index"))
        else:
            flash("Usuario o contrasena incorrectos.")
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


# ── PANEL DE ADMIN ─────────────────────────────────────────────────────────────

@app.route("/admin")
@login_required
def admin():
    if not current_user.es_admin():
        return redirect(url_for("index"))
    usuarios = obtener_todos_usuarios()
    return render_template("admin.html", usuarios=usuarios)


@app.route("/admin/crear-usuario", methods=["POST"])
@login_required
def crear_usuario_route():
    if not current_user.es_admin():
        return redirect(url_for("index"))
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    rol = request.form.get("rol", "usuario")
    if not username or not password:
        flash("Usuario y contrasena son obligatorios.")
        return redirect(url_for("admin"))
    password_hash = bcrypt.generate_password_hash(password).decode("utf-8")
    exito = crear_usuario(username, password_hash, rol)
    if exito:
        flash(f"Usuario '{username}' creado correctamente.")
    else:
        flash(f"El usuario '{username}' ya existe.")
    return redirect(url_for("admin"))


@app.route("/admin/eliminar-usuario/<int:user_id>", methods=["POST"])
@login_required
def eliminar_usuario_route(user_id):
    if not current_user.es_admin():
        return redirect(url_for("index"))
    if user_id == current_user.id:
        flash("No puedes eliminar tu propia cuenta.")
        return redirect(url_for("admin"))
    eliminar_usuario(user_id)
    flash("Usuario eliminado.")
    return redirect(url_for("admin"))


if __name__ == "__main__":
    app.run(debug=True, port=5000)