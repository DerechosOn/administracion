# -*- coding: utf-8 -*-
"""Derechos On — Página web jurídica.

Registro de clientes, consulta del estado de sus procesos,
sección de noticias y áreas de atención jurídica actualizables.
"""

import os
import csv
import re
import math
import time
import json
import base64
import threading
import html as html_mod
import uuid
import calendar as calendario_py
from datetime import datetime, timezone, date, timedelta
from functools import wraps

from io import BytesIO, StringIO

from flask import (Flask, Response, abort, flash, g, jsonify, redirect, render_template, request,
                   send_file, send_from_directory, session, url_for, stream_with_context)
from werkzeug.security import check_password_hash, generate_password_hash

import requests as _requests

import db
import informe
import ramajudicial
import redes
import html_seguro
import ia_juridica
import conocimiento_juridico
import motor_normativo
import crm_core
try:
    from agentes import agente_jarvis
except Exception:
    agente_jarvis = None
try:
    from agentes import agente_iat
except Exception:
    agente_iat = None
import webmail
import contrato_docx
import tarifas_conalbos
import numeracion_tarifario
MARCA_DERECHOS_ON = numeracion_tarifario.MARCA_DERECHOS_ON

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Carpeta de datos. Con DATA_DIR (p. ej. disco persistente) las subidas y la
# base de datos viven ahí; sin ella, junto al código.
DATA_DIR = (os.environ.get("DATA_DIR") or BASE_DIR).strip() or BASE_DIR
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
ARTICULOS_IMG_DIR = os.path.join(BASE_DIR, "static", "img", "articulos")
os.makedirs(ARTICULOS_IMG_DIR, exist_ok=True)
EQUIPO_DIR = os.path.join(BASE_DIR, "static", "img", "equipo")
os.makedirs(EQUIPO_DIR, exist_ok=True)
SLIDES_DIR = os.path.join(BASE_DIR, "static", "img", "slides")
os.makedirs(SLIDES_DIR, exist_ok=True)

EXTENSIONES_PERMITIDAS = {".pdf", ".doc", ".docx", ".jpg", ".jpeg", ".png"}
EXTENSIONES_IMAGEN = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "derechos-on-clave-segura-de-sesion")
app.config["JSON_AS_ASCII"] = False
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024


MESES_ES = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
            "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


@app.template_filter("fecha_es")
def fecha_es(valor):
    """Formatea una fecha/hora 'YYYY-MM-DD[ HH:MM]' en español."""
    if not valor:
        return ""
    texto = str(valor).strip()
    dto = None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            dto = datetime.strptime(texto, fmt)
            break
        except ValueError:
            continue
    if dto is None:
        return texto
    mes = MESES_ES[dto.month - 1]
    if dto.hour or dto.minute:
        return "%d de %s de %d, %02d:%02d" % (dto.day, mes, dto.year, dto.hour, dto.minute)
    return "%d de %s de %d" % (dto.day, mes, dto.year)


def _fecha_larga_es(dto):
    return "%d de %s de %d" % (dto.day, MESES_ES[dto.month - 1], dto.year)


@app.template_filter("estado_clase")
def estado_clase(estado):
    mapa = {
        "Trámite inicial": "tramite",
        "En estudio": "estudio",
        "Audiencia programada": "audiencia",
        "En apelación": "apelacion",
        "Resuelto a favor": "favor",
        "Resuelto en contra": "contra",
        "Archivado": "archivado",
    }
    return mapa.get(estado, "tramite")


# Etapas del proceso (para la línea de avance y los gráficos del portal).
ETAPAS_PROCESO = ["Radicación", "Estudio", "Audiencia", "Fallo", "Cierre"]

_AVANCE_ESTADO = {
    "Trámite inicial": 15,
    "En estudio": 40,
    "Audiencia programada": 65,
    "En apelación": 82,
    "Resuelto a favor": 100,
    "Resuelto en contra": 100,
    "Archivado": 100,
}

_ETAPA_ESTADO = {
    "Trámite inicial": 0,
    "En estudio": 1,
    "Audiencia programada": 2,
    "En apelación": 3,
    "Resuelto a favor": 4,
    "Resuelto en contra": 4,
    "Archivado": 4,
}


def avance_proceso(estado):
    return _AVANCE_ESTADO.get(estado, 15)


def etapa_proceso(estado):
    return _ETAPA_ESTADO.get(estado, 0)


def _enriquecer_procesos(procesos):
    """Añade a cada proceso su % de avance, etapa y tono para las gráficas."""
    salida = []
    for p in procesos:
        d = dict(p)
        d["avance"] = _AVANCE_ESTADO.get(p["estado"], 15)
        d["etapa_idx"] = _ETAPA_ESTADO.get(p["estado"], 0)
        d["clase"] = estado_clase(p["estado"])
        salida.append(d)
    return salida


# Paleta de colores inspirada en la vista predeterminada de Power BI.
_BI_COLORES = {
    "Trámite inicial": "#118DFF",
    "En estudio": "#12239E",
    "Audiencia programada": "#E66C37",
    "En apelación": "#6B007B",
    "Resuelto a favor": "#0F9D63",
    "Resuelto en contra": "#D64550",
    "Archivado": "#8C8C8C",
}


def _resumen_estados(procesos):
    """Distribución de procesos por estado para el anillo estilo Power BI."""
    conteo = {}
    for p in procesos:
        conteo[p["estado"]] = conteo.get(p["estado"], 0) + 1
    claves = [e for e in db.ESTADOS_PROCESO if e in conteo] + \
             [e for e in conteo if e not in db.ESTADOS_PROCESO]
    total = sum(conteo.values()) or 1
    filas, acc = [], 0.0
    for e in claves:
        c = conteo[e]
        pct = c / total * 100
        filas.append({"estado": e, "n": c, "pct": round(pct, 1),
                      "start": round(acc, 2),
                      "color": _BI_COLORES.get(e, "#8C8C8C")})
        acc += pct
    return filas


ICONOS_SVG = {
    "scale": '<path d="M12 3v18M5 21h14M6 7l-3 6a3 3 0 0 0 6 0L6 7zm12 0l-3 6a3 3 0 0 0 6 0l-3-6zM12 3l-2 4M12 3l2 4"/>',
    "book": '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20V2H6.5A2.5 2.5 0 0 0 4 4.5v15zM4 19.5A2.5 2.5 0 0 0 6.5 22H20v-5"/>',
    "users": '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
    "briefcase": '<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/><path d="M12 13v.01M2 9h20"/>',
    "gavel": '<path d="M14 13l-8.5 8.5a2.12 2.12 0 0 1-3-3L11 10M16 16l5-5M4 20l3.5-3.5M20 4l-8.5 8.5M18 6l-3-3 5-1 1 5-3-1z"/>',
    "chart": '<path d="M18 20V10M12 20V4M6 20v-6"/>',
    "building": '<path d="M3 21h18M5 21V7a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v14M9 7h6M9 11h6M9 15h6M9 19h6"/>',
    "shield": '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
    "star": '<path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01z"/>',
    "mail": '<path d="M4 4h16a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z"/><path d="M22 6l-10 7L2 6"/>',
    "phone": '<path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6A19.79 19.79 0 0 1 2.08 4.18 2 2 0 0 1 4.06 2h3a2 2 0 0 1 2 1.72c.13.96.36 1.9.7 2.81a2 2 0 0 1-.45 2.11L8 10a16 16 0 0 0 6 6l1.35-1.35a2 2 0 0 1 2.11-.45c.91.34 1.85.57 2.81.7A2 2 0 0 1 22 16.92z"/>',
}


@app.template_filter("icono_svg")
def icono_svg(nombre):
    ruta = ICONOS_SVG.get(nombre, ICONOS_SVG["scale"])
    return ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
            'width="24" height="24">' + ruta + "</svg>")


# ---------------------------------------------------------------- helpers
def requiere_cliente(funcion):
    @wraps(funcion)
    def envoltura(*args, **kwargs):
        g.usuario = db.usuario_por_id(session.get("uid"))
        if not g.usuario or g.usuario["rol"] != "cliente":
            return redirect(url_for("login"))
        return funcion(*args, **kwargs)
    return envoltura


def requiere_admin(funcion):
    @wraps(funcion)
    def envoltura(*args, **kwargs):
        g.usuario = db.usuario_por_id(session.get("uid"))
        if not g.usuario or g.usuario["rol"] != "admin":
            return redirect(url_for("login"))
        return funcion(*args, **kwargs)
    return envoltura


def requiere_usuario(funcion):
    @wraps(funcion)
    def envoltura(*args, **kwargs):
        g.usuario = db.usuario_por_id(session.get("uid"))
        if not g.usuario or g.usuario["rol"] not in ("cliente", "admin"):
            return redirect(url_for("login"))
        return funcion(*args, **kwargs)
    return envoltura


def requiere_abogado(funcion):
    @wraps(funcion)
    def envoltura(*args, **kwargs):
        g.usuario = db.usuario_por_id(session.get("uid"))
        if not g.usuario or g.usuario["rol"] != "abogado":
            return redirect(url_for("login"))
        g.abogado = db.abogado_por_correo(g.usuario["email"])
        if not g.abogado or not g.abogado["activo"]:
            session.clear()
            flash("Tu cuenta de abogado no está activa. Contacta a la administración.", "error")
            return redirect(url_for("login"))
        return funcion(*args, **kwargs)
    return envoltura


def es_asociacion(usuario):
    return bool(usuario) and usuario["rol"] == "cliente" and \
        usuario.get("tipo_persona") == "asociacion"


def requiere_asociacion(funcion):
    @wraps(funcion)
    def envoltura(*args, **kwargs):
        g.usuario = db.usuario_por_id(session.get("uid"))
        if not es_asociacion(g.usuario):
            return redirect(url_for("login"))
        return funcion(*args, **kwargs)
    return envoltura


def _id_sesion():
    if "vid" not in session:
        session["vid"] = uuid.uuid4().hex[:12]
    return session["vid"]


def _registrar_interaccion(tipo, detalle="", pagina=""):
    try:
        db.interaccion_crear(tipo, detalle=detalle[:200], pagina=pagina,
                             sesion=_id_sesion())
    except Exception:
        pass


def _contar(sql, params=()):
    filas = db.consultar(sql, params)
    return filas[0]["n"] if filas else 0


def guardar_imagen_articulo(archivo):
    """Guarda una imagen de artículo y devuelve (nombre_archivo, error)."""
    if not archivo or not archivo.filename:
        return "", None
    original = os.path.basename(archivo.filename.replace("\\", "/"))
    ext = os.path.splitext(original)[1].lower()
    if ext not in EXTENSIONES_IMAGEN:
        return None, "Formato de imagen no permitido. Use JPG, PNG, WEBP o GIF."
    nombre = uuid.uuid4().hex + ext
    archivo.save(os.path.join(ARTICULOS_IMG_DIR, nombre))
    return nombre, None


def borrar_imagen_articulo(nombre):
    if nombre:
        try:
            os.remove(os.path.join(ARTICULOS_IMG_DIR, nombre))
        except OSError:
            pass


def usuario_actual():
    return db.usuario_por_id(session.get("uid"))


def destino_segun_rol(usuario):
    if usuario["rol"] == "admin":
        return url_for("panel_admin")
    if usuario["rol"] == "abogado":
        return url_for("abogado_inicio")
    if es_asociacion(usuario):
        return url_for("asociacion_inicio")
    return url_for("cliente_inicio")


def fecha_parse(fecha_str):
    """Devuelve un objeto date o None si la cadena no es YYYY-MM-DD."""
    try:
        return datetime.strptime(fecha_str[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def dias_restantes(fecha_str):
    """Días hasta la fecha (negativo si ya pasó)."""
    d = fecha_parse(fecha_str)
    if d is None:
        return None
    return (d - date.today()).days


def _domingo_pascua(anyo):
    """Fecha del Domingo de Resurrección (algoritmo gregoriano)."""
    a, b, c = anyo % 19, anyo // 100, anyo % 100
    d = (19 * a + b - b // 4 - ((b - (b + 8) // 25 + 1) // 3) + 15) % 30
    e = (2 * (b % 4) + 2 * (c // 4) - d - (c % 4) + 35) % 7
    mes = (d + e + 81) // 25
    dia = (d + e + 19 * mes + 3) % 32
    return date(anyo, mes, dia)


def _al_lunes(d):
    """Traslada una fecha a su lunes siguiente (Ley Emiliani)."""
    return d + timedelta(days=(0 - d.weekday()) % 7)


def festivos_colombia(anyo):
    """Conjunto de festivos nacionales de Colombia para un año."""
    pascua = _domingo_pascua(anyo)
    fijos = [(1, 1), (5, 1), (7, 20), (8, 7), (12, 8), (12, 25)]
    trasladables = [(1, 6), (3, 19), (6, 29), (8, 15), (10, 12),
                    (11, 1), (11, 11)]
    fiestas = {date(anyo, m, d) for m, d in fijos}
    fiestas.add(pascua - timedelta(days=3))   # Jueves Santo
    fiestas.add(pascua - timedelta(days=2))   # Viernes Santo
    fiestas.add(_al_lunes(pascua + timedelta(days=39)))   # Ascensión
    fiestas.add(_al_lunes(pascua + timedelta(days=60)))   # Corpus
    fiestas.add(_al_lunes(pascua + timedelta(days=68)))   # Sagrado Corazón
    for m, d in trasladables:
        fiestas.add(_al_lunes(date(anyo, m, d)))
    return fiestas


def _es_dia_habil(d):
    return d.weekday() < 5 and d not in festivos_colombia(d.year)


def _hora_a_min(hhmm):
    try:
        h, m = hhmm.split(":")
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return None


def _slot_libre(hhmm, eventos):
    """¿La franja [hhmm, hhmm+60) está libre frente a los eventos?."""
    inicio = _hora_a_min(hhmm)
    if inicio is None:
        return False
    fin = inicio + 60
    for ev in eventos:
        e_inicio = _hora_a_min(ev["hora"])
        e_fin = _hora_a_min(ev["hora_fin"] or ev["hora"])
        if e_inicio is None or e_fin is None:
            continue
        if e_inicio < fin and e_fin > inicio:
            return False
    return True


def _bloqueos_de_abogado(abogado_id, fecha):
    """Franjas ocupadas de un abogado en una fecha: su agenda + citas asignadas."""
    bloqueos = []
    for e in db.actividades_en_fecha(fecha.isoformat()):
        if e.get("abogado_id") == abogado_id:
            bloqueos.append({"hora": e["hora"],
                             "hora_fin": e.get("hora_fin") or e["hora"]})
    for c in db.citas_en_fecha(fecha.isoformat()):
        if c.get("abogado_id") == abogado_id:
            bloqueos.append({"hora": c["hora"], "hora_fin": c["hora"]})
    return bloqueos


def _abogado_libre(fecha, hora):
    """Primer abogado activo con el horario libre en su agenda esa fecha."""
    ocupadas = {c["hora"] for c in db.citas_en_fecha(fecha.isoformat())}
    if hora in ocupadas:
        return None
    for ab in db.abogados_lista(activos=True):
        if _slot_libre(hora, _bloqueos_de_abogado(ab["id"], fecha)):
            return ab["id"]
    return None


def _horas_disponibles(fecha, abogado_id=None):
    """Horas libres según la agenda de los abogados (sus horarios no agendados).

    Sin abogados activos usa la disponibilidad general de la firma."""
    if fecha < date.today() or not _es_dia_habil(fecha):
        return []
    ocupadas = {c["hora"] for c in db.citas_en_fecha(fecha.isoformat())}
    if abogado_id is not None:
        return [h for h in HORAS_CITA
                if h not in ocupadas and _slot_libre(h, _bloqueos_de_abogado(abogado_id, fecha))]
    abogados = db.abogados_lista(activos=True)
    if not abogados:
        eventos = db.actividades_en_fecha(fecha.isoformat())
        return [h for h in HORAS_CITA
                if h not in ocupadas and _slot_libre(h, eventos)]
    return [h for h in HORAS_CITA
            if h not in ocupadas and any(
                _slot_libre(h, _bloqueos_de_abogado(ab["id"], fecha))
                for ab in abogados)]


def _dias_disponibles(limite=6, abogado_id=None):
    """Próximas fechas hábiles con al menos un horario libre."""
    dias = []
    actual = date.today() + timedelta(days=1)
    tope = date.today() + timedelta(days=45)
    while actual <= tope and len(dias) < limite:
        if _es_dia_habil(actual) and _horas_disponibles(actual, abogado_id):
            dias.append(actual)
        actual += timedelta(days=1)
    return dias


@app.context_processor
def inyectar_contexto():
    return {"now": datetime.now(), "C": db.contenido_todos()}


def _formato_cop(valor):
    """Formato monetario colombiano: $1.250.905 (punto de miles, sin decimales)."""
    try:
        numero = float(valor or 0)
    except (TypeError, ValueError):
        return "$0"
    negativo = numero < 0
    entero = int(math.floor(abs(numero) + 0.5))
    texto = f"{entero:,}".replace(",", ".")
    return ("-$" if negativo else "$") + texto


app.jinja_env.filters["cop"] = _formato_cop


# ---------------------------------------------------------------- público
# ---------------- telemetría pública (visitas e interacciones)
@app.route("/api/visita", methods=["POST"])
def api_visita():
    datos = request.get_json(silent=True) or {}
    try:
        if "visto" not in session:
            session["visto"] = True
            es_vuelta = 0
        else:
            es_vuelta = 1
        db.visita_crear(
            sesion=_id_sesion(),
            pagina=(datos.get("pagina") or "")[:120],
            dispositivo=(datos.get("dispositivo") or "")[:20],
            navegador=(datos.get("navegador") or "")[:60],
            es_vuelta=es_vuelta)
    except Exception:
        pass
    return Response(status=204)


@app.route("/api/evento", methods=["POST"])
def api_evento():
    datos = request.get_json(silent=True) or {}
    tipo = (datos.get("tipo") or "").strip()[:40]
    if tipo:
        _registrar_interaccion(
            tipo,
            detalle=(datos.get("detalle") or ""),
            pagina=(datos.get("pagina") or "")[:120])
    return Response(status=204)


@app.route("/")
def inicio():
    ruta_img = os.path.join("static", "img", "quienes.jpg")
    ruta_png = os.path.join("static", "img", "quienes.png")
    calis = db.consultar("SELECT calificacion FROM testimonios WHERE activo = 1")
    n_calis = len(calis)
    satisf = int(round(100.0 * sum(1 for c in calis if c["calificacion"] >= 4) / n_calis)) if n_calis else 0
    return render_template("index.html",
                           noticias=db.noticias_recientes(),
                           areas=db.areas_todas(),
                           stats_procesos=db.consultar(
                               "SELECT COUNT(*) AS n FROM procesos")[0]["n"],
                           stats_satisfaccion=satisf,
                           secciones=db.secciones_activas(),
                           testimonios=db.testimonios_activos(),
                           img_quienes=("jpg" if os.path.exists(ruta_img)
                                        else "png" if os.path.exists(ruta_png) else None),
                           usuario=usuario_actual())


SERVICIOS_REGISTRO = [
    "Consulta inicial",
    "Contrato de representación",
    "Honorarios por proceso",
    "Redacción de documentos",
    "Audiencia / diligencia",
    "Mensualidad (plan)",
    "Conciliación extrajudicial",
    "Otro",
]


CONTRATO_PLANTILLA_CLAVE = "contrato_plantilla"

CONTRATO_CAMPOS = [
    ("%(nombre)s", "Nombre completo del cliente"),
    ("%(documento)s", "Documento de identidad del cliente"),
    ("%(email)s", "Correo electrónico del cliente"),
    ("%(telefono)s", "Teléfono del cliente"),
    ("%(servicio)s", "Tipo de servicio contratado"),
    ("%(numero)s", "Número del contrato (DO-AAAA-0000)"),
    ("%(ciudad)s", "Ciudad donde se firma"),
    ("%(dia)s", "Día de suscripción"),
    ("%(mes_nombre)s", "Mes de suscripción en letras"),
    ("%(año)s", "Año de suscripción"),
    ("%(despacho)s", "Nombre del despacho"),
    ("%(firmante_nombre)s", "Nombre del firmante autorizado"),
    ("%(firmante_cargo)s", "Cargo del firmante autorizado"),
]

CONTRATO_CLIENTE_MUESTRA = {
    "nombre": "María Fernanda Gómez Restrepo",
    "documento": "C.C. 1.019.283.471",
    "email": "correo@ejemplo.com",
    "telefono": "+57 310 555 0142",
}

_PLANTILLA_VAR = re.compile(r"%\(([^()%\s]+)\)s|\{\{\s*([^{}()%\s]+)\s*\}\}")

_CONTRATO_PLANTILLA_POR_DEFECTO = """
<h1>CONTRATO DE PRESTACIÓN DE SERVICIOS JURÍDICOS</h1>
<div class="ct-num">N.° %(numero)s</div>
<table class="ct-parte">
  <tr><td class="lbl">DESPACHO:</td><td><b>DERECHOS ON</b>, firma de abogados constituida conforme a las
  normas de la República de Colombia, con domicilio principal en %(ciudad)s.</td></tr>
  <tr><td class="lbl">CLIENTE:</td><td><b>%(nombre)s</b>, identificado(a) con %(documento)s,
  correo electrónico %(email)s y teléfono %(telefono)s.</td></tr>
</table>

<h2>1. OBJETO</h2>
<p>El presente contrato regula la prestación de servicios jurídicos que EL DESPACHO prestará
a EL CLIENTE, quien contrató el siguiente tipo de servicio: <b>«%(servicio)s»</b>.</p>

<h2>2. ALCANCE DE LA REPRESENTACIÓN</h2>
<p>EL DESPACHO prestará el servicio de forma independiente, técnica y profesional, de acuerdo con su
autonomía profesional conforme al artículo 28 de la Ley 1123 de 2007 (Código Disciplinario del Abogado),
sin que las instrucciones de EL CLIENTE puedan comprometer el ejercicio honesto y legal de la profesión.
El alcance detallado de labores, etapas y actuaciones específicas se definirá conforme al encargo y a la
naturaleza del servicio contratado.</p>

<h2>3. HONORARIOS Y FORMA DE PAGO</h2>
<p>Los honorarios por la prestación del servicio se pactarán por escrito conforme al valor acordado e
indicado en la propuesta comercial aceptada por EL CLIENTE, la cual hace parte integral de este contrato.
Los pagos se realizarán en la forma y oportunidad pactadas. En caso de que la normatividad aplicable lo
exija, los honorarios podrán ser regulados conforme a lo dispuesto en el artículo 19 de la Ley 1123 de 2007
y normas concordantes.</p>

<h2>4. MORA</h2>
<p>En caso de mora en el pago de las sumas adeudadas, se causarán intereses de mora a la tasa máxima
permitida por la ley, calculados conforme a la tasa de interés de usura certificada por la Superintendencia
Financiera de Colombia para el período correspondiente, sin perjuicio de las acciones legales a que haya
lugar. El incumplimiento persistente facultará a EL DESPACHO para suspender o terminar el presente contrato.</p>

<h2>5. OBLIGACIONES DE EL DESPACHO</h2>
<p>Son obligaciones de EL DESPACHO: guardar reserva profesional y secreto profesional respecto de la
información de EL CLIENTE (Ley 1123 de 2007, artículo 34); actuar con lealtad, diligencia y celo profesional;
informar oportunamente el estado de los asuntos a su cargo; y entregar a EL CLIENTE la documentación que
respalde las gestiones realizadas.</p>

<h2>6. OBLIGACIONES DE EL CLIENTE</h2>
<p>Son obligaciones de EL CLIENTE: suministrar información veraz y completa; proporcionar los documentos y
firmas necesarios para el trámite; cancelar oportunamente los honorarios, gastos y expensas del proceso; y
mantener actualizados sus datos de contacto.</p>

<h2>7. TRATAMIENTO DE DATOS PERSONALES</h2>
<p>En cumplimiento de la Ley 1581 de 2012 y del Decreto 1074 de 2015, EL CLIENTE autoriza a EL DESPACHO a
recolectar, almacenar, usar y circular sus datos personales y los de los terceros que suministre, exclusivamente
para el desarrollo de los servicios contratados, el cumplimiento de obligaciones legales y la comunicación
sobre el estado de sus trámites. EL CLIENTE podrá ejercer sus derechos de conocer, actualizar, rectificar,
suprimir y revocar la autorización comunicándose al correo institucional del despacho.</p>

<h2>8. MENSAJES DE DATOS Y VALIDEZ ELECTRÓNICA</h2>
<p>De conformidad con la Ley 527 de 1999, el presente contrato se genera, transmite, archiva y conserva por
medios electrónicos. EL CLIENTE reconoce que la creación de su cuenta, la aceptación de los presentes términos
y la confirmación del servicio contratado constituyen mensajes de datos con plena validez jurídica, fuerza
obligatoria y eficacia probatoria, equivaliendo a la firma manuscrita para todos los efectos de este contrato.
Las evidencias electrónicas (registros de acceso, correos y confirmaciones) se tendrán como prueba del
perfeccionamiento y contenido del presente acuerdo, conforme a los artículos 6.º y siguientes de la Ley 527 de 1999.</p>

<h2>9. CONFIDENCIALIDAD</h2>
<p>Las partes se obligan a mantener la reserva de la información intercambiada durante la ejecución del
servicio y a no revelarla a terceros sin autorización, salvo orden judicial o deber legal. Esta obligación
subsiste aún después de la terminación del presente contrato.</p>

<h2>10. DOCUMENTACIÓN Y PODERES</h2>
<p>Si el servicio contratado lo requiere, EL CLIENTE otorgará, mediante los documentos y poderes idóneos
conforme a la ley procesal aplicable (Código General del Proceso, Ley 1564 de 2012), la representación
necesaria para adelantar las actuaciones correspondientes ante las autoridades competentes.</p>

<h2>11. DURACIÓN Y TERMINACIÓN</h2>
<p>El presente contrato estará vigente mientras subsista el encargo y no sea terminado por las partes o por
la ejecución total del servicio. Cualquiera de las partes podrá terminarlo por escrito; en tal caso, EL CLIENTE
deberá cancelar los honorarios causados a la fecha y los gastos incurridos.</p>

<h2>12. LEY APLICABLE Y COMPETENCIA</h2>
<p>El presente contrato se rige por las leyes de la República de Colombia. Toda controversia será resuelta por
los jueces de la República, con sujeción a las normas de competencia territorial vigentes.</p>

<h2>ACEPTACIÓN</h2>
<p>Manifiesto que he leído y aceptado las cláusulas anteriores y, en consecuencia, declaro haber recibido
copia del presente documento en formato electrónico. Suscrito a los %(dia)s días del mes de %(mes_nombre)s
del año %(año)s.</p>

<p class="ct-nota">Documento generado electrónicamente conforme a la Ley 527 de 1999. Su impresión y archivo
no alteran su validez jurídica. N.° de referencia: %(numero)s.</p>
"""


def _plantilla_contrato():
    """Devuelve la plantilla vigente del cuerpo del contrato."""
    try:
        guardada = (db.contenido_todos().get(CONTRATO_PLANTILLA_CLAVE) or "").strip()
    except Exception:
        guardada = ""
    return guardada or _CONTRATO_PLANTILLA_POR_DEFECTO.strip()


def _datos_contrato(cliente, servicio, numero, ciudad="Bogotá D.C.", fecha=None):
    """Valores disponibles para las variables de la plantilla."""
    hoy = fecha or date.today()
    try:
        ajustes = db.contenido_todos()
    except Exception:
        ajustes = {}
    return {
        "numero": numero or "DO-%s-____" % hoy.strftime("%Y"),
        "ciudad": ciudad or "Bogotá D.C.",
        "nombre": cliente.get("nombre") or "—",
        "documento": cliente.get("documento") or "______________________",
        "email": cliente.get("email") or "—",
        "telefono": cliente.get("telefono") or "—",
        "servicio": servicio or "Servicios jurídicos en general",
        "dia": hoy.strftime("%d"),
        "mes_nombre": MESES_ES[hoy.month - 1],
        "año": hoy.strftime("%Y"),
        "despacho": "DERECHOS ON",
        "firmante_nombre": ajustes.get("contrato_firmante_nombre") or "DERECHOS ON",
        "firmante_cargo": ajustes.get("contrato_firmante_cargo")
        or "Firma autorizada del despacho",
    }


def _render_contrato(plantilla, datos):
    """Sustituye las variables del documento. Devuelve (html, variables_desconocidas)."""
    desconocidas = set()

    def _cambio(m):
        clave = m.group(1) or m.group(2)
        if clave in datos:
            return html_mod.escape(str(datos[clave]), quote=False)
        desconocidas.add(clave)
        return m.group(0)

    return _PLANTILLA_VAR.sub(_cambio, plantilla or ""), sorted(desconocidas)


def _contrato_html(cliente, servicio, numero, ciudad="Bogotá D.C.", fecha=None,
                   plantilla=None):
    """Genera el texto del contrato electrónico de prestación de servicios jurídicos."""
    texto = plantilla if plantilla is not None else _plantilla_contrato()
    if not (texto or "").strip():
        texto = _CONTRATO_PLANTILLA_POR_DEFECTO.strip()
    html, _ = _render_contrato(texto, _datos_contrato(cliente, servicio, numero, ciudad, fecha))
    return html


def _vista_previa_contrato(plantilla):
    """Renderiza la plantilla con datos de ejemplo para revisarla en el administrador."""
    return _render_contrato(plantilla or _plantilla_contrato(),
                            _datos_contrato(CONTRATO_CLIENTE_MUESTRA,
                                            "Representación judicial",
                                            "DO-%s-0001" % date.today().strftime("%Y"),
                                            "Bogotá D.C."))


def _crear_contrato_cliente(usuario, servicio):
    """Crea el contrato electrónico del cliente y devuelve su id."""
    cid = db.contrato_crear({
        "cliente_id": usuario["id"], "servicio": servicio,
        "texto": _contrato_html(usuario, servicio, "")})
    numero = "DO-%s-%04d" % (datetime.now().year, cid)
    db.contrato_actualizar(cid, {
        "numero": numero,
        "texto": _contrato_html(usuario, servicio, numero)})
    return cid


def _retext_contratos():
    """Re-sincroniza el texto de los contratos SIN FIRMAR con la plantilla vigente.

    Un contrato ya firmado es un documento que el cliente y el despacho
    Revisaron y aceptaron: no se puede reescribir su texto. Por eso aqui solo
    se tocan los contratos nuevos o pendientes de firma.

    Devuelve (actualizados, saltados_por_estar_firmados).
    """
    filas = db.consultar(
        "SELECT ct.id, ct.numero, ct.servicio, ct.ciudad, ct.estado, ct.firmado_el, "
        "ct.firma_nombre, ct.firma_imagen, ct.texto, "
        "u.nombre, u.documento, u.email, u.telefono "
        "FROM contratos ct LEFT JOIN usuarios u ON u.id = ct.cliente_id")
    total = 0
    saltados = 0
    for f in filas:
        # cualquier rastro de firma significa que el contrato ya no se toca
        if (f.get("firmado_el") or f.get("firma_nombre")
                or f.get("firma_imagen")
                or str(f.get("estado") or "").strip().lower() == "firmado"):
            saltados += 1
            continue
        texto = _contrato_html(f, f["servicio"], f["numero"],
                               f["ciudad"] or "Bogotá D.C.")
        if (f.get("texto") or "") == texto:
            continue
        db.contrato_actualizar(f["id"], {"texto": texto})
        total += 1
    return total, saltados


@app.route("/registro", methods=["GET", "POST"])
def registro():
    if usuario_actual():
        return redirect(destino_segun_rol(usuario_actual()))
    return render_template("registro.html", usuario=usuario_actual())


@app.route("/registro_persona", methods=["GET", "POST"])
def registro_persona():
    if usuario_actual():
        return redirect(destino_segun_rol(usuario_actual()))
    error = None
    if request.method == "POST":
        nombre = (request.form.get("nombre_natural") or "").strip()
        email = (request.form.get("email_natural") or "").strip().lower()
        telefono = (request.form.get("telefono_natural") or "").strip()
        documento = (request.form.get("documento_natural") or "").strip()
        tipo_doc = (request.form.get("tipo_doc_natural") or "CC")
        direccion = (request.form.get("direccion_natural") or "").strip()
        ciudad = (request.form.get("ciudad_natural") or "").strip()
        clave = (request.form.get("clave") or "")
        clave2 = (request.form.get("clave2") or "")
        tipo_servicio = (request.form.get("tipo_servicio") or "").strip()

        if not nombre or not email or not telefono or not documento or not clave or not tipo_servicio:
            error = "Complete los campos obligatorios."
        elif "@" not in email:
            error = "Correo inválido."
        elif len(clave) < 6:
            error = "La contraseña debe tener al menos 6 caracteres."
        elif clave != clave2:
            error = "Las contraseñas no coinciden."
        elif db.usuario_por_email(email):
            error = "Ya existe una cuenta con ese correo electrónico."
        else:
            datos_extra = {"tipo_persona": "natural", "tipo_documento": tipo_doc,
                           "direccion": direccion, "ciudad": ciudad}
            uid = db.ejecutar(
                "INSERT INTO usuarios (nombre, email, password_hash, rol, telefono, documento, tipo_servicio, activo, fecha_registro, datos_extra, tipo_persona) "
                "VALUES (?, ?, ?, 'cliente', ?, ?, ?, 1, ?, ?, 'natural')",
                (nombre, email, generate_password_hash(clave),
                 telefono, documento, tipo_servicio,
                 datetime.now().strftime("%Y-%m-%d %H:%M"),
                 json.dumps(datos_extra, ensure_ascii=False))
            )
            _crear_contrato_cliente(
                {"id": uid, "nombre": nombre, "documento": documento,
                 "email": email, "telefono": telefono},
                tipo_servicio)
            _registrar_interaccion("registro", detalle="natural · " + nombre)
            flash("Registro exitoso. Ya puedes iniciar sesión.", "exito")
            return redirect(url_for("login"))
    return render_template("registro_persona.html", usuario=usuario_actual(), error=error,
                           servicios=SERVICIOS_REGISTRO)


@app.route("/registro_empresa", methods=["GET", "POST"])
def registro_empresa():
    if usuario_actual():
        return redirect(destino_segun_rol(usuario_actual()))
    error = None
    if request.method == "POST":
        razon_social = (request.form.get("razon_social") or "").strip()
        sigla = (request.form.get("sigla") or "").strip()
        nit = (request.form.get("nit") or "").strip()
        tipo_sociedad = (request.form.get("tipo_sociedad") or "").strip()
        matricula_cc = (request.form.get("matricula_cc") or "").strip()
        fecha_constitucion = (request.form.get("fecha_constitucion") or "").strip()
        ultimo_ano_renovado = (request.form.get("ultimo_ano_renovado") or "").strip()
        direccion_empresa = (request.form.get("direccion_empresa") or "").strip()
        ciudad_empresa = (request.form.get("ciudad_empresa") or "").strip()
        telefono_empresa = (request.form.get("telefono_empresa") or "").strip()
        email_empresa = (request.form.get("email_empresa") or "").strip().lower()
        rep_legal_nombre = (request.form.get("rep_legal_nombre") or "").strip()
        rep_legal_tipo_doc = (request.form.get("rep_legal_tipo_doc") or "CC")
        rep_legal_documento = (request.form.get("rep_legal_documento") or "").strip()
        rep_legal_cargo = (request.form.get("rep_legal_cargo") or "").strip()
        rues_numero = (request.form.get("rues_numero") or "").strip()
        rues_fecha_inscripcion = (request.form.get("rues_fecha_inscripcion") or "").strip()
        rues_fecha_renovacion = (request.form.get("rues_fecha_renovacion") or "").strip()
        ciiu_principal = (request.form.get("ciiu_principal") or "").strip()
        ciiu_secundarias = (request.form.get("ciiu_secundarias") or "").strip()
        rues_regimen = (request.form.get("rues_regimen") or "").strip()
        tamano_empresa = (request.form.get("tamano_empresa") or "").strip()
        rues_estado = (request.form.get("rues_estado") or "").strip()
        clave = (request.form.get("clave") or "")
        clave2 = (request.form.get("clave2") or "")
        tipo_servicio = (request.form.get("tipo_servicio") or "").strip()

        email = email_empresa
        telefono = telefono_empresa
        documento = nit
        nombre = razon_social

        if (not razon_social or not email or not clave or not tipo_servicio or
                not nit or not matricula_cc or not fecha_constitucion or
                not direccion_empresa or not ciudad_empresa or not telefono_empresa or
                not rep_legal_nombre or not rep_legal_documento or not rep_legal_cargo):
            error = "Complete los campos obligatorios de la empresa."
        elif "@" not in email:
            error = "Correo inválido."
        elif len(clave) < 6:
            error = "La contraseña debe tener al menos 6 caracteres."
        elif clave != clave2:
            error = "Las contraseñas no coinciden."
        elif db.usuario_por_email(email):
            error = "Ya existe una cuenta con ese correo electrónico."
        else:
            datos_extra = {
                "tipo_persona": "juridica",
                "razon_social": razon_social,
                "sigla": sigla,
                "nit": nit,
                "tipo_sociedad": tipo_sociedad,
                "camara_comercio": {
                    "matricula_cc": matricula_cc,
                    "fecha_constitucion": fecha_constitucion,
                    "ultimo_ano_renovado": ultimo_ano_renovado,
                    "direccion_empresa": direccion_empresa,
                    "ciudad_empresa": ciudad_empresa,
                    "telefono_empresa": telefono_empresa,
                    "email_empresa": email_empresa,
                },
                "representante_legal": {
                    "nombre": rep_legal_nombre,
                    "tipo_documento": rep_legal_tipo_doc,
                    "documento": rep_legal_documento,
                    "cargo": rep_legal_cargo,
                },
                "rues": {
                    "numero_rues": rues_numero,
                    "fecha_inscripcion": rues_fecha_inscripcion,
                    "fecha_renovacion": rues_fecha_renovacion,
                    "ciiu_principal": ciiu_principal,
                    "ciiu_secundarias": ciiu_secundarias,
                    "regimen": rues_regimen,
                    "tamano_empresa": tamano_empresa,
                    "estado": rues_estado,
                },
                "direccion_empresa": direccion_empresa,
                "ciudad_empresa": ciudad_empresa,
            }
            uid = db.ejecutar(
                "INSERT INTO usuarios (nombre, email, password_hash, rol, telefono, documento, tipo_servicio, activo, fecha_registro, datos_extra, tipo_persona) "
                "VALUES (?, ?, ?, 'cliente', ?, ?, ?, 1, ?, ?, 'juridica')",
                (nombre, email, generate_password_hash(clave),
                 telefono, documento, tipo_servicio,
                 datetime.now().strftime("%Y-%m-%d %H:%M"),
                 json.dumps(datos_extra, ensure_ascii=False))
            )
            _crear_contrato_cliente(
                {"id": uid, "nombre": nombre, "documento": documento,
                 "email": email, "telefono": telefono},
                tipo_servicio)
            _registrar_interaccion("registro", detalle="juridica · " + nombre)
            flash("Registro exitoso. Ya puedes iniciar sesión.", "exito")
            return redirect(url_for("login"))
    return render_template("registro_empresa.html", usuario=usuario_actual(), error=error,
                           servicios=SERVICIOS_REGISTRO)


@app.route("/registro_asociacion", methods=["GET", "POST"])
def registro_asociacion():
    if usuario_actual():
        return redirect(destino_segun_rol(usuario_actual()))
    error = None
    if request.method == "POST":
        razon_social = (request.form.get("razon_social_asoc") or "").strip()
        nit = (request.form.get("nit_asoc") or "").strip()
        rep_nombre = (request.form.get("rep_asoc_nombre") or "").strip()
        rep_cedula = (request.form.get("rep_asoc_cedula") or "").strip()
        direccion = (request.form.get("direccion_asoc") or "").strip()
        email = (request.form.get("email_asoc") or "").strip().lower()
        ciudad = (request.form.get("ciudad_asoc") or "").strip()
        clave = (request.form.get("clave") or "")
        clave2 = (request.form.get("clave2") or "")
        tipo_servicio = (request.form.get("tipo_servicio") or "").strip()

        telefono = ""

        if (not razon_social or not nit or not rep_nombre or not rep_cedula or
                not direccion or not email or not ciudad or not clave or not tipo_servicio):
            error = "Complete los campos obligatorios de la asociación."
        elif "@" not in email:
            error = "Correo inválido."
        elif len(clave) < 6:
            error = "La contraseña debe tener al menos 6 caracteres."
        elif clave != clave2:
            error = "Las contraseñas no coinciden."
        elif db.usuario_por_email(email):
            error = "Ya existe una cuenta con ese correo electrónico."
        else:
            datos_extra = {
                "tipo_persona": "asociacion",
                "razon_social": razon_social,
                "nit": nit,
                "representante_legal": {
                    "nombre": rep_nombre,
                    "cedula": rep_cedula,
                },
                "direccion": direccion,
                "ciudad": ciudad,
                "correo": email,
            }
            uid = db.ejecutar(
                "INSERT INTO usuarios (nombre, email, password_hash, rol, telefono, documento, tipo_servicio, activo, fecha_registro, datos_extra, tipo_persona) "
                "VALUES (?, ?, ?, 'cliente', ?, ?, ?, 1, ?, ?, 'asociacion')",
                (razon_social, email, generate_password_hash(clave),
                 telefono, nit, tipo_servicio,
                 datetime.now().strftime("%Y-%m-%d %H:%M"),
                 json.dumps(datos_extra, ensure_ascii=False))
            )
            _crear_contrato_cliente(
                {"id": uid, "nombre": razon_social, "documento": nit,
                 "email": email, "telefono": telefono},
                tipo_servicio)
            _registrar_interaccion("registro", detalle="asociacion · " + razon_social)
            flash("Registro exitoso. Ya puedes iniciar sesión.", "exito")
            return redirect(url_for("login"))
    return render_template("registro_asociacion.html", usuario=usuario_actual(), error=error,
                           servicios=SERVICIOS_REGISTRO)


@app.route("/cliente/contrato")
@requiere_cliente
def cliente_contrato():
    if not db.contratos_de_cliente(g.usuario["id"]):
        _crear_contrato_cliente(g.usuario, g.usuario.get("tipo_servicio") or "Servicios jurídicos en general")
    contratos = db.contratos_de_cliente(g.usuario["id"])
    return render_template("cliente/contratos.html", usuario=g.usuario, contratos=contratos)


@app.route("/cliente/contrato/<int:cid>")
@requiere_cliente
def cliente_contrato_ver(cid):
    c = db.contrato_por_id(cid)
    if not c or c["cliente_id"] != g.usuario["id"]:
        abort(404)
    return render_template("cliente/contrato.html", usuario=g.usuario, c=c,
                           hide_header=True)


@app.route("/cliente/contrato/<int:cid>/firmar", methods=["POST"])
@requiere_cliente
def cliente_contrato_firmar(cid):
    c = db.contrato_por_id(cid)
    if not c or c["cliente_id"] != g.usuario["id"]:
        abort(404)
    if c["firmado_el"]:
        flash("Este contrato ya fue firmado digitalmente.", "error")
        return redirect(url_for("cliente_contrato_ver", cid=cid))
    nombre = request.form.get("firma_nombre", "").strip()
    imagen = request.form.get("firma_imagen", "").strip()
    if len(nombre) < 3:
        flash("Escribe tu nombre completo para firmar el contrato.", "error")
        return redirect(url_for("cliente_contrato_ver", cid=cid))
    if not imagen.startswith("data:image/png;base64,"):
        flash("Dibuja tu firma en el recuadro antes de enviar.", "error")
        return redirect(url_for("cliente_contrato_ver", cid=cid))
    db.contrato_actualizar(cid, {
        "estado": "Firmado",
        "firma_nombre": nombre,
        "firma_imagen": imagen,
        "firmado_el": datetime.now().strftime("%Y-%m-%d %H:%M")})
    flash("Contrato firmado digitalmente. Ya puedes imprimirlo.", "exito")
    return redirect(url_for("cliente_contrato_ver", cid=cid))


@app.route("/login", methods=["GET", "POST"])
def login():
    if usuario_actual():
        return redirect(destino_segun_rol(usuario_actual()))
    error = None
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        clave = request.form.get("clave", "")
        usuario = db.usuario_por_email(email)
        if not usuario or not check_password_hash(usuario["password_hash"], clave):
            error = "Correo o contraseña incorrectos."
        elif not usuario["activo"]:
            error = "La cuenta está desactivada. Contacte a la administración."
        else:
            session["uid"] = usuario["id"]
            return redirect(destino_segun_rol(usuario))
    return render_template("login.html", usuario=usuario_actual(), error=error)


@app.route("/salir")
def salir():
    session.clear()
    return redirect(url_for("inicio"))


# ---------------------------------------------------------------- cliente
@app.route("/cliente")
@requiere_cliente
def cliente_inicio():
    solo_procesos = es_asociacion(g.usuario)
    cartera = _cartera_cliente_con_estado(g.usuario["id"])
    en_mora = _cliente_en_mora(g.usuario["id"])

    procesos = _enriquecer_procesos(db.procesos_de_cliente(g.usuario["id"]))
    abiertos = [p for p in procesos if p["estado"] not in
                ("Resuelto a favor", "Resuelto en contra", "Archivado")]
    resueltos = [p for p in procesos if p["estado"] in
                 ("Resuelto a favor", "Resuelto en contra")]
    promedio = round(sum(p["avance"] for p in procesos) / len(procesos)) if procesos else 0
    resumen = {"total": len(procesos), "abiertos": len(abiertos),
               "resueltos": len(resueltos), "promedio": promedio}

    return render_template("cliente/dashboard.html",
                           usuario=g.usuario,
                           solo_procesos=solo_procesos,
                           ver_cuenta=True,
                           procesos=procesos,
                           resumen=resumen,
                           estados_resumen=_resumen_estados(procesos),
                           etapas=ETAPAS_PROCESO,
                           actuaciones=db.consultar(
                               "SELECT a.* FROM actuaciones a "
                               "JOIN procesos p ON p.id = a.proceso_id "
                               "WHERE p.cliente_id = ? ORDER BY a.fecha ASC, a.id ASC",
                               (g.usuario["id"],)),
                           documentos=db.consultar(
                               "SELECT d.* FROM documentos d "
                               "JOIN actuaciones a ON a.id = d.actuacion_id "
                               "JOIN procesos p ON p.id = a.proceso_id "
                               "WHERE p.cliente_id = ? ORDER BY d.cargado_el ASC, d.id ASC",
                               (g.usuario["id"],)),
                           expedientes=db.consultar(
                               "SELECT e.*, p.cliente_id FROM expedientes e "
                               "JOIN procesos p ON p.id = e.proceso_id "
                               "WHERE p.cliente_id = ? ORDER BY e.fecha ASC, e.id ASC",
                               (g.usuario["id"],)),
                           cartera=cartera, en_mora=en_mora,
                           comprobantes=db.comprobantes_de_cliente(g.usuario["id"]),
                           formas_pago=db.formas_pago_lista(solo_activas=True),
                           testimonio=db.testimonio_de_cliente(g.usuario["id"]),
                           hoy=date.today())


def _cartera_cliente_con_estado(cliente_id):
    registros = []
    for f in db.cartera_de_cliente(cliente_id):
        f["saldo"] = float(f["valor_total"] or 0) - float(f["pagado"] or 0)
        f["estado"] = _estado_cartera(f)
        registros.append(f)
    return registros


def _cliente_en_mora(cliente_id):
    return any(r["estado"] == "Vencida" for r in _cartera_cliente_con_estado(cliente_id))


@app.route("/cliente/cartera/comprobante", methods=["POST"])
@requiere_cliente
def cliente_comprobante_subir():
    archivo = request.files.get("archivo")
    if not archivo or not archivo.filename:
        flash("Selecciona el comprobante de pago para subir.", "error")
        return redirect(url_for("cliente_inicio"))
    original = os.path.basename(archivo.filename.replace("\\", "/"))
    ext = os.path.splitext(original)[1].lower()
    if ext not in EXTENSIONES_PERMITIDAS:
        flash("Formato no permitido. Usa PDF, DOC/DOCX, JPG o PNG.", "error")
        return redirect(url_for("cliente_inicio"))
    nombre_guardado = uuid.uuid4().hex + ext
    archivo.save(os.path.join(UPLOAD_DIR, nombre_guardado))
    cartera_id = request.form.get("cartera_id")
    db.comprobante_crear({
        "cliente_id": g.usuario["id"],
        "cartera_id": int(cartera_id) if cartera_id else None,
        "nombre_archivo": original,
        "archivo": nombre_guardado,
        "tamano": os.path.getsize(os.path.join(UPLOAD_DIR, nombre_guardado)),
        "importe": request.form.get("importe", "0"),
        "nota": request.form.get("nota", "").strip()})
    _enviar_notificacion("pago", {
        "cliente": g.usuario["nombre"], "importe": request.form.get("importe", "")})
    _registrar_interaccion("pago",
                          detalle="Comprobante · $" + request.form.get("importe", ""))
    flash("Comprobante enviado. La administración lo validará en la jornada siguiente.", "exito")
    return redirect(url_for("cliente_inicio"))


@app.route("/cliente/testimonio", methods=["POST"])
@requiere_cliente
def cliente_testimonio_enviar():
    texto = request.form.get("texto", "").strip()
    try:
        calificacion = max(1, min(5, int(request.form.get("calificacion", "5"))))
    except ValueError:
        calificacion = 5
    if len(texto) < 10:
        flash("Escribe un testimonio más completo (mínimo 10 caracteres).", "error")
        return redirect(url_for("cliente_inicio"))
    if db.testimonio_de_cliente(g.usuario["id"]):
        flash("Ya enviaste tu testimonio. Está pendiente de validación y publicación por la administración.", "aviso")
        return redirect(url_for("cliente_inicio"))
    db.testimonio_crear({
        "cliente_nombre": g.usuario["nombre"],
        "texto": texto,
        "calificacion": calificacion}, cliente_id=g.usuario["id"])
    _enviar_notificacion("testimonio", {"cliente": g.usuario["nombre"]})
    _registrar_interaccion("testimonio", detalle=g.usuario["nombre"])
    flash("¡Gracias! Tu testimonio quedó enviado y pasará a validación de la administración antes de publicarse.", "exito")
    return redirect(url_for("cliente_inicio"))


@app.route("/cliente/comprobante/<int:cid>/ver")
@requiere_usuario
def ver_comprobante_cliente(cid):
    """Vista protegida para descargar un comprobante (cliente dueño o admin)."""
    comp = db.comprobante_por_id(cid)
    if not comp:
        abort(404)
    if g.usuario["rol"] != "admin" and comp["cliente_id"] != g.usuario["id"]:
        abort(403)
    ruta = os.path.join(UPLOAD_DIR, comp.get("archivo", ""))
    if not os.path.exists(ruta):
        abort(404)
    return send_from_directory(UPLOAD_DIR, comp["archivo"])


@app.route("/admin/comprobantes/<int:cid>/validar", methods=["POST"])
@requiere_admin
def admin_comprobante_validar(cid):
    comp = db.comprobante_por_id(cid)
    if not comp:
        abort(404)
    if comp["estado"] != "Pendiente":
        flash("Este comprobante ya fue procesado.", "exito")
        return redirect(url_for("admin_cartera"))
    validador = g.usuario.get("nombre") or g.usuario.get("email") or "Administración"
    if comp["cartera_id"]:
        db.ejecutar(
            "UPDATE cartera SET pagado = pagado + ?, actualizado_el = ? WHERE id = ?",
            (float(comp["importe"] or 0), datetime.now().strftime("%Y-%m-%d %H:%M"),
             comp["cartera_id"]))
    db.comprobante_estado(cid, "Validado", validador)
    flash("Comprobante validado. El abono se aplicó a la cartera.", "exito")
    return redirect(url_for("admin_cartera"))


@app.route("/admin/comprobantes/<int:cid>/rechazar", methods=["POST"])
@requiere_admin
def admin_comprobante_rechazar(cid):
    comp = db.comprobante_por_id(cid)
    if not comp:
        abort(404)
    if comp["estado"] != "Pendiente":
        flash("Este comprobante ya fue procesado.", "exito")
        return redirect(url_for("admin_cartera"))
    validador = g.usuario.get("nombre") or g.usuario.get("email") or "Administración"
    db.comprobante_estado(cid, "Rechazado", validador)
    flash("Comprobante rechazado. El cliente puede intentarlo de nuevo.", "exito")
    return redirect(url_for("admin_cartera"))


# ---------------------------------------------------------------- abogado
def _por_abogado():
    return {
        "procesos": db.procesos_de_abogado(g.abogado["id"]),
        "actuaciones": db.actuaciones_de_abogado(g.abogado["id"]),
    }


@app.route("/abogado")
@requiere_abogado
def abogado_inicio():
    datos = _por_abogado()
    hoy = date.today()
    proximas = []
    for a in datos["actuaciones"]:
        for clave, defecha in (("fecha", "Fecha de la actuación"), ("fecha_maxima", "Límite para presentarla")):
            if not a.get(clave):
                continue
            d = fecha_parse(a[clave])
            if d and d >= hoy:
                proximas.append({"dia": d, "tipo": defecha, "fecha": a[clave],
                                 "proceso": a["proceso"], "cliente": a["cliente"],
                                 "descripcion": a["descripcion"], "pid": a["proceso_id"]})
    proximas.sort(key=lambda x: x["dia"])
    return render_template("abogado/dashboard.html", usuario=g.usuario, abogado=g.abogado,
                           procesos=datos["procesos"],
                           num_procesos=len(datos["procesos"]),
                           num_actuaciones=len(datos["actuaciones"]),
                           proximas=proximas[:14], del_mes=vencimientos(hoy, datos["actuaciones"]))


def vencimientos(hoy, actuaciones):
    """Actuaciones del mes en curso para el panel."""
    dentro = []
    for a in actuaciones:
        for clave in ("fecha", "fecha_maxima"):
            d = fecha_parse(a.get(clave, ""))
            if d and d >= hoy:
                dentro.append({"fecha": d, "proceso": a["proceso"], "shorte": clave == "fecha_maxima",
                               "descripcion": a.get("descripcion", "")})
    dentro.sort(key=lambda x: x["fecha"])
    return dentro


@app.route("/abogado/calendario")
@requiere_abogado
def abogado_calendario():
    hoy = date.today()
    vista = request.args.get("vista", "mes")
    eventos = _eventos_abogado(g.abogado["id"])

    if vista == "mes":
        anio = request.args.get("anio", type=int, default=hoy.year)
        mes = request.args.get("mes", type=int, default=hoy.month)
        if mes < 1 or mes > 12:
            mes = hoy.month
        if anio < 2000 or anio > 2100:
            anio = hoy.year
        prefijo = "%04d-%02d" % (anio, mes)
        por_dia = {}
        for e in eventos:
            clave = e["inicio"].strftime("%Y-%m-%d")
            if clave.startswith(prefijo):
                e["color"], e["claro"] = _evento_color(e)
                por_dia.setdefault(clave, []).append(e)
        mes_anterior = 12 if mes == 1 else mes - 1
        anio_anterior = anio - 1 if mes == 1 else anio
        mes_siguiente = 1 if mes == 12 else mes + 1
        anio_siguiente = anio + 1 if mes == 12 else anio
        titulo = "%s de %d" % (["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
                                "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"][mes - 1], anio)
        return render_template("abogado/calendario.html", usuario=g.usuario, abogado=g.abogado,
                               vista=vista, hoy=hoy, anio=anio, mes=mes,
                               titulo_periodo=titulo,
                               por_dia=por_dia,
                               semanas=calendario_py.monthcalendar(anio, mes),
                               prev_url=url_for("abogado_calendario", vista="mes", anio=anio_anterior, mes=mes_anterior),
                               next_url=url_for("abogado_calendario", vista="mes", anio=anio_siguiente, mes=mes_siguiente),
                               hoy_url=url_for("abogado_calendario", vista="mes", anio=hoy.year, mes=hoy.month),
                               hoy_iso=hoy.isoformat())

    # semana, dia y agenda
    fecha_str = request.args.get("fecha", "")
    ancla = fecha_parse(fecha_str)
    if not ancla:
        ancla = hoy
    if vista == "semana":
        inicio = ancla - timedelta(days=ancla.weekday())
        dias = [inicio + timedelta(days=i) for i in range(7)]
        delta_nav = timedelta(days=7)
    elif vista == "dia":
        dias = [ancla]
        delta_nav = timedelta(days=1)
    else:  # agenda: próximos 14 días desde el ancla
        dias = [ancla + timedelta(days=i) for i in range(14)]
        delta_nav = timedelta(days=14)
    estructura = _armar_dias(eventos, dias)
    if vista == "semana":
        ini, fin = dias[0], dias[-1]
        if ini.month == fin.month:
            periodo = "%d – %d %s de %d" % (ini.day, fin.day, _mes_nombre_corto(fin.month), fin.year)
        else:
            periodo = "%d %s – %d %s de %d" % (ini.day, _mes_nombre_corto(ini.month), fin.day, _mes_nombre_corto(fin.month), fin.year)
    elif vista == "dia":
        periodo = _fecha_larga(ancla)
    else:
        periodo = "Agenda (próximos 14 días)"
    return render_template("abogado/calendario.html", usuario=g.usuario, abogado=g.abogado,
                           vista=vista, hoy=hoy, ancla=ancla, dias=estructura,
                           titulo_periodo=periodo,
                           hora_min=6, hora_max=18,
                           prev_url=url_for("abogado_calendario", vista=vista, fecha=(ancla - delta_nav).isoformat()),
                           next_url=url_for("abogado_calendario", vista=vista, fecha=(ancla + delta_nav).isoformat()),
                           hoy_url=url_for("abogado_calendario", vista=vista, fecha=hoy.isoformat()),
                           hoy_iso=hoy.isoformat())


def _mes_nombre_corto(mes):
    return ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
            "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"][mes - 1]


def _fecha_larga(d):
    from datetime import datetime as _dt
    return {
        0: "lunes", 1: "martes", 2: "miércoles", 3: "jueves",
        4: "viernes", 5: "sábado", 6: "domingo"}[d.weekday()] + \
        ", %d de " % (d.day) + ["enero", "febrero", "marzo", "abril", "mayo", "junio",
                                "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"][d.month - 1] + \
        " de %d" % d.year


def _eventos_abogado(abogado_id):
    """Lista unificada de los eventos del abogado (actuaciones, actividades, citas)."""
    eventos = []
    for a in db.actuaciones_de_abogado(abogado_id):
        f = fecha_parse(a.get("fecha"))
        fm = fecha_parse(a.get("fecha_maxima"))
        proceso = a["proceso"]
        if f:
            eventos.append({"id": "actuacion-%d" % a["id"], "tipo": "actuacion",
                            "titulo": proceso, "detalle": "Actuación · %s" % a.get("cliente", "?"),
                            "inicio": datetime(f.year, f.month, f.day),
                            "fin": datetime(f.year, f.month, f.day, 23, 59),
                            "todo_dia": True})
        if fm:
            eventos.append({"id": "vencimiento-%d" % a["id"], "tipo": "vencimiento",
                            "titulo": proceso, "detalle": "Límite · %s" % a.get("cliente", "?"),
                            "inicio": datetime(fm.year, fm.month, fm.day),
                            "fin": datetime(fm.year, fm.month, fm.day, 23, 59),
                            "todo_dia": True})
    for act in db.actividades_de_abogado(abogado_id):
        f = fecha_parse(act["fecha"])
        if not f:
            continue
        ini = _hora_a_min(act["hora"])
        if ini is None:
            continue
        fin = _hora_a_min(act.get("hora_fin") or act["hora"]) or (ini + 60)
        if fin <= ini:
            fin = ini + 60
        inicio = datetime(f.year, f.month, f.day, ini // 60, ini % 60)
        fin_dt = datetime(f.year, f.month, f.day, fin // 60, fin % 60)
        eventos.append({"id": "actividad-%d" % act["id"], "tipo": "actividad",
                        "tipo_act": (act.get("tipo") or "Actividad").lower(),
                        "titulo": act["titulo"], "detalle": act.get("tipo", "Actividad"),
                        "inicio": inicio, "fin": fin_dt,
                        "todo_dia": False})
    for cita in db.citas_de_abogado(abogado_id):
        f = fecha_parse(cita["fecha"])
        ini = _hora_a_min(cita["hora"]) if cita.get("hora") else None
        if not f or ini is None:
            continue
        inicio = datetime(f.year, f.month, f.day, ini // 60, ini % 60)
        eventos.append({"id": "cita-%d" % cita["id"], "tipo": "cita",
                        "tipo_act": "cita",
                        "titulo": "Cita · %s" % cita["nombre"], "detalle": cita.get("motivo", "Cita"),
                        "inicio": inicio, "fin": inicio + timedelta(minutes=60),
                        "todo_dia": False})
    return eventos


def _evento_color(evento):
    """Color principal y de fondo según el tipo del evento."""
    paleta = {
        "actuacion": ("#039be5", "#e1f5fe"),
        "vencimiento": ("#f4511e", "#fbe9e7"),
        "audiencia": ("#33b679", "#e6f4ea"),
        "diligencia": ("#e67c73", "#fce8e6"),
        "reunion": ("#8e24aa", "#f3e8fd"),
        "actividad": ("#7986cb", "#e8eaf6"),
        "bloqueo": ("#616161", "#eeeeee"),
        "cita": ("#0b8043", "#e3f2e8"),
    }
    clave = evento.get("tipo_act") or evento["tipo"]
    return paleta.get(clave, paleta.get(evento["tipo"], ("#546e7a", "#eceff1")))


HORA_MIN_CAL = 6
HORA_MAX_CAL = 19  # franja [06:00, 19:00)


def _armar_dias(eventos, dias):
    """Arma la estructura por día con layout tipo Google Calendar."""
    estructura = []
    for dia in dias:
        clave_dia = dia.isoformat()
        del_dia = [e for e in eventos if e["inicio"].date() == dia]
        for e in del_dia:
            e["color"], e["claro"] = _evento_color(e)
        todo_dia = [e for e in del_dia if e["todo_dia"]]
        eventos_hora = [e for e in del_dia if not e["todo_dia"]]
        total_min = (HORA_MAX_CAL - HORA_MIN_CAL) * 60
        eventos_hora.sort(key=lambda e: (e["inicio"], e["fin"]))
        columnas = []
        for e in eventos_hora:
            col = None
            for i, ce in enumerate(columnas):
                if e["inicio"] >= ce[-1]["fin"]:
                    col = i
                    break
            if col is None:
                columnas.append([])
                col = len(columnas) - 1
            columnas[col].append(e)
            e["_col"] = col
        ncols = max(1, len(columnas))
        ancho_col = 100.0 / ncols
        for e in eventos_hora:
            inicio_min = e["inicio"].hour * 60 + e["inicio"].minute
            dur = (e["fin"] - e["inicio"]).total_seconds() // 60
            top = max(0.0, (inicio_min - HORA_MIN_CAL * 60) * 100.0 / total_min)
            alto = max(26.0, min(100.0 - top, dur * 100.0 / total_min))
            e["_top"] = top
            e["_alto"] = alto
            e["_left"] = e["_col"] * ancho_col
            e["_width"] = ancho_col
        info = {
            "fecha": dia,
            "clave": clave_dia,
            "nombre": ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"][dia.weekday()],
            "num": dia.day,
            "mes_corto": _mes_nombre_corto(dia.month),
            "anio": dia.year,
            "hoy": dia == date.today(),
            "todo_dia": todo_dia,
            "eventos": eventos_hora,
            "ncols": ncols,
        }
        if dia == date.today():
            ah = datetime.now()
            info["now_top"] = max(0.0, (ah.hour * 60 + ah.minute - HORA_MIN_CAL * 60) * 100.0 / total_min)
        estructura.append(info)
    return estructura


def _sumar_minutos(hhmm, minutos):
    ini = _hora_a_min(hhmm) or 0
    tot = ini + int(minutos)
    return "%02d:%02d" % (tot // 60, tot % 60)


@app.route("/abogado/actividades/nueva", methods=["POST"])
@requiere_abogado
def abogado_actividad_nueva():
    titulo = request.form.get("titulo", "").strip()
    fecha = request.form.get("fecha", "").strip()
    hora = request.form.get("hora", "").strip()
    if not titulo or not fecha or not hora:
        flash("Completa el título, la fecha y la hora de la actividad.", "error")
        return redirect(url_for("abogado_calendario"))
    duracion = int(request.form.get("duracion", 60) or 60)
    db.actividad_crear({
        "abogado_id": g.abogado["id"],
        "titulo": titulo,
        "tipo": request.form.get("tipo", "Actividad"),
        "fecha": fecha, "hora": hora,
        "hora_fin": _sumar_minutos(hora, duracion),
        "descripcion": request.form.get("descripcion", "").strip()})
    flash("Actividad registrada y descontada del agendamiento público.", "exito")
    return redirect(url_for("abogado_calendario"))


@app.route("/abogado/actividades/<int:aid>/eliminar", methods=["POST"])
@requiere_abogado
def abogado_actividad_eliminar(aid):
    db.actividad_eliminar(aid)
    flash("Actividad eliminada.", "exito")
    return redirect(url_for("abogado_calendario"))


def fila_evento(a, marcados, eventos, clave_campo, tipo, etiqueta):
    d = a.get(clave_campo, "")
    fecha = fecha_parse(d)
    if not fecha:
        return
    clave = "%04d-%02d-%02d" % (fecha.year, fecha.month, fecha.day)
    marcados.setdefault(clave, []).append(tipo)
    eventos.append({"fecha": d, "tipo": tipo, "etiqueta": etiqueta,
                    "proceso": a["proceso"], "cliente": a["cliente"],
                    "descripcion": a.get("descripcion", ""), "pid": a["proceso_id"]})


@app.route("/abogado/archivos")
@requiere_abogado
def abogado_archivos():
    return render_template("abogado/archivos.html", usuario=g.usuario, abogado=g.abogado,
                           expedientes=db.expedientes_de_abogado(g.abogado["id"]))


@app.route("/abogado/procesos")
@requiere_abogado
def abogado_procesos():
    return render_template("abogado/procesos.html", usuario=g.usuario, abogado=g.abogado,
                           procesos=db.procesos_de_abogado(g.abogado["id"]))


@app.route("/abogado/procesos/<int:pid>")
@requiere_abogado
def abogado_proceso(pid):
    procesos = db.consultar(
        "SELECT p.*, u.nombre AS cliente, u.email AS correo_cliente FROM procesos p "
        "JOIN usuarios u ON u.id = p.cliente_id WHERE p.id = ? AND p.abogado_id = ?",
        (pid, g.abogado["id"]))
    if not procesos:
        abort(404)
    proceso = procesos[0]
    actuaciones = db.actuaciones_de_proceso(pid)
    for a in actuaciones:
        a["dias_restantes"] = dias_restantes(a.get("fecha_maxima", ""))
    return render_template("abogado/proceso.html", usuario=g.usuario, abogado=g.abogado,
                           proceso=proceso, actuaciones=actuaciones,
                           expedientes=db.expedientes_de_proceso(pid),
                           anotaciones=db.anotaciones_de_proceso(pid))


@app.route("/abogado/procesos/<int:pid>/notas", methods=["POST"])
@requiere_abogado
def abogado_proceso_notas(pid):
    texto = request.form.get("texto", "").strip()
    if not texto:
        flash("Escribe la anotación antes de guardarla.", "error")
        return redirect(url_for("abogado_proceso", pid=pid))
    db.ejecutar(
        "INSERT INTO anotaciones (proceso_id, abogado_id, texto, creado_el) VALUES (?, ?, ?, ?)",
        (pid, g.abogado["id"], texto, datetime.now().strftime("%Y-%m-%d %H:%M")))
    db.ejecutar("UPDATE procesos SET fecha_actualizacion = ? WHERE id = ?",
                (datetime.now().strftime("%Y-%m-%d %H:%M"), pid))
    flash("Anotación guardada.", "exito")
    return redirect(url_for("abogado_proceso", pid=pid))


@app.route("/abogado/anotaciones/<int:nid>/eliminar", methods=["POST"])
@requiere_abogado
def abogado_anotacion_eliminar(nid):
    filas = db.consultar("SELECT proceso_id FROM anotaciones WHERE id = ? AND abogado_id = ?",
                         (nid, g.abogado["id"]))
    if not filas:
        abort(404)
    db.ejecutar("DELETE FROM anotaciones WHERE id = ?", (nid,))
    flash("Anotación eliminada.", "exito")
    return redirect(url_for("abogado_proceso", pid=filas[0]["proceso_id"]))


# ---------------------------------------------------------------- correo del abogado
def _cfg_correo():
    cfg = db.correo_config_de(g.abogado["id"])
    return cfg if cfg and cfg["activo"] else None


def _datos_correo(cfg):
    return {
        "servidor_imap": cfg["servidor_imap"] or webmail.IMAP_HOST,
        "puerto_imap": cfg["puerto_imap"] or webmail.IMAP_PUERTO,
        "servidor_smtp": cfg["servidor_smtp"] or webmail.SMTP_HOST,
        "puerto_smtp": cfg["puerto_smtp"] or webmail.SMTP_PUERTO,
        "correo": cfg["correo"] or g.abogado["correo"],
        "clave": cfg.get("clave") or "",
    }


def _puerto_int(valor, por_defecto):
    try:
        return int(valor)
    except (TypeError, ValueError):
        return por_defecto


def _enviar_notificacion(tipo, datos):
    """Envía aviso por correo al despacho cuando llega un contacto o una cita."""
    cfg = db.notif_config_de()
    if not cfg or not cfg["activo"] or not cfg["correo"] or not cfg["clave"]:
        return
    try:
        if tipo == "contacto":
            asunto = "Nuevo mensaje de contacto — %s" % (datos.get("asunto") or "Contacto")
            cuerpo = ("Nuevo mensaje enviado desde el sitio web.\n\n"
                      "Nombre: %s\nCorreo: %s\nTeléfono: %s\nAsunto: %s\n\nMensaje:\n%s"
                      % (datos["nombre"], datos["correo"],
                         datos.get("telefono") or "—", datos.get("asunto") or "—",
                         datos["mensaje"]))
        elif tipo == "pago":
            asunto = "Nuevo comprobante de pago por validar — %s" % datos.get("cliente", "Cliente")
            cuerpo = ("El cliente %s subió un comprobante de pago por %s.\n\n"
                      "Revisa el panel de administración (Cartera) para validarlo."
                      % (datos.get("cliente", "—"), datos.get("importe") or "—"))
        elif tipo == "testimonio":
            asunto = "Nuevo testimonio por validar — %s" % datos.get("cliente", "Cliente")
            cuerpo = ("El cliente %s dejó un testimonio.\n\n"
                      "Revísalo y publícalo desde el panel de administración (Testimonios)."
                      % datos.get("cliente", "—"))
        else:
            asunto = "Nueva solicitud de cita — %s" % datos["nombre"]
            cuerpo = ("Nueva solicitud de cita enviada desde el sitio web.\n\n"
                      "Nombre: %s\nCorreo: %s\nTeléfono: %s\nAbogado: %s\nFecha: %s  Hora: %s\nMotivo:\n%s"
                      % (datos["nombre"], datos["correo"],
                         datos.get("telefono") or "—", datos.get("abogado_nombre") or "Sin preferencia",
                         datos["fecha"], datos["hora"], datos.get("motivo") or "—"))
        webmail.enviar(cfg, cfg["destino"], asunto, cuerpo.replace("\n", "<br>"))
    except webmail.ErrorCorreo as e:
        flash("Tu solicitud quedó registrada, pero el aviso por correo falló: %s" % e, "error")


@app.route("/abogado/correo")
@requiere_abogado
def abogado_correo():
    cfg = _cfg_correo()
    carpeta = request.args.get("carpeta", "INBOX")
    mensajes, error = [], None
    carpetas = None
    if cfg:
        try:
            mensajes = webmail.listar(_datos_correo(cfg), carpeta)
        except webmail.ErrorCorreo as e:
            error = str(e)
    return render_template("abogado/correo.html", usuario=g.usuario, abogado=g.abogado,
                           cfg=cfg, carpeta=carpeta, mensajes=mensajes, error=error,
                           carpetas=webmail.CARPETAS)


@app.route("/abogado/correo/mensaje", methods=["POST"])
@requiere_abogado
def abogado_correo_mensaje():
    cfg = _cfg_correo()
    if not cfg:
        return {"ok": False, "error": "Configura primero tu correo institucional."}
    try:
        msj = webmail.leer(_datos_correo(cfg), request.form.get("carpeta", "INBOX"),
                           request.form["uid"])
        msj["ok"] = True
        return msj
    except (webmail.ErrorCorreo, KeyError) as e:
        return {"ok": False, "error": str(e)}


@app.route("/abogado/correo/accion", methods=["POST"])
@requiere_abogado
def abogado_correo_accion():
    cfg = _cfg_correo()
    if not cfg:
        return {"ok": False, "error": "Configura primero tu correo institucional."}
    accion = request.form.get("accion", "")
    carpeta = request.form.get("carpeta", "INBOX")
    uid = request.form.get("uid", "")
    try:
        if accion == "leido":
            webmail.marcar(_datos_correo(cfg), carpeta, uid, True)
        elif accion == "noleido":
            webmail.marcar(_datos_correo(cfg), carpeta, uid, False)
        elif accion == "eliminar":
            webmail.eliminar(_datos_correo(cfg), carpeta, uid)
        else:
            return {"ok": False, "error": "Acción no válida."}
        return {"ok": True}
    except (webmail.ErrorCorreo, KeyError) as e:
        return {"ok": False, "error": str(e)}


@app.route("/abogado/correo/adjunto")
@requiere_abogado
def abogado_correo_adjunto():
    cfg = _cfg_correo()
    if not cfg:
        flash("Configura primero tu correo institucional.", "error")
        return redirect(url_for("abogado_correo_config"))
    try:
        nombre, payload, mime = webmail.adjunto(
            _datos_correo(cfg), request.args.get("carpeta", "INBOX"),
            request.args["uid"], int(request.args.get("indice", 0)))
        return send_file(BytesIO(payload), as_attachment=True,
                         download_name=nombre, mimetype=mime)
    except (webmail.ErrorCorreo, KeyError, ValueError) as e:
        flash("No se pudo descargar el adjunto: %s" % e, "error")
        return redirect(url_for("abogado_correo"))


@app.route("/abogado/correo/redactar")
@requiere_abogado
def abogado_correo_redactar():
    cfg = _cfg_correo()
    uid = request.args.get("uid", "")
    carpeta = request.args.get("carpeta", "INBOX")
    original = para = asunto = cc = cuerpo = None
    if uid and cfg:
        try:
            original = webmail.leer(_datos_correo(cfg), carpeta, uid)
            para = original["de_correo"]
            asunto = ("Re: " + webmail._limpiar_asunto(original["asunto"]))
        except webmail.ErrorCorreo:
            pass
    return render_template("abogado/correo_redactar.html", usuario=g.usuario,
                           abogado=g.abogado, cfg=cfg, para=para or "", cc=cc or "",
                           asunto=asunto or "", cuerpo=cuerpo or "",
                           original=original)


@app.route("/abogado/correo/enviar", methods=["POST"])
@requiere_abogado
def abogado_correo_enviar():
    cfg = _cfg_correo()
    if not cfg:
        flash("Configura primero tu correo institucional.", "error")
        return redirect(url_for("abogado_correo_config"))
    para = request.form.get("para", "").strip()
    asunto = request.form.get("asunto", "").strip()
    cc = request.form.get("cc", "").strip()
    cuerpo = request.form.get("cuerpo", "")
    original_uid = request.form.get("original_uid", "")
    if not para:
        flash("Indica al menos un destinatario.", "error")
        return redirect(url_for("abogado_correo_redactar"))
    responder_origen = None
    if original_uid:
        try:
            original = webmail.leer(_datos_correo(cfg), request.form.get("carpeta", "INBOX"),
                                    original_uid)
            cuerpo = webmail.respuesta_previa(original, cuerpo)
            responder_origen = original
        except webmail.ErrorCorreo as e:
            responder_origen = None
            flash("No se pudo citar el mensaje original: %s" % e, "error")
    try:
        webmail.enviar(_datos_correo(cfg), para, asunto or "(sin asunto)", cuerpo, cc=cc,
                       responder=responder_origen)
        flash("Correo enviado.", "ok")
        return redirect(url_for("abogado_correo", carpeta="Sent"))
    except webmail.ErrorCorreo as e:
        flash("No se pudo enviar: %s" % e, "error")
        return redirect(url_for("abogado_correo_redactar"))


@app.route("/abogado/correo/config", methods=["GET", "POST"])
@requiere_abogado
def abogado_correo_config():
    cfg = _cfg_correo() or {}
    if request.method == "POST":
        accion = request.form.get("accion", "guardar")
        if accion == "prueba":
            datos = _datos_correo({
                "servidor_imap": request.form.get("servidor_imap") or webmail.IMAP_HOST,
                "puerto_imap": request.form.get("puerto_imap") or webmail.IMAP_PUERTO,
                "servidor_smtp": request.form.get("servidor_smtp") or webmail.SMTP_HOST,
                "puerto_smtp": request.form.get("puerto_smtp") or webmail.SMTP_PUERTO,
                "correo": request.form.get("correo", "").strip(),
                "clave": request.form.get("clave", ""),
            })
            try:
                webmail.probar(datos)
                return {"ok": True, "detalle": "Conexión IMAP exitosa."}
            except webmail.ErrorCorreo as e:
                return {"ok": False, "detalle": str(e)}
        datos = {
            "servidor_imap": request.form.get("servidor_imap") or webmail.IMAP_HOST,
            "puerto_imap": _puerto_int(request.form.get("puerto_imap"), webmail.IMAP_PUERTO),
            "servidor_smtp": request.form.get("servidor_smtp") or webmail.SMTP_HOST,
            "puerto_smtp": _puerto_int(request.form.get("puerto_smtp"), webmail.SMTP_PUERTO),
            "correo": request.form.get("correo", "").strip(),
            "clave": request.form.get("clave", ""),
        }
        if not datos["correo"]:
            flash("Indica el correo institucional.", "error")
        elif not datos["clave"]:
            flash("Indica la contraseña del correo.", "error")
        else:
            db.correo_config_guardar(g.abogado["id"], datos)
            flash("Configuración de correo guardada.", "ok")
            return redirect(url_for("abogado_correo"))
    return render_template("abogado/correo_config.html", usuario=g.usuario, abogado=g.abogado,
                           cfg=cfg, correo=(cfg or {}).get("correo") or g.abogado["correo"])


@app.route("/abogado/correo/quitar", methods=["POST"])
@requiere_abogado
def abogado_correo_quitar():
    db.correo_config_quitar(g.abogado["id"])
    flash("Configuración de correo eliminada.", "ok")
    return redirect(url_for("abogado_correo"))


# ---------------------------------------------------------------- admin
@app.route("/admin")
@requiere_admin
def panel_admin():
    cliente = db.consultar(
        "SELECT COUNT(*) AS n FROM usuarios WHERE rol = 'cliente'")[0]["n"]
    procesos = db.consultar("SELECT COUNT(*) AS n FROM procesos")[0]["n"]
    noticias = db.consultar("SELECT COUNT(*) AS n FROM noticias")[0]["n"]
    abogados = db.consultar(
        "SELECT COUNT(*) AS n FROM abogados WHERE activo = 1")[0]["n"]
    expedientes = db.consultar("SELECT COUNT(*) AS n FROM expedientes")[0]["n"]
    citas_pendientes = db.consultar(
        "SELECT COUNT(*) AS n FROM citas WHERE estado = 'Pendiente'")[0]["n"]
    contactos_nuevos = db.consultar(
        "SELECT COUNT(*) AS n FROM contactos WHERE leido = 0")[0]["n"]
    citas = db.consultar(
        "SELECT c.*, a.nombre AS abogado_nombre FROM citas c "
        "LEFT JOIN abogados a ON a.id = c.abogado_id "
        "WHERE c.estado = 'Pendiente' ORDER BY c.fecha ASC, c.hora ASC LIMIT 6")
    ultimos = db.consultar(
        "SELECT p.*, u.nombre AS cliente FROM procesos p "
        "JOIN usuarios u ON u.id = p.cliente_id "
        "ORDER BY p.fecha_actualizacion DESC LIMIT 6")
    return render_template("admin/dashboard.html", usuario=g.usuario,
                           cliente=cliente, procesos=procesos, noticias=noticias,
                           abogados=abogados, expedientes=expedientes,
                           citas_pendientes=citas_pendientes,
                           contactos_nuevos=contactos_nuevos, citas=citas,
                           ultimos=ultimos)


# ------- noticias
@app.route("/admin/noticias")
@requiere_admin
def admin_noticias():
    return render_template("admin/noticias.html", usuario=g.usuario,
                           noticias=db.consultar("SELECT * FROM noticias ORDER BY id DESC"))


@app.route("/admin/noticias/crear", methods=["POST"])
@requiere_admin
def admin_noticias_crear():
    imagen_nombre, error = guardar_imagen_articulo(request.files.get("imagen"))
    if error:
        flash(error, "error")
        return redirect(url_for("admin_noticias"))
    nid = db.ejecutar(
        "INSERT INTO noticias (titulo, resumen, contenido, etiqueta, imagen, creado_el) VALUES (?, ?, ?, ?, ?, ?)",
        (request.form["titulo"].strip(), request.form.get("resumen", "").strip(),
         request.form.get("contenido", "").strip(), request.form.get("etiqueta", "Artículo").strip(),
         imagen_nombre, datetime.now().strftime("%Y-%m-%d %H:%M")))
    flash("Artículo publicado.", "exito")
    if any(c["activa"] and c["auto"] for c in redes.leer_config().values()):
        filas = db.consultar("SELECT * FROM noticias WHERE id = ?", (nid,))
        if filas:
            resultados = redes.publicar_articulo(
                filas[0], _url_articulo(nid),
                ruta_imagen=(os.path.join(ARTICULOS_IMG_DIR, filas[0]["imagen"])
                             if filas[0].get("imagen") else None))
            for plataforma, ok, msg in resultados:
                flash("%s: %s" % (plataforma, msg), "exito" if ok else "error")
    return redirect(url_for("admin_noticias"))


@app.route("/admin/noticias/<int:nid>/editar", methods=["POST"])
@requiere_admin
def admin_noticias_editar(nid):
    actual = db.consultar("SELECT imagen FROM noticias WHERE id = ?", (nid,))
    imagen_nombre, error = guardar_imagen_articulo(request.files.get("imagen"))
    if error:
        flash(error, "error")
        return redirect(url_for("admin_noticias"))
    if imagen_nombre and actual and actual[0]["imagen"]:
        borrar_imagen_articulo(actual[0]["imagen"])
    db.ejecutar(
        "UPDATE noticias SET titulo = ?, resumen = ?, contenido = ?, etiqueta = ?, "
        "imagen = COALESCE(?, imagen) WHERE id = ?",
        (request.form["titulo"].strip(), request.form.get("resumen", "").strip(),
         request.form.get("contenido", "").strip(), request.form.get("etiqueta", "Artículo").strip(),
         imagen_nombre if imagen_nombre else None, nid))
    flash("Artículo actualizado.", "exito")
    return redirect(url_for("admin_noticias"))


@app.route("/admin/noticias/<int:nid>/eliminar", methods=["POST"])
@requiere_admin
def admin_noticias_eliminar(nid):
    filas = db.consultar("SELECT imagen FROM noticias WHERE id = ?", (nid,))
    if filas:
        borrar_imagen_articulo(filas[0]["imagen"])
    db.ejecutar("DELETE FROM noticias WHERE id = ?", (nid,))
    flash("Artículo eliminado.", "exito")
    return redirect(url_for("admin_noticias"))


def _url_articulo(nid):
    return request.host_url.rstrip("/") + url_for("articulo", aid=nid)


def _publicar_en_redes(articulo, nid):
    """Publica el artículo en las redes activas y muestra resultados como flash."""
    resultados = redes.publicar_articulo(articulo, _url_articulo(nid),
                                         ruta_imagen=(os.path.join(ARTICULOS_IMG_DIR, articulo["imagen"])
                                                      if articulo.get("imagen") else None))
    if not resultados:
        flash("No hay redes sociales conectadas. Configúralas en Redes.", "aviso")
    nombres = {"LinkedIn": "linkedin", "X": "x", "Instagram": "instagram"}
    for plataforma, ok, msg in resultados:
        db.publicacion_red_crear(
            plataforma=nombres.get(plataforma, plataforma.lower()),
            articulo_id=nid,
            estado="ok" if ok else "error",
            detalle=msg,
            url_externa="")
        flash("%s: %s" % (plataforma, msg), "exito" if ok else "error")
    return resultados


@app.route("/admin/noticias/<int:nid>/compartir", methods=["POST"])
@requiere_admin
def admin_noticias_compartir(nid):
    filas = db.consultar("SELECT * FROM noticias WHERE id = ?", (nid,))
    if not filas:
        abort(404)
    _publicar_en_redes(filas[0], nid)
    return redirect(url_for("admin_noticias"))


@app.route("/articulo/<int:aid>")
def articulo(aid):
    filas = db.consultar("SELECT * FROM noticias WHERE id = ?", (aid,))
    if not filas:
        abort(404)
    return render_template("articulo.html", noticia=filas[0],
                           otras=db.consultar(
                               "SELECT * FROM noticias WHERE id != ? ORDER BY id DESC LIMIT 3",
                               (aid,)))


# ---------------- marketing digital: posicionamiento y redes
def _marketing_sin_json(texto, por_defecto):
    import json as _json
    if not texto:
        return por_defecto
    try:
        return _json.loads(texto)
    except (ValueError, TypeError):
        return por_defecto


def _marketing_analisis_listo(fila):
    """Agrega a una fila del historial los campos JSON ya convertidos."""
    if not fila:
        return None
    fila = dict(fila)
    fila["motores"] = _marketing_sin_json(fila.get("motores"), [])
    fila["redes"] = _marketing_sin_json(fila.get("redes"), [])
    fila["tecnico"] = _marketing_sin_json(fila.get("tecnico"), [])
    fila["contenido"] = _marketing_sin_json(fila.get("contenido"), {})
    return fila


def _marketing_metricas_propias(articulo_fila, url):
    """Si el servidor no puede descargar su propia pagina, arma las medidas
    con los datos guardados del articulo para no dejar el informe vacio."""
    import marketing
    titulo = (articulo_fila.get("titulo") or "").strip()
    contenido = (articulo_fila.get("contenido") or "").strip()
    m = marketing.metricas("", url)
    m.update({"titulo": titulo, "titulo_len": len(titulo),
              "descripcion": (articulo_fila.get("resumen") or "").strip(),
              "descripcion_len": len((articulo_fila.get("resumen") or "").strip()),
              "h1": [titulo] if titulo else [], "h1_count": 1 if titulo else 0,
              "encabezados": [(1, titulo)] if titulo else [],
              "palabras": len(contenido.split()),
              "texto": contenido,
              "primer_parrafo": contenido[:300],
              "fecha": (articulo_fila.get("creado_el") or "")[:10]})
    return m


def _marketing_informe(objetivo, clave="", url_externa=""):
    """Arma el informe completo (buscadores + redes) del objetivo pedido."""
    import marketing
    objetivo = (objetivo or "").strip()
    C = db.contenido_todos()
    descargado = True
    if objetivo == "portada":
        url = url_for("inicio", _external=True)
        try:
            pagina = marketing.descargar(url, propio=True)
        except marketing.MarketingError:
            descargado = False
            pagina = None
        m = (marketing.metricas(pagina["html"], url) if pagina
             else _marketing_metricas_propias({"titulo": "Derechos On"}, url))
        contenido = {"titulo": m["titulo"] or "Derechos On",
                     "resumen": m["descripcion"] or C.get("quienes_texto", "")[:280],
                     "texto": m["texto"], "imagen": (m["og"].get("image") or ""),
                     "etiqueta": "Portada"}
    elif objetivo.startswith("articulo:"):
        nid = int(objetivo.split(":", 1)[1] or 0)
        fila = db.consultar("SELECT * FROM noticias WHERE id = ?", (nid,))
        if not fila:
            raise marketing.MarketingError("Ese articulo ya no existe.")
        art = fila[0]
        url = url_for("articulo", aid=nid, _external=True)
        try:
            pagina = marketing.descargar(url, propio=True)
        except marketing.MarketingError:
            descargado = False
            pagina = None
        m = (marketing.metricas(pagina["html"], url) if pagina
             else _marketing_metricas_propias(art, url))
        contenido = {"titulo": art["titulo"], "resumen": art.get("resumen") or "",
                     "texto": art.get("contenido") or "",
                     "imagen": art.get("imagen") or "", "etiqueta": art.get("etiqueta") or ""}
    else:
        url = marketing.validar_url(url_externa)
        pagina = marketing.descargar(url)
        m = marketing.metricas(pagina["html"], url)
        contenido = {"titulo": m["titulo"], "resumen": m["descripcion"],
                     "texto": m["texto"], "imagen": m["og"].get("image", ""),
                     "etiqueta": "Sitio externo"}

    ctx = {"propio": objetivo == "portada" or objetivo.startswith("articulo:"),
           "tipo": "articulo" if objetivo.startswith("articulo:") else (
               "portada" if objetivo == "portada" else "url"),
           "clave": (clave or "").strip()}
    if ctx["propio"]:
        ctx["robots"] = marketing._consultar_ruta(url, "/robots.txt")
        ctx["sitemap"] = marketing._consultar_ruta(url, "/sitemap.xml")
    else:
        ctx["robots"] = None
        ctx["sitemap"] = None
    motores = marketing.revisar_motores(m, ctx)
    if not descargado:
        motores[0]["hallazgos"].insert(0, {
            "clave": "descarga", "titulo": "Analisis sin descarga", "estado": "aviso",
            "detalle": "El servidor no pudo descargar su propia pagina; el diagnostico "
                       "se armo con los datos guardados.",
            "consejo": "Revisa que el sitio responda en la direccion publica antes de "
                       "desplegar el analisis.", "peso": 0})
    redes = marketing.revisar_redes(contenido, url)
    puntaje = int(round(sum(x["puntaje"] for x in motores) / float(len(motores))))
    return {"objetivo": objetivo, "url": url, "tipo": ctx["tipo"], "clave": ctx["clave"],
            "puntaje": puntaje, "motores": motores, "redes": redes,
            "contenido": contenido, "resumen": marketing.resumen_ejecutivo(motores, redes, []),
            "metricas": m}


@app.route("/admin/marketing")
@requiere_admin
def admin_marketing():
    import marketing
    noticias = db.consultar("SELECT id, titulo, etiqueta, imagen, resumen, contenido, "
                            "creado_el FROM noticias ORDER BY id DESC")
    articulos = [{"id": n["id"], "titulo": n["titulo"], "etiqueta": n["etiqueta"] or "",
                  "imagen": bool(n["imagen"]),
                  "palabras": len((n["contenido"] or "").split()),
                  "creado_el": (n["creado_el"] or "")[:10]} for n in noticias]
    fila = request.args.get("id")
    analisis = _marketing_analisis_listo(
        db.marketing_analisis(fila) if fila and fila.isdigit() else None)
    if not analisis:
        ultimo = db.marketing_historial(1)
        analisis = _marketing_analisis_listo(ultimo[0]) if ultimo else None
    historial = [_marketing_analisis_listo(h) for h in db.marketing_historial(20)]
    return render_template("admin/marketing.html", usuario=g.usuario,
                           articulos=articulos, motores=marketing.MOTORES,
                           redes=marketing.REDES, analisis=analisis,
                           historial=historial,
                           ia_lista=ia_juridica.configurado(),
                           C=db.contenido_todos())


@app.route("/admin/marketing/analizar", methods=["POST"])
@requiere_admin
def admin_marketing_analizar():
    import marketing
    objetivo = (request.form.get("objetivo") or "").strip()
    clave = (request.form.get("clave") or "").strip()
    url_externa = (request.form.get("url") or "").strip()
    try:
        informe = _marketing_informe(objetivo, clave, url_externa)
    except marketing.MarketingError as exc:
        flash(str(exc), "error")
        return redirect(url_for("admin_marketing"))
    except (ValueError, TypeError):
        flash("No se pudo leer la direccion indicada.", "error")
        return redirect(url_for("admin_marketing"))
    aid = db.marketing_guardar(informe["objetivo"], informe["url"], informe["tipo"],
                              informe["puntaje"], informe["motores"], informe["redes"],
                              informe["motores"][0]["hallazgos"], informe["resumen"],
                              contenido=informe["contenido"])
    flash("Analisis listo: %d/100 en buscadores. Faltan %d correcciones criticas."
          % (informe["puntaje"],
             sum(x["errores"] for x in informe["motores"])), "exito")
    return redirect(url_for("admin_marketing", id=aid))


@app.route("/admin/marketing/<int:analisis_id>/plan", methods=["POST"])
@requiere_admin
def admin_marketing_plan(analisis_id):
    import marketing
    fila = _marketing_analisis_listo(db.marketing_analisis(analisis_id))
    if not fila:
        abort(404)
    informe = {"url": fila["url"], "objetivo": fila["objetivo"], "puntaje": fila["puntaje"],
               "motores": fila["motores"], "redes": fila["redes"],
               "contenido": fila["contenido"]}
    try:
        texto = marketing.plan_ia(informe)
    except marketing.MarketingError as exc:
        db.marketing_actualizar_consejos(analisis_id, str(exc), ia=0)
        flash(str(exc), "aviso")
        return redirect(url_for("admin_marketing", id=analisis_id))
    except Exception:
        app.logger.exception("Fallo el plan de marketing")
        flash("El servicio de IA no respondio. Revisa la clave y el modelo en "
              "/etc/derechoson.env.", "error")
        return redirect(url_for("admin_marketing", id=analisis_id))
    db.marketing_actualizar_consejos(analisis_id, texto, ia=1)
    flash("Plan paso a paso generado con IA.", "exito")
    return redirect(url_for("admin_marketing", id=analisis_id))


@app.route("/admin/marketing/<int:analisis_id>/eliminar", methods=["POST"])
@requiere_admin
def admin_marketing_eliminar(analisis_id):
    db.marketing_eliminar(analisis_id)
    flash("Analisis eliminado del historial.", "exito")
    return redirect(url_for("admin_marketing"))


# ------- contacto público
@app.route("/contacto", methods=["POST"])
def contacto_publico():
    nombre = request.form.get("nombre", "").strip()
    correo = request.form.get("correo", "").strip()
    mensaje = request.form.get("mensaje", "").strip()
    if not nombre or "@" not in correo or not mensaje:
        flash("Completa tu nombre, correo y mensaje para enviarnos tu solicitud.", "error")
        return redirect(url_for("inicio") + "#contacto")
    db.contacto_crear({
        "nombre": nombre, "correo": correo,
        "telefono": request.form.get("telefono", "").strip(),
        "asunto": request.form.get("asunto", "").strip(),
        "mensaje": mensaje})
    _enviar_notificacion("contacto", {
        "nombre": nombre, "correo": correo,
        "telefono": request.form.get("telefono", "").strip(),
        "asunto": request.form.get("asunto", "").strip(),
        "mensaje": mensaje})
    _registrar_interaccion("contacto", detalle=nombre + " · " + (request.form.get("asunto", "").strip() or "Mensaje de la web"))
    flash("Recibimos tu mensaje. Te contactaremos en menos de 24 horas hábiles.", "exito")
    return redirect(url_for("inicio") + "#contacto")


# ------- agenda de citas pública
HORAS_CITA = ["08:00", "09:00", "10:00", "11:00", "14:00", "15:00", "16:00"]


@app.route("/agendar/horas")
def agendar_horas_disponibles():
    fecha = fecha_parse(request.args.get("fecha", ""))
    abogado_id = request.args.get("abogado_id", type=int)
    if not fecha:
        return jsonify({"horas": []})
    return jsonify({"horas": _horas_disponibles(fecha, abogado_id)})


@app.route("/agendar", methods=["GET", "POST"])
def agendar_cita():
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        correo = request.form.get("correo", "").strip()
        fecha = request.form.get("fecha", "").strip()
        hora = request.form.get("hora", "").strip()
        if (not nombre or "@" not in correo or not fecha or not hora):
            flash("Completa tu nombre, correo, fecha y hora para agendar la cita.", "error")
            return redirect(url_for("agendar_cita"))
        fecha_obj = fecha_parse(fecha)
        if not fecha_obj or hora not in _horas_disponibles(
                fecha_obj,
                int(request.form.get("abogado_id")) if request.form.get("abogado_id") else None):
            flash("Ese horario ya no está disponible. Elige otra hora.", "error")
            return redirect(url_for("agendar_cita"))
        abogado_id = request.form.get("abogado_id")
        abogado = db.abogado_por_id(int(abogado_id)) if abogado_id else None
        db.cita_crear({
            "nombre": nombre, "correo": correo,
            "telefono": request.form.get("telefono", "").strip(),
            "abogado_id": int(abogado_id) if abogado_id else None,
            "fecha": fecha, "hora": hora,
            "motivo": request.form.get("motivo", "").strip()})
        _enviar_notificacion("cita", {
            "nombre": nombre, "correo": correo,
            "telefono": request.form.get("telefono", "").strip(),
            "abogado_nombre": abogado["nombre"] if abogado else None,
            "fecha": fecha, "hora": hora,
            "motivo": request.form.get("motivo", "").strip()})
        _registrar_interaccion("cita", detalle=fecha + " " + hora)
        flash("Cita solicitada. Te confirmaremos por correo en la jornada siguiente.", "exito")
        return redirect(url_for("agendar_cita"))
    hoy = date.today().isoformat()
    return render_template("agendar.html", usuario=usuario_actual(),
                           abogados=db.abogados_lista(activos=True),
                           horas=HORAS_CITA, hoy=hoy)


# ------- política de privacidad
@app.route("/privacidad")
def privacidad():
    return render_template("privacidad.html", usuario=usuario_actual())


# ------- chatbot de orientación y agenda
DIA_NOMBRES = ["Lun", "Mar", "Mié", "Jue", "Vie"]


def _etiqueta_fecha(fecha):
    return "%s %02d/%02d" % (DIA_NOMBRES[fecha.weekday()], fecha.day, fecha.month)


def _opcion(valor, etiqueta):
    return {"v": valor, "t": etiqueta}


def _normaliza(texto):
    import unicodedata
    texto = (texto or "").strip().lower()
    return "".join(c for c in unicodedata.normalize("NFD", texto)
                   if unicodedata.category(c) != "Mn")


def _contiene(m, palabras):
    return any(p in m for p in palabras)


def _texto_contacto():
    c = db.contenido_todos()
    correo = c.get("contacto_correo") or "contacto@derechoson.co"
    telefono = c.get("contacto_telefono") or "+57 300 123 4567"
    direccion = c.get("contacto_direccion") or "Bogotá D.C."
    return ("Puedes escribirnos a %s, llamar al %s o visitarnos en %s."
            % (correo, telefono, direccion))


def _texto_horario():
    c = db.contenido_todos()
    return (c.get("contacto_horario")
            or "Atendemos de lunes a viernes, de 8:00 am a 4:00 pm, y coordinamos reuniones por cita previa.")


def _texto_inicio():
    try:
        areas = db.areas_todas()
    except Exception:
        areas = []
    lista = ", ".join(a["nombre"].replace("Derecho ", "").title()
                      for a in areas if a.get("nombre")) or "varias áreas"
    return ("¡Buen día! 👨‍⚖️ Soy Doctor On, el asistente jurídico de Derechos On. "
            "Resuelvo tu caso dentro de las áreas del despacho (%s). Cuéntame qué "
            "pasó y te oriento con la norma colombiana vigente, o agenda una cita "
            "con el equipo." % lista)


def _area_slug(nombre):
    """Convierte el nombre de un área ('Derecho Laboral') en su clave corta."""
    n = _normaliza(nombre).replace("derecho ", "").strip()
    return " ".join(n.split()) or (nombre or "").strip()

def _area_busca(m):
    claves = {
        "administrativo": ["administrativo", "nulidad", "entidades publicas", " entidad "],
        "civil": ["civil", "contratos", "sucesiones", "herencia", "inmueble", "arriendo",
                  "arrendamiento", "desalojo", "responsabilidad civil", "indemnizacion"],
        "comercial": ["comercial", "sociedad", "emprendimiento", "empresa", "mercantil", "insolvencia", "constituir"],
        "laboral": ["laboral", "trabajo", "despido", "despid", "despedid", "liquidacion", "pension", "riesgos laborales", "salario", "contrato laboral", "vacaciones"],
        "penal": ["penal", "defensa", "delito", "denuncia", "victima"],
        "familia": ["familia", "divorci", "separacion", "custodia", "visitas", "alimento",
                    "cuota alimentaria", "pension alimenticia", "matrimonio", "hijos",
                    "patria potestad", "violencia intrafamiliar", "convivencia"],
    }
    for nombre, palabras in claves.items():
        if _contiene(m, palabras):
            return nombre
    # las áreas registradas en la base de datos: primero por su nombre completo,
    # luego por sus palabras significativas, así Doctor On resuelve según las
    # áreas que el despacho realmente atiende.
    try:
        areas = db.areas_todas()
    except Exception:
        areas = []
    conteos = []
    for a in areas:
        if not a.get("nombre"):
            continue
        nombre_n = _normaliza(a["nombre"])
        slug = _area_slug(a["nombre"])
        if nombre_n and nombre_n in m:
            return slug
        tokens = [t for t in nombre_n.split() if len(t) > 4 and t != "derecho"]
        coinciden = sum(1 for t in tokens if t in m)
        if coinciden:
            conteos.append((coinciden + len(nombre_n), slug))
    if conteos:
        return sorted(conteos, reverse=True)[0][1]
    return None


def _texto_area_especifica(nombre):
    for a in db.areas_todas():
        if nombre in a["nombre"].lower():
            return (a["nombre"] + ": " + a["descripcion"] + "\n\n"
                    "En Derechos On atendemos este tipo de casos con abogados especializados. "
                    "Si quieres, podemos agendar una consulta para revisar tu situación.")
    return None


def _soluciones_juridicas(area, m):
    """Posibles soluciones jurídicas según el derecho colombiano."""
    base = ("\nEstas son posibles salidas jurídicas en el derecho colombiano:\n")
    opciones = []
    if area == "laboral":
        if _contiene(m, ("despido", "despid", "despedid")):
            opciones.append("• Despido sin justa causa: revisar la causa invocada y exigir indemnización (CST art. 64) o reintegro si hay fuero (sindical, embarazo, discapacidad).")
        if _contiene(m, ("liquidacion", "liquidación", "cesantia", "prima")):
            opciones.append("• Reclamar prestaciones sociales adeudadas (cesantías, primas, vacaciones) por vía laboral; el contrato realidad puede generar más derechos.")
        if _contiene(m, ("pension", "pensión")):
            opciones.append("• Exigir el reconocimiento pensional ante la AFP/Colpensiones y agotar las instancias; ante demora, procede acción de tutela.")
        if _contiene(m, ("riesgo", "accidente")):
            opciones.append("• Calificar el origen (laboral/común) ante la ARL e iniciar reclamación de prestaciones económicas y asistenciales.")
        if not opciones:
            opciones.append("• En materia laboral: conciliación ante el Ministerio de Trabajo o demanda ordinaria laboral, según lo que se reclame.")
    elif area == "familia":
        if _contiene(m, ("divorci", "separ")):
            opciones.append("• Divorcio por mutuo acuerdo en notaría (régimen patrimonial) o vía judicial por causales (Código Civil arts. 154 y siguientes).")
        if _contiene(m, ("custodia", "visitas", "hijos")):
            opciones.append("• Fijar custodia, visitas y cuota mediante conciliación o proceso ante el juez de familia; se puede pactar custodia compartida.")
        if _contiene(m, ("alimento", "cuota")):
            opciones.append("• Cobro de cuota de alimentos por conciliación en comisaría/defensoría o proceso ejecutivo de alimentos (Código de Infancia y Adolescencia).")
        if not opciones:
            opciones.append("• Los asuntos de familia suelen iniciar con conciliación extrajudicial y luego proceso ante el juez de familia.")
    elif area == "civil":
        if _contiene(m, ("arrendamiento", "arriendo", "desalojo")):
            opciones.append("• Restitución del inmueble por mora (Ley 820 de 2003) y cobro de cánones adeudados en proceso verbal de arrendamiento.")
        if _contiene(m, ("contrato", "incumpl")):
            opciones.append("• Exigir el cumplimiento del contrato (Código Civil arts. 1546 y 1609) o la resolución con indemnización de perjuicios.")
        if _contiene(m, ("responsabilidad", "indemnizacion", "perjuicio")):
            opciones.append("• Acción de responsabilidad civil extracontractual para reparar perjuicios (Código Civil art. 2341).")
        if _contiene(m, ("sucesion", "herencia", "hereder")):
            opciones.append("• Adelantar la sucesión por notaría (mutuo acuerdo) o judicial; reconocimiento de la herencia según orden de llamamiento (Código Civil arts. 1039 y ss.).")
        if not opciones:
            opciones.append("• En materia civil: exigir el cumplimiento o la reparación según el tipo de contrato o relación (Código Civil).")
    elif area == "comercial":
        if _contiene(m, ("constituir", "empresa", "sociedad", "emprend")):
            opciones.append("• Constituir una SAS por documento privado con registro ante la Cámara de Comercio (Ley 1258 de 2008), ideal para emprendedores.")
        if _contiene(m, ("insolvencia", "quiebra", "deudas")):
            opciones.append("• Proceso de reorganización o validación de acuerdos de la Ley 1116 de 2006 para empresas en crisis, evitando la liquidación.")
        if _contiene(m, ("contrato", "mercantil", "incumpl")):
            opciones.append("• Exigir obligaciones mercantiles (Código de Comercio) mediante proceso ejecutivo o declarativo, según el título.")
        if not opciones:
            opciones.append("• En derecho comercial: definir la estructura societaria adecuada y pactar contratos con cláusulas de resolución y garantías.")
    elif area == "penal":
        if _contiene(m, ("denuncia", "victima", "delito")):
            opciones.append("• Instaurar la denuncia ante la Fiscalía General de la Nación y activar la protección como víctima (Ley 906 de 2004).")
        if _contiene(m, ("defensa", "acusado", "imput")):
            opciones.append("• Ejercer el derecho de defensa con abogado desde la indagación; revisar medidas de aseguramiento y salidas alternativas (principio de oportunidad).")
        if not opciones:
            opciones.append("• En derecho penal: denuncia/preclusión según el rol (víctima o acusado), con acompañamiento de la defensa técnica.")
    elif area == "administrativo":
        if _contiene(m, ("nulidad", "anul")):
            opciones.append("• Acción de nulidad y restablecimiento del derecho ante la jurisdicción contencioso-administrativa (Ley 1437 de 2011, CPACA).")
        if _contiene(m, ("contrato", "estatal")):
            opciones.append("• Reclamar frente a la entidad por vía contractual administrativa y, si hay negativa, acudir a la jurisdicción de lo contencioso.")
        if not opciones:
            opciones.append("• Frente a actos de entidades públicas: petición, recursos en sede administrativa y luego la acción correspondiente del CPACA.")
    return base + "\n".join(opciones) if opciones else ""


def _orientar(m):
    """Devuelve (texto_orientacion, area_detectada)."""
    area = _area_busca(m)
    ori = _texto_area_especifica(area) if area else None
    texto = ""
    if ori:
        texto = ori
    else:
        texto = ("He analizado tu consulta. En Derechos On un abogado podrá darte un "
                 "concepto preciso, pero con base en el derecho colombiano la idea "
                 "general es la siguiente:")
    sol = _soluciones_juridicas(area, m) if area else ("\nExisten acciones y remedios según la rama del "
                                                       "derecho aplicable (laboral, civil o de familia entre "
                                                       "otras). Podemos revisarlo en detalle en una consulta.")
    return texto + sol, area


def _texto_areas():
    areas = db.areas_todas()
    if not areas:
        return "Puedo orientarte sobre nuestros servicios. Escríbenos en el formulario de contacto."
    lineas = ["Nuestras áreas de atención son:"]
    for a in areas:
        lineas.append("• %s: %s" % (a["nombre"], a["descripcion"]))
    lineas.append("¿Quieres agendar una cita con un abogado?")
    return "\n".join(lineas)


def _texto_honorarios():
    return ("En Derechos On los honorarios dependen del tipo de servicio y de tu caso. "
            "Ofrecemos consulta inicial, honorarios por proceso y planes como mensualidad. "
            "Lo más preciso es agendar una consulta para darte una cotización ajustada a tu asunto.")


def _texto_quienes():
    return ("Somos Derechos On, una firma de abogados enfocada en acompañar a personas y empresas "
            "con servicios jurídicos claros y cercanos. Trabajamos varias áreas del derecho; "
            "mira la lista en 'Ver servicios'.")


def _texto_privacidad():
    return ("Toda la información que nos confíes está protegida por la reserva profesional "
            "(Ley 1123 de 2007) y tratamos tus datos conforme a la Ley 1581 de 2012, "
            "solo para atender tu caso.")


def _texto_proceso():
    return ("Por lo general el proceso empieza con una consulta inicial: te escuchamos, "
            "estudiamos tu caso y te explicamos las opciones y etapas. Luego definimos el encargo "
            "y, si es necesario, firmamos un contrato de prestación de servicios jurídicos.")


def _texto_fallback():
    return ("No estoy seguro de haber entendido 😅. ¿Te ayudo con 'servicios', "
            "'agendar cita', 'honorarios' o datos de 'contacto'?")


def _responder_fechas():
    dias = _dias_disponibles()
    if not dias:
        return ("En este momento no hay fechas disponibles en el horario "
                "de atención (lunes a viernes, 8 am a 4 pm, sin festivos). "
                "Inténtalo mañana o escríbenos en el formulario de contacto.",
                [_opcion("servicios", "Ver servicios")])
    msj = "Claro. ¿Qué día te queda bien? (lunes a viernes, sin festivos):\n" + \
          "\n".join("%d. %s — %d horarios" % (i + 1, _etiqueta_fecha(d),
                                               len(_horas_disponibles(d)))
                    for i, d in enumerate(dias))
    return msj, [_opcion(d.isoformat(), _etiqueta_fecha(d)) for d in dias]


def _responder_horas(fecha):
    horas = _horas_disponibles(fecha)
    if not horas:
        return ("Ese día ya no tiene horarios libres. Elige otro día:",
                [_opcion("volver", "Ver otras fechas")])
    return ("Para el %s tenemos estos horarios libres (8 am a 4 pm):" % _etiqueta_fecha(fecha),
            [_opcion(h, h) for h in horas] + [_opcion("volver", "← Otra fecha")])


PREGUNTAS_CASO = [
    "¿Hace cuánto ocurrió la situación o desde cuándo está en curso?",
    "¿Qué documentos o pruebas tienes del caso? (contratos, correos, recibos, mensajes)",
    "¿Ya hubo un trámite previo? (reclamo, conciliación, demanda, denuncia o intento de acuerdo)",
]


def _flujo_agenda(mensaje, chat):
    m = _normaliza(mensaje)
    paso = chat.get("paso")
    consulta = chat.get("consulta")

    if paso == "pedir_consulta":
        if m in ("volver", "cancelar"):
            return ("No hay problema. ¿En qué más te ayudo?",
                    {"paso": "inicio"}, [_opcion("servicios", "Ver servicios"),
                                         _opcion("agendar", "Agendar cita")])
        if len(m) < 15:
            return ("Cuéntame un poco más tu situación (al menos 15 caracteres) "
                    "para orientarte bien 🙂", chat, {})
        return ("Gracias. Para orientarte mejor y preparar tu consulta, déjame "
                "hacerte 3 preguntas rápidas sobre tu caso.\n\n" +
                "1️⃣ " + PREGUNTAS_CASO[0],
                {"paso": "pregunta_1", "consulta": mensaje.strip()}, {})

    if paso in ("pregunta_1", "pregunta_2", "pregunta_3"):
        idx = int(paso[-1])
        if m in ("volver", "cancelar"):
            return ("Entendido, lo dejamos ahí. ¿Quieres agendar de todos modos?",
                    {"paso": "inicio", "consulta": consulta},
                    [_opcion("agendar", "Agendar cita"), _opcion("servicios", "Ver servicios")])
        if len(m) < 3:
            return ("Escribe una respuesta breve para seguir 🙂", chat, {})
        respuestas = list(chat.get("respuestas") or []) + [mensaje.strip()]
        if idx < 3:
            return (("✅ Anotado.\n\n%s") % PREGUNTAS_CASO[idx],
                    {"paso": "pregunta_%d" % (idx + 1), "consulta": consulta,
                     "respuestas": respuestas}, {})
        detalle = "\n".join("• %s: %s" % (PREGUNTAS_CASO[i].split(" ")[0], r)
                            for i, r in enumerate(respuestas))
        resumen = "%s | Antecedentes: %s" % (consulta, " / ".join(respuestas))
        texto_orient, _area = _orientar(consulta or "")
        texto = (texto_orient + "\n\nGracias por la información 📋. Ya tengo el contexto "
                 "de tu caso y te oriento sobre las salidas jurídicas antes de agendar.")
        return (texto, {"paso": "inicio", "consulta": resumen},
                [_opcion("agendar", "Agendar cita con este tema"),
                 _opcion("servicios", "Ver servicios")])

    if paso == "pedir_hora":
        if m == "volver":
            msj, ops = _responder_fechas()
            return msj, {"paso": "pedir_hora", "consulta": consulta}, ops
        fecha = _fecha_en(mensaje)
        if fecha and _es_dia_habil(fecha) and fecha >= date.today():
            msj, ops = _responder_horas(fecha)
            return msj, {"paso": "pedir_fecha", "fecha": fecha.isoformat(),
                         "consulta": consulta}, ops
        msj, ops = _responder_fechas()
        return msj, {"paso": "pedir_hora", "consulta": consulta}, ops

    if paso == "pedir_fecha":
        f = fecha_parse(chat.get("fecha"))
        if m == "volver":
            msj, ops = _responder_fechas()
            return msj, {"paso": "pedir_hora", "consulta": consulta}, ops
        hora = _hora_en(mensaje)
        if hora and f and hora in _horas_disponibles(f):
            return ("¿Con qué nombre te registramos? 😊",
                    {"paso": "pedir_nombre", "fecha": f.isoformat(), "hora": hora,
                     "consulta": consulta}, {})
        msj, ops = _responder_horas(f) if f else _responder_fechas()
        return msj, {"paso": "pedir_fecha", "fecha": f.isoformat(),
                     "consulta": consulta}, ops

    if paso == "pedir_nombre":
        if len(m) < 2:
            return ("Escribe tu nombre para continuar 🙂", chat, {})
        clean = " ".join(w.capitalize() for w in mensaje.strip().split())
        return ("Perfecto. Dime tu correo para confirmarte la cita:",
                {"paso": "pedir_correo", "fecha": chat.get("fecha"),
                 "hora": chat.get("hora"), "nombre": clean, "consulta": consulta}, {})

    if paso == "pedir_correo":
        if "@" not in m or "." not in m:
            return ("Ese correo no parece válido. Inténtalo de nuevo (ej. nombre@correo.com).", chat, {})
        nombre = chat.get("nombre", "")
        f = fecha_parse(chat.get("fecha"))
        hora = chat.get("hora", "")
        if not f or hora not in _horas_disponibles(f):
            msj, ops = _responder_fechas()
            return msj, {"paso": "pedir_hora", "consulta": consulta}, ops
        motivo = (consulta or "")[:300]
        abogado_id = _abogado_libre(f, hora)
        db.cita_crear({"nombre": nombre, "correo": m, "abogado_id": abogado_id,
                       "fecha": f.isoformat(), "hora": hora, "motivo": motivo})
        _enviar_notificacion("cita", {"nombre": nombre, "correo": m,
                                      "fecha": f.isoformat(), "hora": hora,
                                      "motivo": motivo, "abogado_id": abogado_id})
        if motivo:
            confirmacion = ("¡Listo, %s! 🎉 Tu cita para el %s a las %s quedó solicitada "
                            "con tu consulta: \"%s\". Te confirmaremos por correo."
                            % (nombre, _etiqueta_fecha(f), hora, motivo))
        else:
            confirmacion = ("¡Listo, %s! 🎉 Tu cita para el %s a las %s quedó solicitada.\n"
                            "Te confirmaremos por correo en la jornada siguiente."
                            % (nombre, _etiqueta_fecha(f), hora))
        return (confirmacion, {"paso": "inicio"},
                [_opcion("servicios", "Ver servicios"), _opcion("agendar", "Otra cita")])

    return None


def _procesar_chat(mensaje, chat):
    """Devuelve (texto_respuesta, nuevo_estado_chat, opciones)."""
    m = _normaliza(mensaje)
    paso = chat.get("paso", "inicio")

    # --- flujo de agenda / entrevista del caso en curso ---
    if paso in ("pedir_hora", "pedir_fecha", "pedir_nombre", "pedir_correo",
                "pedir_consulta", "pregunta_1", "pregunta_2", "pregunta_3"):
        res = _flujo_agenda(mensaje, chat)
        if res:
            return res

    # --- conversación libre ---
    if not m:
        ops = [_opcion("servicios", "Ver servicios"), _opcion("agendar", "Agendar cita")]
        return _texto_inicio(), {"paso": "inicio"}, ops

    if _contiene(m, ("cita", "agendar", "reservar", "turno", "dispon",
                     "reunion", "apartar", "fecha libre", "fecha")):
        msj, ops = _responder_fechas()
        nuevo = {"paso": "pedir_hora"}
        if chat.get("consulta"):
            nuevo["consulta"] = chat.get("consulta")
        return msj, nuevo, ops

    if _contiene(m, ("honorario", "costo", "valor", "precio", "tarifa", "cuanto vale",
                     "cuanto cobra", "cuanto cuesta", "cobran", "presupuesto",
                     "pago", "pagar", "cotizacion")):
        return (_texto_honorarios(), {"paso": "inicio"},
                [_opcion("agendar", "Agendar cita"), _opcion("servicios", "Ver servicios")])

    if _contiene(m, ("abogado", "equipo", "profesion", "quienes", "quien es")):
        return (_texto_quienes(), {"paso": "inicio"},
                [_opcion("servicios", "Ver servicios"), _opcion("agendar", "Agendar cita")])

    area = _area_busca(m)
    if area:
        especifico = _texto_area_especifica(area)
        if especifico:
            soluciones = _soluciones_juridicas(area, m)
            texto = especifico + (soluciones if soluciones else "")
            return (texto + "\n\n¿Quieres agendar una cita sobre este tema?",
                    {"paso": "inicio", "consulta": "Tengo un caso de %s" % area},
                    [_opcion("agendar", "Agendar cita con este tema"),
                     _opcion("consulta", "Quiero dejar mi consulta")])

    if _contiene(m, ("servicio", "area", "orient", "asesor", "que hacen", "que ofrecen",
                     "materia", "especialidad", "consultoria", "ramas del derecho",
                     "ayudan", "ayuda", "derecho")):
        return (_texto_areas() + "\n\nPregúntame por una de estas áreas (ej. 'divorcio') "
                "y te oriento en tu consulta antes de agendar.",
                {"paso": "inicio"}, [_opcion("agendar", "Agendar cita")])

    if _contiene(m, ("consulta", "duda", "pregunta", "quiero saber", "querria saber",
                     "mi situacion", "mi caso", "un caso", "me pueden ayudar",
                     "como hago", "que hago", "asesori", "necesito saber si",
                     "puedo demandar", "tengo derecho")):
        return (("Claro, cuéntame tu consulta o situación y te oriento ahora mismo 😊\n"
                 "Descríbela brevemente (p. ej. 'me despidieron sin liquidación') y "
                 "después podemos agendar la cita con ese tema."),
                {"paso": "pedir_consulta", "consulta": chat.get("consulta")},
                [_opcion("volver", "Cancelar consulta")])

    if _contiene(m, ("horario", "atendemos", "horas", "jornada", "atencion", "abierto",
                     "lunes a viernes", "cuando atienden")):
        return (_texto_horario() + " " + _texto_contacto(),
                {"paso": "inicio"}, [_opcion("agendar", "Agendar cita")])

    if _contiene(m, ("contacto", "telefono", "correo", "mail", "direccion", "ubicacion",
                     "donde estan", "oficina", "escribir", "llamar", "whatsapp", "celular")):
        return (_texto_contacto() + " " + _texto_horario(),
                {"paso": "inicio"}, [_opcion("agendar", "Agendar cita")])

    if _contiene(m, ("confidencial", "privacidad", "datos", "secreto", "reserva",
                     "seguridad", "1581")):
        return (_texto_privacidad(), {"paso": "inicio"},
                [_opcion("contacto", "Datos de contacto"), _opcion("agendar", "Agendar cita")])

    if _contiene(m, ("proceso", "como funciona", "pasos", "etapas", "que necesito",
                     "documentos", "contrato")):
        return (_texto_proceso(), {"paso": "inicio"},
                [_opcion("agendar", "Agendar cita"), _opcion("servicios", "Ver servicios")])

    if _contiene(m, ("gracias", "genial", "excelente", "perfecto", "ok", "okay", "bien")):
        return ("¡Con mucho gusto! 😊 Aquí estaré para lo que necesites. ¿Te ayudo "
                "con 'servicios' o prefieres agendar una cita?",
                {"paso": "inicio"},
                [_opcion("servicios", "Ver servicios"), _opcion("agendar", "Agendar cita")])

    if _contiene(m, ("chao", "adios", "hasta luego", "bye", "nos vemos")):
        return ("¡Hasta luego! 👋 Si nos necesitas, aquí estaré.",
                {"paso": "inicio"}, [])

    if _contiene(m, ("hola", "buenas", "buenos dias", "buenas tardes", "buenas noches",
                     "hi", "hey", "que mas", "buen dia", "saludos")):
        return (_texto_inicio(), {"paso": "inicio"},
                [_opcion("servicios", "Ver servicios"), _opcion("agendar", "Agendar cita")])

    if paso == "servicios" and _contiene(m, ("agendar", "cita")):
        msj, ops = _responder_fechas()
        return msj, {"paso": "pedir_hora"}, ops

    return (_texto_fallback(), {"paso": "inicio"},
            [_opcion("servicios", "Ver servicios"), _opcion("agendar", "Agendar cita"),
             _opcion("contacto", "Datos de contacto")])


def _fecha_en(texto):
    import re
    mm = re.search(r"(\d{4})-(\d{2})-(\d{2})", texto)
    if mm:
        return fecha_parse(texto[mm.start():mm.end()])
    mm2 = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", texto)
    if mm2:
        return fecha_parse("%s-%s-%s" % (mm2.group(3), mm2.group(2), mm2.group(1)))
    return None


def _hora_en(texto):
    import re
    mm = re.search(r"(\d{2}):(\d{2})", texto)
    if mm and texto[mm.start():mm.end()] in HORAS_CITA:
        return texto[mm.start():mm.end()]
    return None


LARGO_MAX_CHAT = 1200


def _contexto_despacho():
    """Arma el contexto real del despacho que se le pasa al asistente.

    Se arma desde la base de datos para que el asistente nunca invente datos
    de contacto, areas ni honorarios.
    """
    c = db.contenido_todos()
    partes = []

    contacto = []
    if c.get("contacto_correo"):
        contacto.append("correo %s" % c["contacto_correo"])
    if c.get("contacto_telefono"):
        contacto.append("telefono %s" % c["contacto_telefono"])
    if c.get("contacto_direccion"):
        contacto.append("direccion %s" % c["contacto_direccion"])
    if c.get("contacto_horario"):
        contacto.append("horario %s" % c["contacto_horario"])
    if contacto:
        partes.append("DATOS DEL DESPACHO: " + ", ".join(contacto) + ".")

    try:
        areas = db.areas_todas()
    except Exception:
        areas = []
    if areas:
        linea = "; ".join("%s: %s" % (a.get("nombre", ""), (a.get("descripcion") or "").strip())
                          for a in areas if a.get("nombre"))
        if linea:
            partes.append("AREAS QUE ATIENDEN:\n%s" % linea[:4000])

    try:
        honorarios = db.contenido_todos().get("texto_honorarios") or ""
    except Exception:
        honorarios = ""
    if honorarios:
        partes.append("HONORARIOS Y CONDICIONES DEL DESPACHO:\n%s" % honorarios.strip()[:1500])

    try:
        proceso = db.contenido_todos().get("texto_proceso") or ""
    except Exception:
        proceso = ""
    if proceso:
        partes.append("COMO TRABAJA EL DESPACHO:\n%s" % proceso.strip()[:1200])

    try:
        entradas = db.noticias_lista(limite=6)
    except Exception:
        entradas = []
    titulos = [str(n.get("titulo", "")).strip() for n in (entradas or []) if n.get("titulo")]
    if titulos:
        partes.append("ARTICULOS PUBLICADOS EN EL SITIO:\n- " + "\n- ".join(titulos[:6]))

    return "\n\n".join(partes)


def _rate_limit_chat(limite=12, segundos=300):
    """Limita las preguntas por sesion para no abuso de la IA."""
    ahora = time.time()
    hist = [t for t in (session.get("chat_preguntas") or []) if ahora - t < segundos]
    if len(hist) >= limite:
        faltan = int(segundos - (ahora - hist[0])) // 60 + 1
        return faltan
    session["chat_preguntas"] = hist + [ahora]
    return 0


def _historial_chat(n=8):
    """Ultimos turnos de la conversacion para darle contexto."""
    salida = []
    for turno in (session.get("chat_historial") or [])[-n:]:
        if not isinstance(turno, dict):
            continue
        texto = (turno.get("contenido") or "").strip()
        if not texto:
            continue
        rol = "assistant" if turno.get("rol") == "asistente" else "user"
        salida.append({"role": rol, "content": texto[:2000]})
    return salida


def _evento(nombre, **campos):
    """Serializa un evento SSE."""
    datos = {"tipo": nombre}
    datos.update(campos)
    return "data: %s\n\n" % json.dumps(datos, ensure_ascii=False)


@app.route("/api/jarvis", methods=["POST"])
def jarvis_chat():
    """Asistente juridico con IA, respuesta en streaming (SSE).

    Si la IA no esta disponible cae al motor de reglas existente para que el
    chat nunca deje de funcionar.
    """
    datos = request.get_json(silent=True) or {}
    mensaje = str(datos.get("mensaje") or "").strip()

    if not mensaje:
        return Response(_evento("error", texto="Escribe tu consulta para poder ayudarte."),
                        mimetype="text/event-stream")
    if len(mensaje) > LARGO_MAX_CHAT:
        mensaje = mensaje[:LARGO_MAX_CHAT]
        aviso = ("Recorté tu mensaje a %d caracteres para poder procesarlo. "
                 "Si tu caso es largo, cuéntame lo esencial." % LARGO_MAX_CHAT)
    else:
        aviso = ""

    espera = _rate_limit_chat()
    if espera:
        return Response(_evento("error", texto=(
            "Has hecho muchas consultas seguidas. Espera %d minutos antes de "
            "continuar para que el asistente siga disponible." % espera)),
            mimetype="text/event-stream")

    def fallback():
        """Motor de reglas: garantiza respuesta aunque no haya IA.

        El chat de Jarvis resuelve la cita con su propio panel inline, asi que
        aqui el estado siempre arranca limpio para no mezclar los dos flujos.
        """
        texto, _nuevo, opciones = _procesar_chat(mensaje, {"paso": "inicio"})
        return texto, [{"v": o["v"], "t": o["t"]} for o in (opciones or [])]

    def guardar(rol, contenido):
        hist = session.get("chat_historial") or []
        hist.append({"rol": rol, "contenido": contenido[:2000]})
        session["chat_historial"] = hist[-12:]

    def generar():
        yield _evento("inicio", aviso=aviso, ia=bool(ia_juridica.configurado()))

        mensajes = _historial_chat()
        mensajes.append({"role": "user", "content": mensaje})

        texto_completo = ""
        uso_ia = False
        ia_visible = False

        # Texto oficial vigente de las normas que el usuario esta pisando. Se
        # busca una sola vez por consulta y solo para las normas tematicas que
        # correspondan; si la red falla se sigue con lo que haya en cache.
        try:
            normas = conocimiento_juridico.fragmentos(mensaje, limite=4)
        except Exception:
            normas = []

        if ia_juridica.configurado():
            try:
                sistema = ia_juridica.SISTEMA_CHAT
                contexto = _contexto_despacho()
                if contexto:
                    sistema = sistema + "\n\nINFORMACION REAL DEL DESPACHO (úsala, no la inventes):\n" + contexto
                if normas:
                    sistema = sistema + (
                        "\n\nTEXTO OFICIAL VERIFICADO DE LA NORMATIVA COLOMBIANA "
                        "(citado de la fuente oficial; cítalo textualmente y no "
                        "lo reescribas ni lo completes):\n"
                        + conocimiento_juridico.redactar(normas)
                    )
                for trozo in ia_juridica.consultar_stream(mensajes, sistema=sistema,
                                                          max_tokens=1800, temperatura=0.4):
                    if trozo:
                        ia_visible = True
                    texto_completo += trozo
                    yield _evento("delta", texto=trozo)
                uso_ia = True
            except Exception:
                texto_completo = ""
                # Si ya habíamos mostrado texto de la IA hay que descartarlo en
                # el navegador antes de enviar la respuesta del modo sin IA.
                if ia_visible:
                    yield _evento("reinicio")

        if not uso_ia:
            texto, opciones = fallback()
            texto_completo = texto
            # Se entrega en trozos para que el efecto de escritura sea el mismo
            for trozo in _trocear(texto, 26):
                yield _evento("delta", texto=trozo)
            yield _evento("opciones", opciones=opciones)

        texto_limpio = texto_completo.strip()
        if texto_limpio:
            yield _evento("fin", texto=texto_limpio,
                          fuentes=_fuentes_de(texto_limpio, mensaje, normas))
            guardar("usuario", mensaje)
            guardar("asistente", texto_limpio)
        else:
            yield _evento("error", texto=(
                "No pude responder en este momento. Puedes escribirnos por el "
                "formulario de contacto o intentarlo de nuevo en un rato."))

    respuesta = Response(stream_with_context(generar()), mimetype="text/event-stream")
    respuesta.headers["Cache-Control"] = "no-cache, no-transform"
    respuesta.headers["X-Accel-Buffering"] = "no"
    respuesta.headers["Connection"] = "keep-alive"
    try:
        _registrar_interaccion("chat_mensaje", detalle=mensaje[:200])
    except Exception:
        pass
    return respuesta


def _trocear(texto, tamano=26):
    """Parte un texto en trozos del tamaño pedido."""
    limpio = str(texto or "")
    for i in range(0, len(limpio), tamano):
        yield limpio[i:i + tamano]


# Texto que se muestra como referencia al pie de la respuesta. Solo se usa para
# detectar la norma citada; la fundamentacion real llega de
# `conocimiento_juridico`, que descarga el texto oficial vigente y verificado.
# Los numeros de norma estan corregidos: el CST es el Decreto 2663 de 1950, el
# CGP es la Ley 1564 de 2012, el Codigo Civil se adopto por la Ley 57 de 1887 y
# el Codigo de Comercio es el Decreto 410 de 1971.
NOTAS_LEY = [
    ("CST", "Codigo Sustantivo del Trabajo (Decreto 2663 de 1950)"),
    ("CPACA", "Codigo de Procedimiento Administrativo y de lo Contencioso Administrativo (Ley 1437 de 2011)"),
    ("CGP", "Codigo General del Proceso (Ley 1564 de 2012)"),
    ("Codigo Civil", "Codigo Civil (Ley 57 de 1887)"),
    ("Codigo de Comercio", "Codigo de Comercio (Decreto 410 de 1971)"),
    ("Codigo Penal", "Codigo Penal (Ley 599 de 2000)"),
    ("Ley 1581", "Ley 1581 de 2012 - proteccion de datos personales"),
    ("Ley 820", "Ley 820 de 2003 - regimen de arrendamiento de vivienda urbana"),
    ("Ley 1258", "Ley 1258 de 2008 - sociedades por accion simplificada"),
    ("Ley 1116", "Ley 1116 de 2006 - regimen de insolvencia empresarial"),
    ("Ley 906", "Ley 906 de 2004 - Codigo Penal Procedimental"),
    ("Ley 2466", "Ley 2466 de 2025 - reforma laboral"),
    ("Constitucion Politica", "Constitucion Politica de Colombia"),
    ("Articulo 206", "Articulo 206 del CST - forma de llevar a cabo el despido"),
    ("Articulo 189", "Articulo 189 del CST - indemnizacion por despido sin justa causa"),
    ("Articulo 2532", "Articulo 2532 del Codigo Civil - prescripcion"),
]


def _fuentes_de(texto, consulta="", frags=None):
    """Normas que respaldan la respuesta, para mostrarlas como pills.

    Primero van las citas que el asistente acabo de leer del texto oficial
    verificado (con URL y fecha de consulta); despues, las referencias
    detectadas por nombre en la respuesta.
    """
    fuentes = []
    vistos = set()

    def agregar(etiqueta, descripcion, url="", fecha=""):
        clave = str(etiqueta).strip().lower()
        if not clave or clave in vistos:
            return
        vistos.add(clave)
        item = {"t": str(etiqueta), "d": descripcion}
        if url:
            item["url"] = url
        if fecha:
            item["fecha"] = fecha
        fuentes.append(item)

    try:
        urls = conocimiento_juridico.urls_de(consulta or texto, limite=4, frags=frags)
        for item in urls:
            agregar(item.get("t"), item.get("d"), item.get("url", ""), item.get("fecha", ""))
    except Exception:
        pass

    bajo = str(texto or "").lower()
    for etiqueta, descripcion in NOTAS_LEY:
        if len(fuentes) >= 8:
            break
        if etiqueta.lower() in bajo:
            agregar(etiqueta, descripcion)
    return fuentes[:8]


@app.route("/api/jarvis/cita", methods=["POST"])
def jarvis_cita():
    """Aparta una cita solicitada desde el chat.

    Reutiliza la disponibilidad real del despacho (dias habiles, agenda de
    abogados y control de doble reserva).
    """
    datos = request.get_json(silent=True) or {}
    fecha_txt = str(datos.get("fecha") or "").strip()
    hora = str(datos.get("hora") or "").strip()
    nombre = str(datos.get("nombre") or "").strip()
    correo = str(datos.get("correo") or "").strip().lower()
    telefono = str(datos.get("telefono") or "").strip()
    motivo = str(datos.get("motivo") or "").strip()[:300]

    faltan = [n for n, v in (("nombre", nombre), ("correo", correo)) if not v]
    if faltan:
        return jsonify({"ok": False, "error": "Completa tu nombre y tu correo."}), 400
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", correo):
        return jsonify({"ok": False, "error": "Escribe un correo electrónico válido."}), 400
    if len(nombre) < 3:
        return jsonify({"ok": False, "error": "Escribe tu nombre completo."}), 400

    f = _fecha_en(fecha_txt)
    if f is None:
        return jsonify({"ok": False, "error": "Elige una fecha válida."}), 400
    if f < date.today() or not _es_dia_habil(f):
        return jsonify({"ok": False, "error": "Esa fecha no es un día hábil."}), 400
    if hora not in HORAS_CITA:
        return jsonify({"ok": False, "error": "Elige una hora válida."}), 400
    # La disponibilidad real decide: si no hay abogados activos el despacho
    # opera con agenda general, igual que el formulario /agendar.
    if hora not in _horas_disponibles(f):
        return jsonify({"ok": False,
                        "error": "Esa hora ya se ocupó. Elige otra del mismo día."}), 409

    abogado_id = _abogado_libre(f, hora) if db.abogados_lista(activos=True) else None

    try:
        db.cita_crear({
            "nombre": nombre,
            "correo": correo,
            "telefono": telefono,
            "abogado_id": abogado_id,
            "fecha": f.isoformat(),
            "hora": hora,
            "motivo": motivo or "Consulta solicitada desde el chat",
        })
    except Exception:
        return jsonify({"ok": False, "error": "No pudimos registrar la cita. Intenta de nuevo."}), 500

    try:
        _enviar_notificacion("cita", {
            "nombre": nombre,
            "correo": correo,
            "telefono": telefono,
            "abogado_nombre": None,
            "fecha": f.isoformat(),
            "hora": hora,
            "motivo": motivo,
        })
    except Exception:
        pass

    try:
        _registrar_interaccion("cita", detalle=f.isoformat() + " " + hora)
    except Exception:
        pass

    session.pop("chat_cita", None)
    return jsonify({
        "ok": True,
        "fecha": f.isoformat(),
        "hora": hora,
        "texto": ("Listo. Tu cita quedó apartada para el %s a las %s. "
                  "Te enviamos la confirmación al correo." % (
                      fecha_es(f.isoformat()), hora)),
    })


@app.route("/api/jarvis/disponibilidad", methods=["GET"])
def jarvis_disponibilidad():
    """Días y horas libres reales para el panel de agenda del chat."""
    dias = _dias_disponibles(limite=5)
    salida = []
    for d in dias:
        salida.append({
            "fecha": d.isoformat(),
            "etiqueta": fecha_es(d.isoformat()),
            "horas": _horas_disponibles(d),
        })
    return jsonify({"dias": salida})


@app.route("/chat", methods=["POST"])
def chat_bot():
    datos = request.get_json(silent=True) or {}
    mensaje = (datos.get("mensaje") or "").strip()
    chat = session.get("chat") or {"paso": "inicio"}
    texto, nuevo_chat, opciones = _procesar_chat(mensaje, chat)
    session["chat"] = nuevo_chat or {}
    _registrar_interaccion("chat_mensaje", detalle=mensaje)
    return jsonify({"mensaje": texto, "opciones": [{"v": o["v"], "t": o["t"]} for o in (opciones or [])]})


@app.route("/chat/nuevo", methods=["POST"])
def chat_nuevo():
    """Reinicia la conversación del chat para la sesión actual."""
    session["chat"] = {}
    return jsonify({"ok": True})


def _chat_a_html(usuario, filas):
    """Convierte la conversación del chat en un correo legible."""
    fecha = datetime.now().strftime("%d/%m/%Y · %I:%M %p")
    partes = [
        '<div style="font-family:Arial,Helvetica,sans-serif;max-width:620px;margin:0 auto">'
        '<div style="background:linear-gradient(90deg,#075e54,#128c7e);color:#fff;'
        'padding:20px 24px;border-radius:14px 14px 0 0">'
        '<div style="font-size:19px;font-weight:bold">Doctor On · Derechos On</div>'
        '<div style="font-size:13px;opacity:.9">Resumen de tu asesoría virtual</div></div>'
        '<div style="background:#f7f9fb;padding:18px 24px;border:1px solid #dfe3e8;border-top:none">'
        '<div style="font-size:12px;color:#75808c;margin-bottom:16px">Enviado el %s · para %s</div>' % (fecha, html_mod.escape(usuario)),
    ]
    for rol, texto in filas:
        cuerpo = html_mod.escape(texto).replace("\n", "<br>")
        if rol == "usuario":
            estilo = ('margin:0 0 12px 22%;background:#d9fdd3;border-radius:10px;'
                      'padding:10px 13px;font-size:14px;line-height:1.5')
        else:
            estilo = ('margin:0 22% 12px 0;background:#fff;border-radius:10px;'
                      'padding:10px 13px;font-size:14px;line-height:1.5;border:1px solid #e2e5ea')
        partes.append('<div style="%s"><b>%s</b><br>%s</div>' % (
            estilo, "Tú" if rol == "usuario" else "Doctor On", cuerpo))
    partes.append(
        '</div><div style="background:#eef1f4;padding:12px 24px;font-size:12px;color:#75808c;'
        'border-radius:0 0 14px 14px">Mensaje automático · no respondas a este correo. '
        'Para más información escribe a <a href="mailto:contacto@derechoson.co" '
        'style="color:#128c7e">contacto@derechoson.co</a>.</div></div>')
    return "".join(partes)


@app.route("/chat/enviar", methods=["POST"])
def chat_enviar():
    datos = request.get_json(silent=True) or {}
    correo = (datos.get("correo") or "").strip().lower()
    mensajes = datos.get("mensajes")

    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", correo):
        return jsonify({"ok": False, "error": "Escribe un correo electrónico válido."}), 400
    if not isinstance(mensajes, list) or not mensajes:
        return jsonify({"ok": False, "error": "Todavía no hay mensajes que enviar."}), 400

    ahora = time.time()
    hist = [t for t in (session.get("chat_envios") or []) if ahora - t < 3600]
    if len(hist) >= 3:
        return jsonify({"ok": False, "error": "Espera unos minutos antes de enviar otro correo."}), 429

    cfg = db.notif_config_de()
    if not cfg or not cfg.get("activo") or not cfg.get("correo") or not cfg.get("clave"):
        return jsonify({"ok": False, "error": "El correo de salida del sitio aún no está configurado."}), 500

    filas = []
    for m in mensajes[:150]:
        if not isinstance(m, dict):
            continue
        rol = "usuario" if m.get("rol") == "usuario" else "bot"
        texto = (m.get("texto") or "").strip()
        if not texto:
            continue
        filas.append((rol, texto))
    if not filas:
        return jsonify({"ok": False, "error": "Todavía no hay mensajes que enviar."}), 400

    try:
        webmail.enviar(cfg, correo, "Tu conversación con Doctor On · Derechos On",
                       _chat_a_html(correo, filas))
    except webmail.ErrorCorreo as e:
        return jsonify({"ok": False, "error": "El envío falló: %s" % e}), 502

    session["chat_envios"] = hist + [ahora]
    return jsonify({"ok": True})


@app.route("/admin/redes", methods=["GET", "POST"])
@requiere_admin
def admin_redes():
    cfg = redes.leer_config()

    if request.method == "POST":
        plataforma = request.form.get("plataforma")
        if plataforma not in cfg:
            flash("Plataforma desconocida.", "error")
            return redirect(url_for("admin_redes"))

        if request.form.get("accion") == "test":
            pruebas = {"linkedin": redes.test_linkedin,
                       "x": redes.test_x,
                       "instagram": redes.test_instagram}
            ok, msg = pruebas[plataforma]()
            flash("%s · %s" % (plataforma.title(), msg), "exito" if ok else "error")
            return redirect(url_for("admin_redes"))

        datos = cfg[plataforma]
        datos["activa"] = request.form.get("activa") == "1"
        datos["auto"] = request.form.get("auto") == "1"
        for campo in ("token", "autor_urn", "id_cuenta", "api_key", "api_secret",
                      "access_token", "access_secret"):
            if campo in request.form:
                datos[campo] = request.form.get(campo, "").strip()
        redes.guardar_config(cfg)
        flash("Configuración de %s guardada." % plataforma.title(), "exito")
        return redirect(url_for("admin_redes"))

    return render_template("admin/redes.html", usuario=g.usuario, config=cfg,
                           redactado=redes.redactar(cfg))


# ------- áreas de atención
@app.route("/admin/areas")
@requiere_admin
def admin_areas():
    return render_template("admin/areas.html", usuario=g.usuario,
                           areas=db.areas_todas())


@app.route("/admin/areas/crear", methods=["POST"])
@requiere_admin
def admin_areas_crear():
    db.ejecutar(
        "INSERT INTO areas (nombre, descripcion, icono) VALUES (?, ?, ?)",
        (request.form["nombre"].strip(), request.form.get("descripcion", "").strip(),
         request.form.get("icono", "scale").strip()))
    flash("Área de atención agregada.", "exito")
    return redirect(url_for("admin_areas"))


@app.route("/admin/areas/<int:aid>/editar", methods=["POST"])
@requiere_admin
def admin_areas_editar(aid):
    db.ejecutar(
        "UPDATE areas SET nombre = ?, descripcion = ?, icono = ? WHERE id = ?",
        (request.form["nombre"].strip(), request.form.get("descripcion", "").strip(),
         request.form.get("icono", "scale").strip(), aid))
    flash("Área actualizada.", "exito")
    return redirect(url_for("admin_areas"))


@app.route("/admin/areas/<int:aid>/eliminar", methods=["POST"])
@requiere_admin
def admin_areas_eliminar(aid):
    db.ejecutar("DELETE FROM areas WHERE id = ?", (aid,))
    flash("Área eliminada.", "exito")
    return redirect(url_for("admin_areas"))


# ------- contenido de la página
GRUPOS_CONTENIDO = [
    ("Portada · Carrusel", [
        ("hero1_titulo", "Slide 1 · Título"),
        ("hero1_texto", "Slide 1 · Texto"),
        ("hero2_titulo", "Slide 2 · Título"),
        ("hero2_texto", "Slide 2 · Texto"),
        ("hero3_titulo", "Slide 3 · Título"),
        ("hero3_texto", "Slide 3 · Texto"),
    ]),
    ("Portada · Quiénes somos", [
        ("quienes_titulo", "Título"),
        ("quienes_texto", "Primer párrafo"),
        ("quienes_texto2", "Segundo párrafo"),
    ]),
    ("Portada · Áreas", [
        ("areas_titulo", "Título"),
        ("areas_sub", "Subtítulo"),
    ]),
    ("Portada · Cifras", [
        ("stats_anios", "Años de experiencia del equipo"),
    ]),
    ("Portada · Digital", [
        ("digital_titulo", "Título"),
        ("digital_texto", "Texto"),
    ]),
    ("Portada · Artículos", [
        ("noticias_titulo", "Título"),
        ("noticias_sub", "Subtítulo"),
    ]),
    ("Portada · Contacto", [
        ("contacto_titulo", "Título"),
        ("contacto_sub", "Subtítulo"),
        ("contacto_correo", "Correo"),
        ("contacto_telefono", "Teléfono"),
        ("contacto_direccion", "Dirección"),
        ("contacto_horario", "Horario"),
    ]),
    ("Portada · Formulario de contacto", [
        ("contacto_form_titulo", "Título"),
        ("contacto_form_sub", "Subtítulo"),
    ]),
    ("Portada · Agenda de citas", [
        ("agendar_titulo", "Título de la página de agenda"),
    ]),
    ("Portada · Testimonios", [
        ("testimonios_titulo", "Título"),
        ("testimonios_sub", "Subtítulo"),
    ]),
    ("Portada · Preguntas frecuentes", [
        ("faq_titulo", "Título"),
        ("faq_sub", "Subtítulo"),
        ("faq1_p", "Pregunta 1"),
        ("faq1_r", "Respuesta 1"),
        ("faq2_p", "Pregunta 2"),
        ("faq2_r", "Respuesta 2"),
        ("faq3_p", "Pregunta 3"),
        ("faq3_r", "Respuesta 3"),
        ("faq4_p", "Pregunta 4"),
        ("faq4_r", "Respuesta 4"),
        ("faq5_p", "Pregunta 5"),
        ("faq5_r", "Respuesta 5"),
    ]),
    ("Pie de página", [
        ("footer_desc", "Descripción del despacho"),
    ]),
    ("Portal de clientes", [
        ("portal_mensaje", "Mensaje bajo el título de bienvenida"),
        ("portal_aviso", "Aviso destacado (se muestra solo si se escribe algo)"),
    ]),
]


@app.route("/admin/contenido", methods=["GET", "POST"])
@requiere_admin
def admin_contenido():
    if request.method == "POST":
        cambios = {clave: request.form.get(clave, "").strip()
                   for grupo, campos in GRUPOS_CONTENIDO for clave, _ in campos}
        db.contenido_guardar(cambios)
        flash("Contenido de la página actualizado.", "exito")
        return redirect(url_for("admin_contenido"))
    return render_template("admin/contenido.html", usuario=g.usuario,
                           grupos=GRUPOS_CONTENIDO, C=db.contenido_todos())


@app.route("/admin/slides", methods=["GET", "POST"])
@requiere_admin
def admin_slides():
    if request.method == "POST":
        cambios = {}
        actuales = db.contenido_todos()
        for i in (1, 2, 3):
            clave = "hero_slide%d_imagen" % i
            quitar = request.form.get("quitar_slide%d" % i) == "1"
            if quitar:
                viejo = actuales.get(clave, "")
                cambios[clave] = ""
                if viejo:
                    try:
                        os.remove(os.path.join(SLIDES_DIR, viejo))
                    except OSError:
                        pass
            archivo = request.files.get("slide%d" % i)
            if archivo and archivo.filename:
                original = os.path.basename(archivo.filename.replace("\\", "/"))
                ext = os.path.splitext(original)[1].lower()
                if ext not in EXTENSIONES_IMAGEN:
                    flash("Formato de imagen no permitido. Use JPG, PNG, WEBP o GIF.", "error")
                    return redirect(url_for("admin_slides"))
                nombre = "slide-%d%s" % (i, ext)
                ruta = os.path.join(SLIDES_DIR, nombre)
                archivo.save(ruta)
                viejo = actuales.get(clave, "")
                if viejo and viejo != nombre:
                    try:
                        os.remove(os.path.join(SLIDES_DIR, viejo))
                    except OSError:
                        pass
                cambios[clave] = nombre
        db.contenido_guardar(cambios)
        flash("Flyers de la portada actualizados.", "exito")
        return redirect(url_for("admin_slides"))
    return render_template("admin/slides.html", usuario=g.usuario,
                           C=db.contenido_todos())


# ---------------- agente comercial (motor de búsqueda de clientes)
FUENTES_AGENTE = [
    "Redes sociales", "Buscadores", "Cámara de Comercio de Bogotá",
    "Otras cámaras de comercio", "Directorios públicos", "Referido", "Manual",
]

ESTADOS_PROSPECTO = ["Nuevo", "Contactado", "En negociación", "Ganado", "Perdido"]

MARCAS_PJ = ("SAS", "S.A.S", "S.A", "LTDA", "Ltda", "Ltd", "CÍA", "CIA", "E.S.P",
             "E.U.", "FUNDACIÓN", "FUNDACION", "COOPERATIVA", "HOLDING", "GROUP", "GRUPO")

SECTORES_AGENTE = [
    ("construc", "Construcción e infraestructura", "Industrial"),
    ("inmobiliar", "Inmobiliario", "Comercial"),
    ("salud", "Salud", "De servicios"),
    ("medic", "Salud", "De servicios"),
    ("tecnolog", "Tecnología", "De tecnología"),
    ("software", "Tecnología", "De tecnología"),
    ("telecom", "Telecomunicaciones", "De tecnología"),
    ("comercio", "Comercio", "Comercial"),
    ("retail", "Comercio", "Comercial"),
    ("distribuid", "Comercio", "Comercial"),
    ("aliment", "Alimentos", "Industrial"),
    ("restaur", "Gastronomía", "Comercial"),
    ("textil", "Textil y confecciones", "Industrial"),
    ("transporte", "Transporte y logística", "De servicios"),
    ("logistic", "Transporte y logística", "De servicios"),
    ("educaci", "Educación", "Educativa"),
    ("energ", "Energía", "Industrial"),
    ("financier", "Financiero", "Financiera"),
    ("seguro", "Financiero", "Financiera"),
    ("agro", "Agroindustria", "Agroindustrial"),
    ("industria", "Industrial", "Industrial"),
    ("manufactur", "Industrial", "Industrial"),
    ("hotel", "Hotelería y turismo", "Comercial"),
    ("turism", "Hotelería y turismo", "Comercial"),
    ("servicio", "Servicios", "De servicios"),
    ("legal", "Servicios jurídicos", "De servicios"),
    ("miner", "Minero", "Industrial"),
]

SERVICIOS_PJ = [
    "Constitución y trámites societarios (SAS y otros tipos).",
    "Revisión, redacción y negociación de contratos comerciales.",
    "Asesoría laboral, reglamento interno y contratos de trabajo.",
    "Derecho societario y gobierno corporativo.",
    "Protección de datos y cumplimiento normativo.",
]

SERVICIOS_PN = [
    "Consulta inicial y análisis de tu caso.",
    "Derecho de familia: divorcios, custodia y liquidación.",
    "Derecho laboral: despidos, liquidaciones y pandemia.",
    "Derecho civil y de responsabilidad.",
    "Trámites, derechos de petición y acompañamiento en audiencias.",
]


def _detectar_sector(texto):
    t = (texto or "").lower()
    for clave, sector, _nat in SECTORES_AGENTE:
        if clave in t:
            return sector, _nat
    return "", ""


def _naturaleza_prospecto(tipo, sector, nombre):
    if tipo == "juridica":
        _, nat = _detectar_sector(sector or nombre)
        return nat or "De servicios"
    return "Persona natural"


def _clasificar_prospecto(datos):
    """Clasifica el prospecto por naturaleza (jurídica/natural), sector y prioridad."""
    nombre = (datos.get("nombre") or "").strip()
    documento = (datos.get("documento") or "").strip()
    sup = nombre.upper()
    digitos = re.sub(r"\D", "", documento)
    tipo = datos.get("tipo", "").strip().lower()
    if tipo not in ("juridica", "natural"):
        if any(m in sup for m in MARCAS_PJ) or len(digitos) >= 9:
            tipo = "juridica"
        else:
            tipo = "natural"
    sector, nat = _detectar_sector(datos.get("sector") or "")
    naturaleza = _naturaleza_prospecto(tipo, sector, nombre)
    score = 25 if tipo == "natural" else 45
    if sector:
        score += 15
    if tipo == "juridica" and len(documento) >= 9:
        score += 10
    if datos.get("correo") or datos.get("telefono"):
        score += 5
    return {"tipo": tipo, "sector": sector, "naturaleza": naturaleza,
            "score": min(score, 100)}


def _logo_data_url():
    """Logo de la página en data-URL para incrustarlo en documentos y correos."""
    for nombre in ("logo.png", "logo-original.png"):
        ruta = os.path.join(BASE_DIR, "static", "img", nombre)
        if os.path.exists(ruta):
            try:
                with open(ruta, "rb") as f:
                    ext = os.path.splitext(nombre)[1].lstrip(".") or "png"
                    return ("data:image/%s;base64,%s"
                            % (ext, base64.b64encode(f.read()).decode("ascii")))
            except OSError:
                pass
    return ""


def _propuesta_html(p):
    """Genera la propuesta de servicios en HTML (con el logo) según la naturaleza."""
    import html as h
    tipo = p["tipo"]
    nombre = (p["nombre"] or "").strip()
    sector = (p.get("sector") or "").strip()
    doc = (p.get("documento") or "").strip()
    repre = (p.get("representante_legal") or "").strip()
    domicilio = (p.get("domicilio") or "").strip()
    direccion = (p.get("direccion") or "").strip()
    correo_dest = (p.get("correo") or "").strip()
    rol = (p.get("rol") or "").strip()
    radicado = (p.get("radicado") or "").strip()
    despacho = (p.get("despacho") or "").strip()
    if tipo == "juridica":
        intro = ("Atendiendo su naturaleza de persona jurídica y su actividad en %s, "
                 "sometemos a su consideración nuestra propuesta de servicios jurídicos "
                 "integrales." % (sector or "el sector privado"))
        servicios = SERVICIOS_PJ
    else:
        intro = ("En atención a su solicitud, ponemos a su disposición nuestro equipo de "
                 "abogados para acompañarle en el siguiente portafolio de servicios.")
        servicios = SERVICIOS_PN
    if rol:
        intro += (" En su calidad de %s en un proceso ante la Rama Judicial, "
                  "podemos asesorarle y representarle judicial y extrajudicialmente."
                  % h.escape(rol.lower()))
    fecha = datetime.now().strftime("%d de %B de %Y")
    logo = _logo_data_url()
    fila = lambda etiqueta, valor: ("""
        <tr><td style="padding:4px 10px;border-bottom:1px solid #e6eef7;color:#5b6775;font-size:12px;white-space:nowrap">%s</td>
            <td style="padding:4px 10px;border-bottom:1px solid #e6eef7;color:#12263a;font-size:12px"><b>%s</b></td></tr>
        """ % (h.escape(etiqueta), h.escape(valor))) if valor else ""
    bloque_datos = "".join([
        fila("Razón social", nombre),
        fila("NIT", doc),
        fila("Representante legal", repre),
        fila("Domicilio principal", domicilio),
        fila("Dirección", direccion),
        fila("Correo de contacto", correo_dest),
        fila("Calidad en el proceso", rol),
        fila("Radicado / llave de proceso", radicado),
        fila("Despacho judicial", despacho),
    ])
    lista = "".join(
        """<tr><td style="padding:6px 2px;border-bottom:1px dashed #e6eef7;color:#12263a;font-size:13px">•
        %s</td></tr>""" % h.escape(s) for s in servicios)
    portafolio_socio = h.escape(SERVICIOS_PJ[2])
    cuerpo = """
<b>Portafolio sugerido:</b>
<table style="border-collapse:collapse;width:100%%;margin-top:6px">%s</table>

<b>Condiciones:</b>
<ul style="color:#12263a;font-size:13px;line-height:1.6;padding-left:18px;margin:8px 0">
  <li>Los honorarios se pactan según la complejidad y el tipo de servicio.</li>
  <li>Los acompañamientos se facturan sin costos ocultos y se formalizan mediante contrato electrónico.</li>
  <li>Esta propuesta tiene una vigencia de 30 días calendario.</li>
</ul>

<p style="color:#12263a;font-size:13px;line-height:1.6">Quedamos atentos a la oportunidad de atenderle y a su disposición para ampliar la información de cada servicio.</p>
<p style="color:#12263a;font-size:13px;line-height:1.6;margin-bottom:2px">Cordialmente,</p>
""" % lista
    if logo:
        arriva_logo = ('<img src="%s" alt="Derechos On" '
                       'style="height:64px;max-width:220px;object-fit:contain">' % logo)
        firma_logo = ('<img src="%s" alt="Derechos On logo" '
                      'style="height:44px;max-width:180px;object-fit:contain;margin-bottom:6px">' % logo)
    else:
        arriva_logo = ""
        firma_logo = ""
    return """<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Propuesta de servicios jurídicos — %s</title>
</head>
<body style="margin:0;padding:0;background:#eef3f9;font-family:Arial,Helvetica,sans-serif">
<div style="max-width:800px;margin:24px auto;background:#ffffff;border-radius:10px;overflow:hidden;box-shadow:0 2px 14px rgba(18,38,58,.08)">
  <div style="background:#0b3b8e;padding:18px 26px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap">
    %s
    <div style="color:#ffffff;text-align:right">
      <div style="font-size:15px;font-weight:700;letter-spacing:.4px">DERECHOS ON</div>
      <div style="font-size:11px;opacity:.85">Despacho jurídico · www.derechoson.co</div>
    </div>
  </div>
  <div style="padding:26px">
    <p style="color:#5b6775;font-size:12px;margin:0">Bogotá D.C., %s</p>
    <p style="color:#0b3b8e;font-size:20px;font-weight:700;margin:14px 0 4px">Propuesta de servicios jurídicos</p>
    <table style="border-collapse:collapse;width:100%%;margin-top:12px">%s</table>
    <p style="color:#12263a;font-size:13px;line-height:1.6;margin-top:16px">%s</p>
    %s
    <div style="border-top:1px solid #e6eef7;margin-top:26px;padding-top:16px">
      %s
      <div style="color:#12263a;font-size:14px;font-weight:700">DERECHOS ON</div>
      <div style="color:#5b6775;font-size:12px">Despacho jurídico · www.derechoson.co · Bogotá, Colombia</div>
      <div style="color:#aab4c0;font-size:11px;margin-top:8px">Esta propuesta fue generada automáticamente y tiene una vigencia de 30 días calendario.</div>
    </div>
  </div>
</div>
</body></html>""" % (
        h.escape(nombre[:60]), arriva_logo, fecha, bloque_datos,
        h.escape(intro), cuerpo, firma_logo)


@app.route("/admin/contrato", methods=["GET", "POST"])
@requiere_admin
def admin_contrato():
    if request.method == "POST":
        accion = request.form.get("accion", "").strip()

        # Subida de plantilla Word (.docx)
        if accion == "subir_plantilla":
            archivo = request.files.get("plantilla_docx")
            if not archivo or not archivo.filename:
                flash("Selecciona un archivo .docx", "error")
                return redirect(url_for("admin_contrato"))

            original = os.path.basename(archivo.filename.replace("\\", "/"))
            ext = os.path.splitext(original)[1].lower()
            if ext != ".docx":
                flash("Solo se permiten archivos .docx", "error")
                return redirect(url_for("admin_contrato"))

            # Guarda temporalmente
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
                archivo.save(tmp.name)
                tmp_path = tmp.name

            try:
                # Valida y procesa
                ok, msg = contrato_docx.validar_docx(tmp_path)
                if not ok:
                    flash(msg, "error")
                    return redirect(url_for("admin_contrato"))

                html_plantilla, variables, advertencias = contrato_docx.docx_a_plantilla(tmp_path)

                # Limpia con el saneador
                html_limpio = html_seguro.limpiar(html_plantilla)
                if not html_limpio.strip():
                    flash("El documento quedó vacío tras procesar.", "error")
                    return redirect(url_for("admin_contrato"))

                # Guarda la plantilla procesada
                db.contenido_guardar({CONTRATO_PLANTILLA_CLAVE: html_limpio})

                # Mensajes de resultado
                flash("Plantilla Word procesada y guardada correctamente.", "exito")
                if variables:
                    vars_mostrar = [v for v in variables if v in contrato_docx.VARIABLES_CONTRATO]
                    if vars_mostrar:
                        flash(f"Variables detectadas: {', '.join(vars_mostrar)}", "aviso")
                for adv in advertencias:
                    flash(adv, "aviso")

            except Exception as e:
                flash(f"Error al procesar el documento: {e}", "error")
            finally:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

            return redirect(url_for("admin_contrato"))

        # Firma autorizada (existente)
        db.contenido_guardar({
            "contrato_firmante_nombre": request.form.get("firmante_nombre", "").strip(),
            "contrato_firmante_cargo": request.form.get("firmante_cargo", "").strip(),
        })
        archivo = request.files.get("firma")
        if archivo and archivo.filename:
            original = os.path.basename(archivo.filename.replace("\\", "/"))
            ext = os.path.splitext(original)[1].lower()
            if ext not in EXTENSIONES_IMAGEN:
                flash("Formato de imagen no permitido. Use JPG, PNG, WEBP o GIF.", "error")
                return redirect(url_for("admin_contrato"))
            viejo = db.contenido_todos().get("contrato_firma_archivo", "")
            nombre = "firma-despacho" + ext
            archivo.save(os.path.join(BASE_DIR, "static", "img", nombre))
            if viejo and viejo != nombre:
                try:
                    os.remove(os.path.join(BASE_DIR, "static", "img", viejo))
                except OSError:
                    pass
            db.contenido_guardar({"contrato_firma_archivo": nombre})
        flash("Firma autorizada del despacho guardada.", "exito")
        return redirect(url_for("admin_contrato"))

    return _render_admin_contrato()


def _render_admin_contrato(plantilla=None, vista_previa=False):
    """Vista del constructor de contratos con la plantilla vigente."""
    C = db.contenido_todos()
    guardada = (C.get(CONTRATO_PLANTILLA_CLAVE) or "").strip()
    texto = plantilla if plantilla is not None else (
        guardada or _CONTRATO_PLANTILLA_POR_DEFECTO.strip())
    previo, desconocidas = _vista_previa_contrato(texto)
    total = db.consultar("SELECT COUNT(*) AS n FROM contratos")
    firmados = db.consultar(
        "SELECT COUNT(*) AS n FROM contratos "
        "WHERE firmado_el IS NOT NULL AND TRIM(firmado_el) <> '' "
        "OR (firma_nombre IS NOT NULL AND TRIM(firma_nombre) <> '') "
        "OR (firma_imagen IS NOT NULL AND TRIM(firma_imagen) <> '') "
        "OR LOWER(TRIM(COALESCE(estado,''))) = 'firmado'")
    n_total = total[0]["n"] if total else 0
    n_firmados = firmados[0]["n"] if firmados else 0
    return render_template("admin/contrato.html", usuario=g.usuario, C=C,
                           plantilla=texto, campos=CONTRATO_CAMPOS,
                           vista_previa_html=previo, es_borrador=bool(plantilla),
                           desconocido=desconocidas,
                           ia_config=ia_juridica.resumen_configuracion(),
                           total_contratos=n_total,
                           contratos_firmados=n_firmados,
                           contratos_sin_firmar=n_total - n_firmados)


@app.route("/admin/contrato/ia", methods=["POST"])
@requiere_admin
def admin_contrato_ia():
    """Apoyo de redaccion con IA sobre el contenido del contrato."""
    if not ia_juridica.configurado():
        return jsonify({"error": "La IA no esta configurada. Agrega IA_CLAVE en "
                                 "/etc/derechoson.env y reinicia el servicio."}), 503
    datos = request.get_json(silent=True) or {}
    accion = (datos.get("accion") or "chat").strip().lower()
    tema = (datos.get("tema") or "").strip()
    if accion == "redactar" and tema == "libre":
        tema = ""
    try:
        mensajes, temperatura, max_tokens = ia_juridica.preparar(
            accion,
            tema=tema,
            texto_seleccion=datos.get("texto_seleccion") or "",
            documento=datos.get("documento") or "",
            honorarios=(datos.get("honorarios") or "").strip(),
            pregunta=(datos.get("pregunta") or "").strip(),
            historial=datos.get("historial") or [])
    except ia_juridica.ErrorIA as e:
        return jsonify({"error": str(e)}), 400
    try:
        r = ia_juridica.consultar(mensajes, max_tokens=max_tokens, temperatura=temperatura)
    except ia_juridica.ErrorIA as e:
        return jsonify({"error": str(e)}), 502
    texto = r["texto"]
    return jsonify({"html": ia_juridica.a_html(texto), "texto": texto,
                    "uso": r.get("uso", {}), "modelo": r.get("modelo", "")})


@app.route("/admin/contrato/contenido", methods=["POST"])
@requiere_admin
def admin_contrato_contenido():
    """Construye el contenido del documento: vista previa, guardado y aplicación."""
    accion = request.form.get("accion") or "guardar"
    texto = request.form.get("plantilla", "").strip()
    if accion == "restaurar":
        db.contenido_guardar({CONTRATO_PLANTILLA_CLAVE: _CONTRATO_PLANTILLA_POR_DEFECTO.strip()})
        flash("Se restauró el texto original del contrato.", "exito")
        return redirect(url_for("admin_contrato"))
    if not texto:
        flash("El contenido del documento no puede quedar vacío.", "error")
        return redirect(url_for("admin_contrato"))
    if len(texto) > 200000:
        flash("El contenido es demasiado extenso (máximo 200.000 caracteres).", "error")
        return redirect(url_for("admin_contrato"))
    texto = html_seguro.limpiar(texto)
    if not texto.strip():
        flash("El contenido quedó vacío tras limpiar el formato. Revisa el documento.", "error")
        return redirect(url_for("admin_contrato"))
    _, desconocidas = _vista_previa_contrato(texto)
    if accion == "vista_previa":
        return _render_admin_contrato(plantilla=texto, vista_previa=True)
    db.contenido_guardar({CONTRATO_PLANTILLA_CLAVE: texto})
    if accion == "aplicar":
        total, saltados = _retext_contratos()
        if total:
            flash("Plantilla aplicada a %d contrato(s) sin firmar." % total, "exito")
        else:
            flash("Contenido guardado. No habia contratos sin firmar por actualizar.", "exito")
        if saltados:
            flash("%d contrato(s) ya firmado(s) no se tocaron: su texto es "
                  "definitivo y no se puede cambiar." % saltados, "aviso")
    else:
        flash("Contenido del documento guardado. Aplícalo a los contratos para actualizar a los clientes.", "exito")
    if desconocidas:
        flash("Variables sin dato: %s. Se mostrarán tal cual en el documento." % (
            ", ".join(desconocidas)), "aviso")
    return redirect(url_for("admin_contrato"))


# ---------------- agente comercial: rutas
@app.route("/admin/agente")
@requiere_admin
def admin_agente():
    tipo = request.args.get("tipo", "")
    fuente = request.args.get("fuente", "")
    estado = request.args.get("estado", "")
    q = request.args.get("q", "").strip()
    prospectos = db.prospectos_lista(tipo=tipo, fuente=fuente, estado=estado, q=q)
    stats = db.consultar(
        "SELECT tipo, COUNT(*) AS n FROM prospectos GROUP BY tipo")
    por_fuente = db.consultar(
        "SELECT fuente, COUNT(*) AS n FROM prospectos GROUP BY fuente ORDER BY n DESC")
    resumen = {
        "total": len(db.consultar("SELECT id FROM prospectos")),
        "juridicas": next((r["n"] for r in stats if r["tipo"] == "juridica"), 0),
        "naturales": next((r["n"] for r in stats if r["tipo"] == "natural"), 0),
        "nuevos": len(db.consultar("SELECT id FROM prospectos WHERE estado = 'Nuevo'")),
        "ganados": len(db.consultar("SELECT id FROM prospectos WHERE estado = 'Ganado'")),
        "con_propuesta": len(db.consultar("SELECT id FROM prospectos WHERE propuesta <> ''")),
    }
    return render_template("admin/agente.html", usuario=g.usuario,
                           prospectos=prospectos, resumen=resumen, por_fuente=por_fuente,
                           fuentes=FUENTES_AGENTE, estados=ESTADOS_PROSPECTO,
                           fi_tipo=tipo, fi_fuente=fuente, fi_estado=estado, fi_q=q)


@app.route("/admin/agente/nuevo", methods=["GET", "POST"])
@requiere_admin
def admin_agente_nuevo():
    if request.method == "POST":
        datos = {
            "nombre": request.form.get("nombre", "").strip(),
            "tipo": request.form.get("tipo", "").strip(),
            "documento": request.form.get("documento", "").strip(),
            "sector": request.form.get("sector", "").strip(),
            "fuente": request.form.get("fuente", "Manual"),
            "consulta_origen": request.form.get("consulta_origen", "").strip(),
            "correo": request.form.get("correo", "").strip(),
            "telefono": request.form.get("telefono", "").strip(),
            "sitio_web": request.form.get("sitio_web", "").strip(),
            "representante_legal": request.form.get("representante_legal", "").strip(),
            "domicilio": request.form.get("domicilio", "").strip(),
            "direccion": request.form.get("direccion", "").strip(),
        }
        if not datos["nombre"]:
            flash("El nombre del prospecto es obligatorio.", "error")
            return redirect(url_for("admin_agente_nuevo"))
        clasif = _clasificar_prospecto(datos)
        datos.update(clasif)
        datos["estado"] = "Nuevo"
        pid = db.prospecto_crear(datos)
        if request.form.get("generar_propuesta") == "1":
            p = db.prospecto_por_id(pid)
            db.prospecto_actualizar(pid, {"propuesta": _propuesta_html(p)})
        flash("Prospecto clasificado como %s (prioridad %d/100)." %
              (datos["tipo"], datos["score"]), "exito")
        return redirect(url_for("admin_agente_prospecto", pid=pid))
    return render_template("admin/prospecto.html", usuario=g.usuario, p=None,
                           fuentes=FUENTES_AGENTE, estados=ESTADOS_PROSPECTO,
                           C=db.contenido_todos())


@app.route("/admin/agente/<int:pid>", methods=["GET", "POST"])
@requiere_admin
def admin_agente_prospecto(pid):
    p = db.prospecto_por_id(pid)
    if not p:
        flash("Prospecto no encontrado.", "error")
        return redirect(url_for("admin_agente"))
    if request.method == "POST":
        accion = request.form.get("accion", "guardar")
        cambios = {
            "nombre": request.form.get("nombre", "").strip() or p["nombre"],
            "tipo": request.form.get("tipo", "").strip() or p["tipo"],
            "documento": request.form.get("documento", "").strip(),
            "sector": request.form.get("sector", "").strip(),
            "naturaleza": request.form.get("naturaleza", "").strip(),
            "fuente": request.form.get("fuente", p["fuente"]),
            "consulta_origen": request.form.get("consulta_origen", "").strip(),
            "correo": request.form.get("correo", "").strip(),
            "telefono": request.form.get("telefono", "").strip(),
            "sitio_web": request.form.get("sitio_web", "").strip(),
            "representante_legal": request.form.get("representante_legal", "").strip(),
            "domicilio": request.form.get("domicilio", "").strip(),
            "direccion": request.form.get("direccion", "").strip(),
            "estado": request.form.get("estado", p["estado"]),
        }
        if accion == "reclasificar":
            clasif = _clasificar_prospecto(cambios)
            cambios.update(clasif)
            cambios["propuesta"] = request.form.get("propuesta", p["propuesta"] or "")
            flash("Prospecto reclasificado: %s, %s (prioridad %d/100)." %
                  (clasif["tipo"], clasif["naturaleza"], clasif["score"]), "exito")
        elif accion == "proponer":
            cambios["propuesta"] = _propuesta_html({**p, **cambios})
            flash("Propuesta generada según su naturaleza, con el logo de la página.", "exito")
        elif accion == "enviar":
            cambios["propuesta"] = (request.form.get("propuesta", "").strip()
                                    or _propuesta_html({**p, **cambios}))
            db.prospecto_actualizar(pid, cambios)
            nuevo = db.prospecto_por_id(pid)
            try:
                para = _enviar_propuesta(nuevo)
                flash("Prospecto guardado y propuesta enviada a %s." % para, "exito")
            except webmail.ErrorCorreo as e:
                flash("Prospecto guardado, pero el envío falló: %s" % e, "error")
            return redirect(url_for("admin_agente_prospecto", pid=pid))
        else:
            cambios["propuesta"] = request.form.get("propuesta", p["propuesta"] or "")
            if request.form.get("generar_propuesta") == "1":
                cambios["propuesta"] = _propuesta_html({**p, **cambios})
        db.prospecto_actualizar(pid, cambios)
        return redirect(url_for("admin_agente_prospecto", pid=pid))
    return render_template("admin/prospecto.html", usuario=g.usuario, p=p,
                           fuentes=FUENTES_AGENTE, estados=ESTADOS_PROSPECTO,
                           C=db.contenido_todos())


@app.route("/admin/agente/<int:pid>/eliminar", methods=["POST"])
@requiere_admin
def admin_agente_eliminar(pid):
    db.prospecto_eliminar(pid)
    flash("Prospecto eliminado.", "exito")
    return redirect(url_for("admin_agente"))


@app.route("/admin/agente/buscar", methods=["GET", "POST"])
@requiere_admin
def admin_agente_buscar():
    if request.method == "POST":
        accion = request.form.get("accion", "buscar")
        if accion == "buscar":
            texto = request.form.get("texto", "").strip()
            fuentes = request.form.getlist("fuentes")
            if not texto:
                flash("Escribe qué quieres buscar (nombre de empresa, sector, actividad…).", "error")
                return redirect(url_for("admin_agente_buscar"))
            bid = db.busqueda_agente_crear(texto, ", ".join(fuentes) or "Sin especificar")
            flash("Búsqueda registrada. Importa los resultados encontrados con el panel inferior.", "exito")
            return redirect(url_for("admin_agente_buscar", ok=bid))
        if accion == "importar":
            crudo = request.form.get("resultados", "").strip()
            fuente = request.form.get("fuente_import", "Cámara de Comercio de Bogotá")
            consulta = request.form.get("consulta_import", "").strip()
            if not crudo:
                flash("Pega o sube los resultados a importar (una fila por linea).", "error")
                return redirect(url_for("admin_agente_buscar"))
            creados, fallidos = _importar_resultados(crudo, fuente, consulta)
            if creados:
                db.ejecutar(
                    "UPDATE busquedas_agente SET resultado = 'Importada', nro_resultados = ? "
                    "WHERE id = (SELECT id FROM busquedas_agente ORDER BY id DESC LIMIT 1)",
                    (creados,))
            flash("Importados %d prospecto(s), clasificados automáticamente (%d línea(s) ignoradas)."
                  % (creados, fallidos), "exito")
            return redirect(url_for("admin_agente"))
    return render_template("admin/agente_buscar.html", usuario=g.usuario,
                           fuentes=FUENTES_AGENTE, busquedas=db.busquedas_agente_lista())


def _importar_resultados(crudo, fuente, consulta):
    creados = 0
    fallidos = 0
    for linea in crudo.splitlines():
        linea = linea.strip()
        if not linea or linea.lower().startswith("nombre"):
            continue
        partes = [p.strip() for p in linea.replace(";", ",").split(",") if p.strip()]
        if not partes:
            continue
        nombre = partes[0]
        documento = partes[1] if len(partes) > 1 else ""
        sector = partes[2] if len(partes) > 2 else ""
        correo = partes[3] if len(partes) > 3 else ""
        telefono = partes[4] if len(partes) > 4 else ""
        datos = {"nombre": nombre, "documento": documento, "sector": sector,
                 "correo": correo, "telefono": telefono, "fuente": fuente,
                 "consulta_origen": consulta}
        clasif = _clasificar_prospecto(datos)
        datos.update(clasif)
        datos["estado"] = "Nuevo"
        pid = db.prospecto_crear(datos)
        if pid:
            creados += 1
        else:
            fallidos += 1
    return creados, fallidos


@app.route("/admin/agente/plantilla")
@requiere_admin
def admin_agente_plantilla():
    from io import StringIO
    texto = "Nombre;Documento;Sector;Correo;Telefono\n"
    texto += "Construcciones Alfa SAS;900123456;Construccion;ventas@alfa.co;+57 300 000 0001\n"
    texto += "Comercializadora Beta LTDA;901234567;Comercio;contacto@beta.com;+57 300 000 0002\n"
    buff = StringIO(texto)
    return Response("\ufeff" + buff.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition":
                             "attachment; filename=plantilla_resultados_ccb.csv"})


# ------- agente comercial: motor automático de búsqueda de empresas colombianas
# Consulta fuentes de datos abiertos (datos.gov.co) y cruza resultados por NIT.
MOTOR_DATASETS = [
    {
        "clave": "rues",
        "dataset": "c82u-588k",
        "nombre": "RUES · Personas jurídicas y naturales (datos.gov.co)",
        "nit_col": "numero_identificacion",
        "columnas": {"razon_social": "nombre", "numero_identificacion": "nit",
                     "camara_comercio": "camara", "matricula": "matricula",
                     "estado_matricula": "estado_matricula",
                     "organizacion_juridica": "organizacion",
                     "ultimo_ano_renovado": "ultimo_ano_renovado",
                     "tipo_sociedad": "tipo_sociedad",
                     "cod_ciiu_act_econ_pri": "ciiu"},
    },
    {
        "clave": "actividad",
        "dataset": "cas9-r54x",
        "nombre": "NIT y actividad económica (datos.gov.co)",
        "nit_col": "nit",
        "columnas": {"razon_social": "nombre", "nit": "nit",
                     "dir_comercial": "direccion", "email_comercial": "correo",
                     "tam_empresa": "tam_empresa", "personal": "personal",
                     "ciiu_1": "ciiu"},
    },
    {
        "clave": "ibague",
        "dataset": "gwqv-sqvs",
        "nombre": "Cámara de Comercio de Ibagué · activas (corte 2026)",
        "nit_col": "nit",
        "columnas": {"razon_social": "nombre", "nit": "nit",
                     "representante_legal": "representante_legal",
                     "representante_legal_suplente": "representante_legal_suplente",
                     "direccion_comercial": "direccion",
                     "barrio_comercial": "barrio",
                     "municipio_comercial": "municipio",
                     "email_comercial": "correo",
                     "camara_de_propietario": "camara",
                     "estado_de_la_matricula": "estado_matricula",
                     "matricula": "matricula",
                     "organizacion": "organizacion",
                     "tipo_local": "tipo_local",
                     "ultimo_a_o_renovado": "ultimo_ano_renovado",
                     "fecha_constitucion": "fecha_constitucion",
                     "actividad": "ciiu"},
        "extra_correos": ["email_comercial_2", "email_comercial_3",
                          "email_de_notificacion", "email_propietario"],
    },
]
MOTOR_URL = "https://www.datos.gov.co/resource/%s.json"
MOTOR_TIEMPO = 6
MOTOR_LIMITE = 12

# Motor de personas naturales: mismos motores, pero solo personas que ejercen
# comercio u oficios (sujetas a registro/cámara). Son clientes potenciales de la
# firma (asesoría laboral, civil, familiar, comercial, etc.).
MOTOR_PERSONAS_DATASETS = [
    {
        "clave": "rues_personas",
        "dataset": "c82u-588k",
        "nombre": "RUES · personas naturales (datos.gov.co)",
        "where": "organizacion_juridica = 'PERSONA NATURAL'",
        "nit_col": "numero_identificacion",
        "columnas": {"razon_social": "nombre", "numero_identificacion": "nit",
                     "camara_comercio": "camara", "matricula": "matricula",
                     "estado_matricula": "estado_matricula",
                     "clase_identificacion": "tipo_local",
                     "ultimo_ano_renovado": "ultimo_ano_renovado",
                     "cod_ciiu_act_econ_pri": "ciiu"},
    },
    {
        "clave": "ibague_personas",
        "dataset": "gwqv-sqvs",
        "nombre": "Cámara de Comercio de Ibagué · personas naturales (corte 2026)",
        "where": "organizacion = 'PERSONA NATURAL'",
        "nit_col": "nit",
        "columnas": {"razon_social": "nombre", "nit": "nit",
                     "direccion_comercial": "direccion",
                     "barrio_comercial": "barrio",
                     "municipio_comercial": "municipio",
                     "email_comercial": "correo",
                     "estado_de_la_matricula": "estado_matricula",
                     "matricula": "matricula",
                     "nacionalidad": "tipo_local",
                     "ultimo_a_o_renovado": "ultimo_ano_renovado",
                     "actividad": "ciiu", "ciiu_1": "ciiu"},
        "extra_correos": ["email_comercial_2", "email_comercial_3",
                          "email_de_notificacion"],
    },
]


def _motor_consultar(dataset, soql, limite=None):
    """Consulta un dataset abierto (SODA) con filtro $where. Devuelve lista de filas."""
    params = {"$where": soql}
    if limite:
        params["$limit"] = limite
    try:
        r = _requests.get(MOTOR_URL % dataset, params=params, timeout=MOTOR_TIEMPO)
        if r.status_code != 200:
            return []
        filas = r.json()
        return filas if isinstance(filas, list) else []
    except Exception:
        return []


def _motor_limpiar(valor):
    if valor is None:
        return ""
    t = str(valor).strip()
    if t.upper() in ("NO APLICA", "N/A", "NA", "SIN INFORMACION",
                     "SIN DATOS", "SIN REGISTRO", "NO REGISTRA"):
        return ""
    return t


def _sector_por_ciiu(texto):
    t = (texto or "").upper().strip()
    letra = t[:1] if t else ""
    mapa = {"A": "Agroindustria", "B": "Minero", "C": "Industrial",
            "D": "Energía", "E": "Energía", "F": "Construcción e infraestructura",
            "G": "Comercio", "H": "Transporte y logística",
            "I": "Servicios", "J": "Tecnología",
            "K": "Financiero", "L": "Inmobiliario", "M": "Servicios",
            "N": "Servicios", "O": "Servicios", "P": "Educación",
            "Q": "Salud", "R": "Servicios", "S": "Servicios"}
    return mapa.get(letra, "")


def _sector_ficha(ficha):
    ciiu = ficha.get("ciiu") or ""
    nombre = ficha.get("nombre") or ""
    sector, _ = _detectar_sector(ciiu or ficha.get("organizacion") or "")
    if not sector:
        sector = _sector_por_ciiu(ciiu)
    if not sector:
        sector, _ = _detectar_sector(nombre)
    return sector


def _motor_mapa(cfg, fila):
    """Traduce una fila del dataset abierto a la ficha canónica del motor."""
    ficha = {
        "nombre": "", "nit": "", "representante_legal": "",
        "representante_legal_suplente": "", "direccion": "", "barrio": "",
        "municipio": "", "correo": "", "camara": "", "matricula": "",
        "estado_matricula": "", "organizacion": "", "tipo_local": "",
        "ultimo_ano_renovado": "", "fecha_constitucion": "", "tam_empresa": "",
        "personal": "", "tipo_sociedad": "", "ciiu": "",
        "fuente": cfg["nombre"], "sector": "", "telefono": "", "sitio_web": "",
    }
    for origen, destino in cfg["columnas"].items():
        ficha[destino] = _motor_limpiar(fila.get(origen))
    for extra in cfg.get("extra_correos", []):
        val = _motor_limpiar(fila.get(extra))
        if val and not ficha["correo"]:
            ficha["correo"] = val
    if ficha["municipio"]:
        ficha["municipio"] = re.sub(r"^\d{2,5}\s*-\s*", "", ficha["municipio"])
    if ficha["nombre"]:
        ficha["sector"] = _sector_ficha(ficha)
    if ficha["barrio"] and ficha["barrio"] not in ficha["direccion"]:
        ficha["direccion"] = ("%s, %s" % (ficha["direccion"], ficha["barrio"])).strip(", ")
    return ficha


def _motor_termino(t):
    t = re.sub(r"[%_\"]", " ", t or "")
    t = re.sub(r"\s+", " ", t).strip().upper()
    return t


def _motor_puntaje(ficha):
    pts = 0
    if ficha.get("nit"):
        pts += 2
    if ficha.get("representante_legal"):
        pts += 3
    if ficha.get("direccion") or ficha.get("municipio"):
        pts += 2
    if ficha.get("correo"):
        pts += 3
    if ficha.get("ciiu"):
        pts += 1
    return pts


def _motor_consultar_dataset(cfg, soql, limite=None):
    """Consulta un dataset abierto incluyendo el filtro propio del dataset (p. ej. personas)."""
    if cfg.get("where"):
        soql = "(%s) AND %s" % (cfg["where"], soql)
    return _motor_consultar(cfg["dataset"], soql, limite)


def motor_buscar(termino, limite=None, datasets=None):
    """Busca empresas colombianas (o personas naturales) en datos abiertos y
    unifica las fichas por NIT/cédula. `datasets` selecciona el catálogo."""
    datasets = datasets or MOTOR_DATASETS
    t = _motor_termino(termino)
    limite = min(int(limite or MOTOR_LIMITE), 30)
    if not t:
        return []
    por_nit = {}
    for cfg in datasets:
        soql = "upper(razon_social) LIKE '%{q}%'".format(q=t.replace("'", "''"))
        for fila in _motor_consultar_dataset(cfg, soql,
                                             max(limite, 8)):
            ficha = _motor_mapa(cfg, fila)
            nit = ficha.get("nit") or ""
            if not nit:
                continue
            if nit not in por_nit:
                por_nit[nit] = ficha
            else:
                base = por_nit[nit]
                for clave, valor in ficha.items():
                    if valor and not base.get(clave):
                        base[clave] = valor
    resultados = sorted(por_nit.values(), key=_motor_puntaje, reverse=True)
    return resultados[:limite]


def motor_ficha_por_nit(nit, datasets=None):
    """Enriquece los datos de identificación de una empresa (o persona)
    consultando su NIT/cédula en el catálogo indicado."""
    nit_limpio = re.sub(r"[^0-9]", "", nit or "")
    if not nit_limpio:
        return {}
    datasets = datasets or MOTOR_DATASETS
    ficha = {}
    for cfg in datasets:
        soql = "%s = '%s'" % (cfg["nit_col"], nit_limpio)
        if cfg.get("where"):
            soql = "(%s) AND %s" % (cfg["where"], soql)
        filas = _motor_consultar(cfg["dataset"], soql, 1)
        for fila in filas:
            mapa = _motor_mapa(cfg, fila)
            for clave, valor in mapa.items():
                if valor and not ficha.get(clave):
                    ficha[clave] = valor
    return ficha


def personas_buscar(termino, limite=None, con_rama_judicial=False):
    """Motor de personas naturales que podrían requerir servicios jurídicos.
    Con `con_rama_judicial` también consulta la Rama Judicial para encontrar
    demandantes y demandados en procesos públicos."""
    fichas = motor_buscar(termino, limite=limite, datasets=MOTOR_PERSONAS_DATASETS)
    if con_rama_judicial:
        try:
            fichas += ramajudicial.buscar(
                termino, limite=min((int(limite) if limite else MOTOR_LIMITE), 12))
        except Exception:
            pass
    return fichas


def personas_ficha_por_id(id_persona):
    """Enriquece la ficha de una persona natural por su cédula/NIT."""
    return motor_ficha_por_nit(id_persona, datasets=MOTOR_PERSONAS_DATASETS)


def _importar_motor(nits, fuente, consulta, enviar=False):
    """Crea prospectos desde el motor, genera propuesta con logo y opcionalmente envía."""
    creados = enviados = sin_correo = fallidos = 0
    for nit in nits:
        ficha = motor_ficha_por_nit(nit)
        nombre = (ficha.get("nombre") or "").strip()
        if not nombre:
            fallidos += 1
            continue
        sector, _ = _detectar_sector(ficha.get("ciiu") or ficha.get("organizacion") or nombre)
        datos = {
            "nombre": nombre, "tipo": "", "documento": (ficha.get("nit") or "").strip(),
            "sector": sector, "correo": (ficha.get("correo") or "").strip(),
            "telefono": (ficha.get("telefono") or "").strip(),
            "sitio_web": (ficha.get("sitio_web") or "").strip(),
            "representante_legal": (ficha.get("representante_legal") or "").strip(),
            "domicilio": (ficha.get("municipio") or ficha.get("camara") or "").strip(),
            "direccion": (ficha.get("direccion") or "").strip(),
            "fuente": fuente, "consulta_origen": consulta,
        }
        clasif = _clasificar_prospecto(datos)
        datos.update(clasif)
        datos["estado"] = "Nuevo"
        datos["propuesta"] = _propuesta_html(datos)
        pid = db.prospecto_crear(datos)
        if not pid:
            fallidos += 1
            continue
        creados += 1
        if enviar:
            if datos.get("correo"):
                try:
                    _enviar_propuesta(datos)
                    enviados += 1
                except webmail.ErrorCorreo:
                    fallidos += 1
            else:
                sin_correo += 1
    return creados, enviados, sin_correo, fallidos


def _importar_personas(fichas, fuente, consulta, enviar=False):
    """Crea prospectos de personas naturales desde el motor de personas y
    genera la propuesta con el portafolio para persona natural. `fichas` son
    las fichas ya resueltas del motor (datos abiertos o Rama Judicial)."""
    creados = enviados = sin_correo = fallidos = 0
    for ficha in fichas:
        nombre = (ficha.get("nombre") or "").strip()
        if not nombre:
            fallidos += 1
            continue
        rol = (ficha.get("rol") or "").strip()
        sector, _ = _detectar_sector(ficha.get("ciiu")
                                     or ficha.get("organizacion") or nombre)
        datos = {
            "nombre": nombre, "tipo": "natural",
            "documento": (ficha.get("nit") or "").strip(),
            "sector": sector, "correo": (ficha.get("correo") or "").strip(),
            "telefono": (ficha.get("telefono") or "").strip(),
            "sitio_web": (ficha.get("sitio_web") or "").strip(),
            "representante_legal": nombre,
            "domicilio": (ficha.get("municipio")
                          or ficha.get("departamento")
                          or (ficha.get("camara") or "").strip()),
            "direccion": ((ficha.get("direccion") or "").strip()
                          or ficha.get("despacho") or ""),
            "fuente": fuente, "consulta_origen": consulta,
        }
        if rol:
            datos["rol"] = rol
            datos["radicado"] = (ficha.get("radicado") or "").strip()
            datos["despacho"] = (ficha.get("despacho") or "").strip()
        clasif = _clasificar_prospecto(datos)
        clasif["tipo"] = "natural"
        datos.update(clasif)
        datos["estado"] = "Nuevo"
        datos["propuesta"] = _propuesta_html(datos)
        pid = db.prospecto_crear(datos)
        if not pid:
            fallidos += 1
            continue
        creados += 1
        if enviar:
            if datos.get("correo"):
                try:
                    _enviar_propuesta(datos)
                    enviados += 1
                except webmail.ErrorCorreo:
                    fallidos += 1
            else:
                sin_correo += 1
    return creados, enviados, sin_correo, fallidos


def _enviar_propuesta(p):
    """Envía la propuesta comercial con el logo usando el correo del sitio."""
    cfg = db.notif_config_de()
    if not cfg or not cfg["activo"] or not cfg["correo"] or not cfg["clave"]:
        raise webmail.ErrorCorreo(
            "el correo del sitio no está configurado (Notificaciones).")
    para = (p.get("correo") or "").strip()
    if not para:
        raise webmail.ErrorCorreo("la persona no tiene correo electrónico registrado.")
    cuerpo = p.get("propuesta") or _propuesta_html(p)
    webmail.enviar(cfg, para,
                   "Propuesta de servicios jurídicos — Derechos On", cuerpo)
    return para


@app.route("/admin/agente/motor", methods=["GET", "POST"])
@requiere_admin
def admin_agente_motor():
    return _motor_vista(persona=False)


@app.route("/admin/agente/motor/personas", methods=["GET", "POST"])
@requiere_admin
def admin_agente_motor_personas():
    return _motor_vista(persona=True)


@app.route("/admin/agente/motor/historial/limpiar", methods=["POST"])
@requiere_admin
def admin_agente_motor_historial_limpiar():
    personas = request.form.get("tipo") == "personas"
    db.busquedas_agente_limpiar(personas)
    flash(("Historial del motor de personas limpiado."
           if personas else "Historial del motor de empresas limpiado."), "exito")
    return redirect(url_for("admin_agente_motor_personas" if personas
                            else "admin_agente_motor"))


def _busquedas_motor(persona=False):
    """Historial del motor filtrado por tipo (empresas o personas)."""
    todos = db.busquedas_agente_lista()
    if persona:
        return [b for b in todos
                if (b.get("fuentes") or "").startswith("Personas |")]
    return [b for b in todos
            if not (b.get("fuentes") or "").startswith("Personas |")]


def _motor_acciones(accion, texto, limite, fuentes, persona=False):
    """Ejecuta una acción del motor. Devuelve
    ("redirigir", url, texto, bid) o ("render", encontradas, texto, bid)."""
    destino = ("admin_agente_motor_personas" if persona
               else "admin_agente_motor")
    if accion == "buscar":
        texto = (texto or "").strip()
        if not texto:
            flash("Escribe qué quieres buscar (razón social, nombre o apellido).", "error")
            return ("redirigir", url_for(destino), "", 0)
        con_rama = persona and any("Rama Judicial" in f for f in fuentes)
        encontradas = (personas_buscar(texto, limite, con_rama_judicial=con_rama)
                       if persona
                       else motor_buscar(texto, limite))
        prefijo = "Personas | " if persona else ""
        fuentes_label = prefijo + (", ".join(fuentes) or (
            "RUES · Cámaras de comercio" if persona else "Datos abiertos Colombia"))
        bid = db.busqueda_agente_crear(texto, fuentes_label)
        resumen = ("%d personas encontradas (%s)" % (len(encontradas),
                   "datos abiertos y Rama Judicial" if con_rama
                   else "datos abiertos")
                   if persona
                   else "%d empresas encontradas en datos abiertos" % len(encontradas))
        db.ejecutar(
            "UPDATE busquedas_agente SET resultado = ?, nro_resultados = ?, detalle = ? "
            "WHERE id = ?",
            (resumen, len(encontradas),
             json.dumps(encontradas, ensure_ascii=False), bid))
        if not encontradas:
            flash("El motor no encontró resultados. Intenta con el nombre y apellido, "
                  "la actividad que ejerce o su vinculación a un proceso judicial.", "error")
        return ("render", encontradas, texto, bid)
    if accion in ("importar", "importar_enviar"):
        enviar = (accion == "importar_enviar")
        if persona:
            por_clave = {}
            bid_n = (request.form.get("bid_import", "") or "").strip()
            if bid_n.isdigit():
                reg = db.busqueda_agente_por_id(int(bid_n))
                try:
                    detalle = json.loads((reg or {}).get("detalle") or "[]") or []
                except ValueError:
                    detalle = []
                por_clave = {k.get("clave_import"): k for k in detalle
                             if k.get("rama") and k.get("clave_import")}
            fichas = []
            for idp in request.form.getlist("id_p"):
                if idp in por_clave:
                    fichas.append(por_clave[idp])
                else:
                    fichas.append(personas_ficha_por_id(idp))
            crear, enviados, sin_correo, fallo = _importar_personas(
                fichas,
                request.form.get("fuente_import", "Motor de personas · RUES"),
                request.form.get("consulta_import", "").strip(), enviar=enviar)
        else:
            crear, enviados, sin_correo, fallo = _importar_motor(
                request.form.getlist("nit"),
                request.form.get("fuente_import", "Motor automático · Datos abiertos"),
                request.form.get("consulta_import", "").strip(), enviar=enviar)
        mensaje = "Importados %d prospecto(s) desde el motor." % crear
        if enviar:
            mensaje += " Propuestas enviadas: %d. Sin correo: %d." % (enviados, sin_correo)
        if fallo:
            mensaje += " No procesados: %d." % fallo
        flash(mensaje, "exito")
        return ("redirigir", url_for("admin_agente"), "", 0)
    return ("render", [], "", 0)


def _motor_vista(persona=False):
    encontradas = []
    texto_busqueda = ""
    bid = 0
    if request.method == "POST":
        modo, a, b, c = _motor_acciones(
            request.form.get("accion", "buscar"),
            request.form.get("texto", ""),
            request.form.get("limite", MOTOR_LIMITE),
            request.form.getlist("fuentes"), persona=persona)
        if modo == "redirigir":
            return redirect(a)
        encontradas, texto_busqueda, bid = a, b, c
    else:
        try:
            bid = int(request.args.get("b", 0) or 0)
        except (TypeError, ValueError):
            pass
        if bid:
            reg = db.busqueda_agente_por_id(bid)
            if reg:
                texto_busqueda = reg["texto"]
                try:
                    encontradas = json.loads(reg.get("detalle") or "[]") or []
                except ValueError:
                    encontradas = []
    plantilla = ("admin/agente_motor_personas.html" if persona
                 else "admin/agente_motor.html")
    return render_template(plantilla, usuario=g.usuario,
                           fuentes=FUENTES_AGENTE, encontradas=encontradas,
                           texto=texto_busqueda, bid=bid,
                           busquedas=_busquedas_motor(persona))


@app.route("/admin/agente/<int:pid>/propuesta")
@requiere_admin
def admin_agente_propuesta(pid):
    p = db.prospecto_por_id(pid)
    if not p:
        abort(404)
    return Response(p.get("propuesta") or _propuesta_html(p), mimetype="text/html")


@app.route("/admin/agente/<int:pid>/enviar", methods=["POST"])
@requiere_admin
def admin_agente_enviar(pid):
    p = db.prospecto_por_id(pid)
    if not p:
        abort(404)
    try:
        para = _enviar_propuesta(p)
        flash("Propuesta de servicios enviada a %s." % para, "exito")
    except webmail.ErrorCorreo as e:
        flash("No se pudo enviar la propuesta: %s" % e, "error")
    return redirect(request.referrer or url_for("admin_agente_prospecto", pid=pid))


# ------- secciones
@app.route("/admin/secciones")
@requiere_admin
def admin_secciones():
    return render_template("admin/secciones.html", usuario=g.usuario,
                           secciones=db.secciones_todas())


@app.route("/admin/secciones/crear", methods=["POST"])
@requiere_admin
def admin_secciones_crear():
    db.ejecutar(
        "INSERT INTO secciones (titulo, subtitulo, contenido, icono, activa, posicion) VALUES (?, ?, ?, ?, ?, ?)",
        (request.form["titulo"].strip(),
         request.form.get("subtitulo", "").strip(),
         request.form.get("contenido", "").strip(),
         request.form.get("icono", "scale").strip(),
         1 if request.form.get("activa") == "1" else 0,
         int(request.form.get("posicion", 0) or 0)))
    flash("Sección agregada.", "exito")
    return redirect(url_for("admin_secciones"))


@app.route("/admin/secciones/<int:sid>/editar", methods=["POST"])
@requiere_admin
def admin_secciones_editar(sid):
    db.ejecutar(
        "UPDATE secciones SET titulo = ?, subtitulo = ?, contenido = ?, icono = ?, activa = ?, posicion = ? WHERE id = ?",
        (request.form["titulo"].strip(),
         request.form.get("subtitulo", "").strip(),
         request.form.get("contenido", "").strip(),
         request.form.get("icono", "scale").strip(),
         1 if request.form.get("activa") == "1" else 0,
         int(request.form.get("posicion", 0) or 0), sid))
    flash("Sección actualizada.", "exito")
    return redirect(url_for("admin_secciones"))


@app.route("/admin/secciones/<int:sid>/eliminar", methods=["POST"])
@requiere_admin
def admin_secciones_eliminar(sid):
    db.ejecutar("DELETE FROM secciones WHERE id = ?", (sid,))
    flash("Sección eliminada.", "exito")
    return redirect(url_for("admin_secciones"))


# ------- abogados
@app.route("/admin/abogados")
@requiere_admin
def admin_abogados():
    return render_template("admin/abogados.html", usuario=g.usuario,
                           abogados=db.abogados_lista())


@app.route("/admin/abogados/crear", methods=["POST"])
@requiere_admin
def admin_abogados_crear():
    nombre = request.form["nombre"].strip()
    correo = request.form.get("correo", "").strip()
    clave = request.form.get("clave", "")
    db.ejecutar(
        "INSERT INTO abogados (nombre, especialidad, correo, telefono, tarjeta_profesional, activo, fecha_registro) "
        "VALUES (?, ?, ?, ?, ?, 1, ?)",
        (nombre, request.form.get("especialidad", "").strip(),
         correo, request.form.get("telefono", "").strip(),
         request.form.get("tarjeta_profesional", "").strip(),
         datetime.now().strftime("%Y-%m-%d %H:%M")))
    _crear_cuenta_abogado(correo, clave, nombre)
    flash("Abogado agregado al despacho.", "exito")
    return redirect(url_for("admin_abogados"))


def _crear_cuenta_abogado(correo, clave, nombre):
    """Crea (o actualiza) el usuario del portal del abogado con rol 'abogado'."""
    if "@" not in correo:
        return
    usuario = db.usuario_por_email(correo)
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M")
    if usuario:
        if usuario["rol"] != "abogado":
            flash("El correo ya pertenece a otro tipo de usuario; no se modificó su cuenta.", "error")
            return
        if clave:
            db.ejecutar("UPDATE usuarios SET password_hash = ?, activo = 1 WHERE id = ?",
                        (generate_password_hash(clave), usuario["id"]))
        return
    if not clave:
        clave = "Abogado123!"
        flash("Portal creado. Acceso inicial: %s / %s (cámbiala por seguridad)." % (correo, clave), "aviso")
    db.ejecutar(
        "INSERT INTO usuarios (nombre, email, password_hash, rol, activo, fecha_registro) "
        "VALUES (?, ?, ?, 'abogado', 1, ?)",
        (nombre, correo, generate_password_hash(clave), ahora))


@app.route("/admin/abogados/<int:aid>/quitar", methods=["POST"])
@requiere_admin
def admin_abogados_quitar(aid):
    abogado = db.abogado_por_id(aid)
    db.ejecutar("UPDATE procesos SET abogado_id = NULL WHERE abogado_id = ?", (aid,))
    db.ejecutar("DELETE FROM abogados WHERE id = ?", (aid,))
    if abogado and abogado.get("correo"):
        db.ejecutar("UPDATE usuarios SET activo = 0 WHERE rol = 'abogado' AND LOWER(email) = LOWER(?)",
                    (abogado["correo"],))
    flash("Abogado retirado del despacho.", "exito")
    return redirect(url_for("admin_abogados"))


# ------- expedientes
@app.route("/admin/expedientes")
@requiere_admin
def admin_expedientes():
    return render_template("admin/expedientes.html", usuario=g.usuario,
                           expedientes=db.expedientes_todos(),
                           procesos=db.consultar(
                               "SELECT p.id, p.titulo, u.nombre AS cliente FROM procesos p "
                               "JOIN usuarios u ON u.id = p.cliente_id ORDER BY p.titulo"),
                           tipos=["Documento", "Memorial", "Proveído", "Auto",
                                  "Sentencia", "Oficio", "Otro"])


@app.route("/admin/expedientes/crear", methods=["POST"])
@requiere_admin
def admin_expedientes_crear():
    db.ejecutar(
        "INSERT INTO expedientes (proceso_id, tipo, titulo, descripcion, fecha) VALUES (?, ?, ?, ?, ?)",
        (int(request.form["proceso_id"]), request.form.get("tipo", "Documento"),
         request.form["titulo"].strip(), request.form.get("descripcion", "").strip(),
         request.form.get("fecha", "") or datetime.now().strftime("%Y-%m-%d")))
    flash("Expediente agregado al proceso.", "exito")
    return redirect(url_for("admin_expedientes"))


@app.route("/admin/expedientes/<int:eid>/eliminar", methods=["POST"])
@requiere_admin
def admin_expedientes_eliminar(eid):
    db.ejecutar("DELETE FROM expedientes WHERE id = ?", (eid,))
    flash("Expediente eliminado.", "exito")
    return redirect(url_for("admin_expedientes"))


# ------- procesos
@app.route("/admin/procesos")
@requiere_admin
def admin_procesos():
    procesos = db.consultar(
        "SELECT p.*, u.nombre AS cliente, u.email AS correo_cliente, a.nombre AS abogado_nombre "
        "FROM procesos p JOIN usuarios u ON u.id = p.cliente_id "
        "LEFT JOIN abogados a ON a.id = p.abogado_id "
        "ORDER BY p.fecha_actualizacion DESC")
    return render_template("admin/procesos.html", usuario=g.usuario,
                           procesos=procesos, clientes=db.consultar(
                               "SELECT id, nombre, email FROM usuarios WHERE rol = 'cliente' ORDER BY nombre"),
                           abogados=db.abogados_lista(),
                           estados=db.ESTADOS_PROCESO)


@app.route("/admin/procesos/crear", methods=["POST"])
@requiere_admin
def admin_procesos_crear():
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M")
    abogado_id = request.form.get("abogado_id")
    db.ejecutar(
        "INSERT INTO procesos (cliente_id, abogado_id, titulo, despacho, descripcion, tipo, estado, fecha_apertura, fecha_actualizacion, notas) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (int(request.form["cliente_id"]),
         int(abogado_id) if abogado_id else None,
         request.form["titulo"].strip(),
         request.form.get("despacho", "").strip(),
         request.form.get("descripcion", "").strip(), request.form.get("tipo", "").strip(),
         request.form.get("estado", "Trámite inicial"), request.form.get("fecha_apertura", "") or ahora[:10],
         ahora, request.form.get("notas", "").strip()))
    flash("Proceso creado.", "exito")
    return redirect(url_for("admin_procesos"))


@app.route("/admin/procesos/<int:pid>/editar", methods=["POST"])
@requiere_admin
def admin_procesos_editar(pid):
    abogado_id = request.form.get("abogado_id")
    db.ejecutar(
        "UPDATE procesos SET cliente_id = ?, abogado_id = ?, titulo = ?, despacho = ?, descripcion = ?, tipo = ?, estado = ?, "
        "notas = ?, fecha_actualizacion = ? WHERE id = ?",
        (int(request.form["cliente_id"]),
         int(abogado_id) if abogado_id else None,
         request.form["titulo"].strip(),
         request.form.get("despacho", "").strip(),
         request.form.get("descripcion", "").strip(), request.form.get("tipo", "").strip(),
         request.form.get("estado", "Trámite inicial"),
         request.form.get("notas", "").strip(),
         datetime.now().strftime("%Y-%m-%d %H:%M"), pid))
    flash("Proceso actualizado.", "exito")
    return redirect(url_for("admin_procesos"))


@app.route("/admin/procesos/<int:pid>/eliminar", methods=["POST"])
@requiere_admin
def admin_procesos_eliminar(pid):
    db.ejecutar("DELETE FROM procesos WHERE id = ?", (pid,))
    flash("Proceso eliminado.", "exito")
    return redirect(url_for("admin_procesos"))


# ------- actuaciones
@app.route("/admin/actuaciones")
@requiere_admin
def admin_actuaciones():
    return render_template("admin/actuaciones.html", usuario=g.usuario,
                           actuaciones=db.actuaciones_todas(),
                           documentos=db.documentos_todos(),
                           procesos=db.consultar(
                               "SELECT p.id, p.titulo, u.nombre AS cliente FROM procesos p "
                               "JOIN usuarios u ON u.id = p.cliente_id ORDER BY p.titulo"))


@app.route("/admin/actuaciones/crear", methods=["POST"])
@requiere_admin
def admin_actuaciones_crear():
    fecha_maxima = ""
    if not request.form.get("fecha_maxima_na"):
        fecha_maxima = request.form.get("fecha_maxima", "").strip()
    db.ejecutar(
        "INSERT INTO actuaciones (proceso_id, fecha, fecha_maxima, descripcion, creado_el) "
        "VALUES (?, ?, ?, ?, ?)",
        (int(request.form["proceso_id"]),
         request.form.get("fecha", "") or datetime.now().strftime("%Y-%m-%d"),
         fecha_maxima,
         request.form["descripcion"].strip(),
         datetime.now().strftime("%Y-%m-%d %H:%M")))
    db.ejecutar(
        "UPDATE procesos SET fecha_actualizacion = ? WHERE id = ?",
        (datetime.now().strftime("%Y-%m-%d %H:%M"), int(request.form["proceso_id"])))
    flash("Actuación registrada en el proceso.", "exito")
    return redirect(url_for("admin_actuaciones"))


@app.route("/admin/actuaciones/<int:aid>/editar", methods=["POST"])
@requiere_admin
def admin_actuaciones_editar(aid):
    fecha_maxima = ""
    if not request.form.get("fecha_maxima_na"):
        fecha_maxima = request.form.get("fecha_maxima", "").strip()
    db.ejecutar(
        "UPDATE actuaciones SET proceso_id = ?, fecha = ?, fecha_maxima = ?, descripcion = ? WHERE id = ?",
        (int(request.form["proceso_id"]),
         request.form.get("fecha", "") or datetime.now().strftime("%Y-%m-%d"),
         fecha_maxima,
         request.form["descripcion"].strip(), aid))
    flash("Actuación actualizada.", "exito")
    return redirect(url_for("admin_actuaciones"))


@app.route("/admin/actuaciones/<int:aid>/eliminar", methods=["POST"])
@requiere_admin
def admin_actuaciones_eliminar(aid):
    db.ejecutar("DELETE FROM actuaciones WHERE id = ?", (aid,))
    flash("Actuación eliminada.", "exito")
    return redirect(url_for("admin_actuaciones"))


# ------- documentos de actuaciones
@app.route("/admin/actuaciones/<int:aid>/documento", methods=["POST"])
@requiere_admin
def admin_actuaciones_documento(aid):
    archivo = request.files.get("archivo")
    if not archivo or not archivo.filename:
        flash("Seleccione un archivo para adjuntar.", "error")
        return redirect(url_for("admin_actuaciones"))
    original = os.path.basename(archivo.filename.replace("\\", "/"))
    ext = os.path.splitext(original)[1].lower()
    if ext not in EXTENSIONES_PERMITIDAS:
        flash("Formato no permitido. Use PDF, DOC/DOCX, JPG o PNG.", "error")
        return redirect(url_for("admin_actuaciones"))
    nombre_guardado = uuid.uuid4().hex + ext
    archivo.save(os.path.join(UPLOAD_DIR, nombre_guardado))
    tamano = os.path.getsize(os.path.join(UPLOAD_DIR, nombre_guardado))
    db.ejecutar(
        "INSERT INTO documentos (actuacion_id, nombre_original, archivo, tamano, cargado_el) VALUES (?, ?, ?, ?, ?)",
        (aid, original, nombre_guardado, tamano,
         datetime.now().strftime("%Y-%m-%d %H:%M")))
    flash("Documento adjuntado a la actuación.", "exito")
    return redirect(url_for("admin_actuaciones"))


@app.route("/admin/documentos/<int:did>/eliminar", methods=["POST"])
@requiere_admin
def admin_documentos_eliminar(did):
    doc = db.consultar("SELECT * FROM documentos WHERE id = ?", (did,))
    if doc:
        db.ejecutar("DELETE FROM documentos WHERE id = ?", (did,))
        ruta = os.path.join(UPLOAD_DIR, doc[0]["archivo"])
        for _ in range(4):
            try:
                os.remove(ruta)
                break
            except OSError:
                time.sleep(0.3)
        flash("Documento eliminado.", "exito")
    return redirect(url_for("admin_actuaciones"))


@app.route("/documento/<int:did>")
@requiere_usuario
def ver_documento(did):
    doc = db.consultar(
        "SELECT d.*, p.cliente_id FROM documentos d "
        "JOIN actuaciones a ON a.id = d.actuacion_id "
        "JOIN procesos p ON p.id = a.proceso_id "
        "WHERE d.id = ?", (did,))
    if not doc:
        abort(404)
    doc = doc[0]
    if (g.usuario["rol"] != "admin"
            and doc["cliente_id"] != g.usuario["id"]):
        abort(403)
    if (g.usuario["rol"] == "cliente" and not es_asociacion(g.usuario)
            and _cliente_en_mora(g.usuario["id"])):
        abort(403)
    ruta = os.path.join(UPLOAD_DIR, doc["archivo"])
    if not os.path.exists(ruta):
        abort(404)
    return send_from_directory(UPLOAD_DIR, doc["archivo"])


# ------- clientes
@app.route("/admin/clientes")
@requiere_admin
def admin_clientes():
    clientes = db.consultar(
        "SELECT u.*, (SELECT COUNT(*) FROM procesos p WHERE p.cliente_id = u.id) AS total_procesos "
        "FROM usuarios u WHERE u.rol = 'cliente' ORDER BY u.nombre")
    return render_template("admin/clientes.html", usuario=g.usuario, clientes=clientes)


@app.route("/admin/clientes/exportar")
@requiere_admin
def admin_clientes_exportar():
    """Exporta listado de clientes a Excel estilo Power BI: KPIs, tabla principal y pivots."""
    import openpyxl
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
    from openpyxl.utils import get_column_letter
    from io import BytesIO
    from collections import Counter

    clientes = db.consultar(
        "SELECT u.*, (SELECT COUNT(*) FROM procesos p WHERE p.cliente_id = u.id) AS total_procesos "
        "FROM usuarios u WHERE u.rol = 'cliente' ORDER BY u.nombre")

    wb = openpyxl.Workbook()

    # ============================================================
    # PALETA CORPORATIVA DERECHOS ON (estilo Power BI)
    # ============================================================
    NAVY      = '0A2D86'   # Azul corporativo principal
    NAVY_DARK = '071C52'
    NAVY_LIGHT= 'E6EEFF'   # Fondo suave para headers
    TEAL      = '01B8AA'   # Verde azulado (éxito/activo)
    AMBER     = 'F2B705'   # Amarillo (advertencia)
    RED       = 'D64550'   # Rojo (inactivo/alerta)
    WHITE     = 'FFFFFF'
    LIGHT_BG  = 'F5F9FF'   # Fondo muy suave
    GRID_LINE = 'D3DCEF'   # Líneas de grilla suaves
    TEXT_DARK = '1C2733'
    TEXT_MID  = '556279'
    TEXT_LIGHT= '8A94A6'

    # Estilos base
    def style_header(cell):
        cell.font = Font(name='Calibri', bold=True, size=11, color=WHITE)
        cell.fill = PatternFill(start_color=NAVY, end_color=NAVY, fill_type='solid')
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        cell.border = Border(
            left=Side(style='thin', color=GRID_LINE),
            right=Side(style='thin', color=GRID_LINE),
            top=Side(style='thin', color=GRID_LINE),
            bottom=Side(style='thin', color=GRID_LINE)
        )

    def style_data(cell, bold=False, color=TEXT_DARK, align='left'):
        cell.font = Font(name='Calibri', bold=bold, size=10, color=color)
        cell.alignment = Alignment(horizontal=align, vertical='center', wrap_text=True)
        cell.border = Border(
            left=Side(style='thin', color=GRID_LINE),
            right=Side(style='thin', color=GRID_LINE),
            top=Side(style='thin', color=GRID_LINE),
            bottom=Side(style='thin', color=GRID_LINE)
        )

    def style_kpi_label(cell):
        cell.font = Font(name='Calibri', size=9, color=TEXT_MID, bold=False)
        cell.alignment = Alignment(horizontal='center', vertical='bottom', wrap_text=True)

    def style_kpi_value(cell, color=NAVY):
        cell.font = Font(name='Calibri', bold=True, size=22, color=color)
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.fill = PatternFill(start_color=LIGHT_BG, end_color=LIGHT_BG, fill_type='solid')
        cell.border = Border(
            left=Side(style='thin', color=GRID_LINE),
            right=Side(style='thin', color=GRID_LINE),
            top=Side(style='thin', color=GRID_LINE),
            bottom=Side(style='thin', color=GRID_LINE)
        )

    def style_kpi_card(ws, row, col, label, value, color=NAVY):
        """Crea una tarjeta KPI estilo Power BI (label arriba, valor grande abajo)."""
        # Label
        c = ws.cell(row=row, column=col, value=label)
        style_kpi_label(c)
        # Value
        c = ws.cell(row=row+1, column=col, value=value)
        style_kpi_value(c, color)

    # ============================================================
    # HOJA 1: CLIENTES — Layout estilo Power BI
    # ============================================================
    ws = wb.active
    ws.title = "Clientes"
    ws.sheet_properties.pageSetUpPr = openpyxl.worksheet.properties.PageSetupProperties(fitToPage=True)

    # Column widths for main table
    col_widths = [6, 32, 32, 18, 18, 18, 10, 12, 10]
    for i, w in enumerate(col_widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    # Row heights for header area
    ws.row_dimensions[1].height = 26   # Title area
    ws.row_dimensions[2].height = 18   # Subtitle
    ws.row_dimensions[3].height = 18   # Date + total
    ws.row_dimensions[4].height = 6    # Separator
    ws.row_dimensions[5].height = 40   # KPI cards
    ws.row_dimensions[6].height = 6    # Separator
    ws.row_dimensions[7].height = 28   # Table header

    # ===== HEADER AREA (Rows 1-3) =====
    # Title block in A1:I3
    ws.merge_cells('A1:I1')
    ws.merge_cells('A2:I2')
    ws.merge_cells('A3:I3')
    ws['A1'] = "DERECHOS ON"
    ws['A1'].font = Font(name='Calibri', bold=True, size=22, color=NAVY)
    ws['A1'].alignment = Alignment(horizontal='left', vertical='bottom')

    ws['A2'] = "Listado de Clientes"
    ws['A2'].font = Font(name='Calibri', bold=True, size=14, color=TEXT_DARK)
    ws['A2'].alignment = Alignment(horizontal='left', vertical='top')

    ws['A3'] = f"Actualizado: {datetime.now().strftime('%d/%m/%Y %H:%M')}   |   Total clientes: {len(clientes)}"
    ws['A3'].font = Font(name='Calibri', size=10, color=TEXT_MID)
    ws['A3'].alignment = Alignment(horizontal='left', vertical='top')

    # Thin separator line row 4
    for col in range(1, 10):
        ws.cell(row=4, column=col).border = Border(bottom=Side(style='thin', color=NAVY))

    # ===== KPI CARDS ROW (Row 5) =====
    kpi_labels = ["Total Clientes", "Activos", "Inactivos", "Total Procesos", "Con Procesos"]
    kpi_values = [
        len(clientes),
        sum(1 for c in clientes if c.get("activo")),
        sum(1 for c in clientes if not c.get("activo")),
        sum(c["total_procesos"] for c in clientes),
        sum(1 for c in clientes if c["total_procesos"] > 0)
    ]
    kpi_colors = [NAVY, TEAL, RED, NAVY_DARK, AMBER]

    for i, (lbl, val, clr) in enumerate(zip(kpi_labels, kpi_values, kpi_colors), 1):
        style_kpi_card(ws, 5, i, lbl, val, clr)

    # Separator row 6
    for col in range(1, 10):
        ws.cell(row=6, column=col).border = Border(bottom=Side(style='thin', color=GRID_LINE))

    # ===== TABLE HEADER (Row 7) =====
    headers = ["ID", "Nombre", "Correo", "Documento", "Teléfono", "Ciudad", "Procesos", "Registro", "Estado"]
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=7, column=col, value=h)
        style_header(cell)
        # Set column width
        ws.column_dimensions[get_column_letter(col)].width = col_widths[col-1]

    # ===== DATA ROWS (Row 8+) =====
    for i, c in enumerate(clientes, 1):
        row = 7 + i
        data = [
            c["id"],
            c["nombre"],
            c["email"],
            c.get("documento", "") or "—",
            c.get("telefono", "") or "—",
            c.get("ciudad", "") or "—",
            c["total_procesos"],
            c["fecha_registro"][:10] if c.get("fecha_registro") else "—",
            "Activo" if c.get("activo") else "Inactivo"
        ]
        for col, val in enumerate(data, 1):
            cell = ws.cell(row=row, column=col, value=val)
            is_status = (col == 9)
            cell_color = TEAL if (is_status and val == "Activo") else (RED if (is_status and val == "Inactivo") else TEXT_DARK)
            bold = is_status
            align = 'center' if col in (1, 6, 7, 8, 9) else 'left'
            style_data(cell, bold=bold, color=cell_color, align=align)

    # Freeze panes: freeze header row and first column
    ws.freeze_panes = 'A8'

    # Auto-filter
    ws.auto_filter.ref = f"A7:{get_column_letter(len(headers))}{7 + len(clientes)}"

    # ============================================================
    # HOJA 2: RESUMEN POR CIUDAD (Pivot estilo Power BI)
    # ============================================================
    ws2 = wb.create_sheet("Resumen por Ciudad")
    # Column widths
    for i, w in enumerate([32, 16, 12, 12, 18], 1):
        ws2.column_dimensions[get_column_letter(i)].width = w

    # Compute pivot data
    ciudades = Counter(c.get("ciudad") or "Sin ciudad" for c in clientes)
    activos_por_ciudad = Counter(c.get("ciudad") or "Sin ciudad" for c in clientes if c.get("activo"))
    inactivos_por_ciudad = Counter(c.get("ciudad") or "Sin ciudad" for c in clientes if not c.get("activo"))
    procesos_por_ciudad = Counter()
    for c in clientes:
        ciudad = c.get("ciudad") or "Sin ciudad"
        procesos_por_ciudad[ciudad] += c["total_procesos"]

    all_ciudades = sorted(set(list(ciudades.keys()) + list(activos_por_ciudad.keys()) + list(inactivos_por_ciudad.keys()) + list(procesos_por_ciudad.keys())))

    # Header area (rows 1-3)
    ws2.row_dimensions[1].height = 26
    ws2.row_dimensions[2].height = 18
    ws2.row_dimensions[3].height = 18

    ws2.merge_cells('A1:E1')
    ws2['A1'] = "DERECHOS ON — Resumen de Clientes por Ciudad"
    ws2['A1'].font = Font(name='Calibri', bold=True, size=18, color=NAVY)
    ws2['A1'].alignment = Alignment(horizontal='left', vertical='bottom')

    ws2.merge_cells('A2:E2')
    ws2['A2'] = f"Actualizado: {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    ws2['A2'].font = Font(name='Calibri', size=11, color=TEXT_MID)
    ws2['A2'].alignment = Alignment(horizontal='left', vertical='top')

    ws2.merge_cells('A3:E3')
    ws2['A3'] = f"Total ciudades: {len(all_ciudades)}  |  Total clientes: {len(clientes)}"
    ws2['A3'].font = Font(name='Calibri', size=10, color=TEXT_MID)
    ws2['B3'].alignment = Alignment(horizontal='left', vertical='top')

    # KPI Cards row 5
    kpi2_labels = ["Ciudades", "Clientes", "Activos", "Inactivos", "Procesos"]
    kpi2_values = [len(all_ciudades), len(clientes), sum(activos_por_ciudad.values()), sum(inactivos_por_ciudad.values()), sum(procesos_por_ciudad.values())]
    kpi2_colors = [NAVY, TEAL, RED, AMBER, NAVY_DARK]
    for i, (lbl, val, clr) in enumerate(zip(kpi2_labels, kpi2_values, kpi2_colors), 1):
        style_kpi_card(ws2, 5, i, lbl, val, clr)

    # Pivot header row 7
    pivot_headers = ["Ciudad", "Total Clientes", "Activos", "Inactivos", "Total Procesos"]
    for col, h in enumerate(pivot_headers, 1):
        cell = ws2.cell(row=7, column=col, value=h)
        style_header(cell)

    # Data rows
    for i, ciudad in enumerate(all_ciudades, 1):
        row = 7 + i
        vals = [
            ciudad,
            ciudades.get(ciudad, 0),
            activos_por_ciudad.get(ciudad, 0),
            inactivos_por_ciudad.get(ciudad, 0),
            procesos_por_ciudad.get(ciudad, 0)
        ]
        for col, val in enumerate(vals, 1):
            cell = ws2.cell(row=row, column=col, value=val)
            bold = (col == 1)
            align = 'left' if col == 1 else 'center'
            style_data(cell, bold=bold, align=align)

    # Totals row
    total_row = 7 + len(all_ciudades)
    ws2.cell(row=total_row, column=1, value="TOTAL").font = Font(name='Calibri', bold=True, size=10, color=WHITE)
    ws2.cell(row=total_row, column=1).fill = PatternFill(start_color=NAVY, end_color=NAVY, fill_type='solid')
    ws2.cell(row=total_row, column=1).alignment = Alignment(horizontal='center', vertical='center')
    ws2.cell(row=total_row, column=1).border = Border(
        left=Side(style='thin', color=GRID_LINE), right=Side(style='thin', color=GRID_LINE),
        top=Side(style='thin', color=GRID_LINE), bottom=Side(style='thin', color=GRID_LINE)
    )
    for col in range(2, 6):
        total_val = sum([ciudades.get(c, 0), activos_por_ciudad.get(c, 0), inactivos_por_ciudad.get(c, 0), procesos_por_ciudad.get(c, 0)][col-2] for c in all_ciudades)
        # Actually compute properly:
        if col == 2: total_val = sum(ciudades.values())
        elif col == 3: total_val = sum(activos_por_ciudad.values())
        elif col == 4: total_val = sum(inactivos_por_ciudad.values())
        elif col == 5: total_val = sum(procesos_por_ciudad.values())
        cell = ws2.cell(row=total_row, column=col, value=total_val)
        cell.font = Font(name='Calibri', bold=True, size=10, color=WHITE)
        cell.fill = PatternFill(start_color=NAVY, end_color=NAVY, fill_type='solid')
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.border = Border(
            left=Side(style='thin', color=GRID_LINE), right=Side(style='thin', color=GRID_LINE),
            top=Side(style='thin', color=GRID_LINE), bottom=Side(style='thin', color=GRID_LINE)
        )

    ws2.freeze_panes = 'A8'
    ws2.auto_filter.ref = f"A7:E{7 + len(all_ciudades)}"

    # ============================================================
    # HOJA 3: RESUMEN POR ESTADO (Tarjetas KPI + Detalle)
    # ============================================================
    ws3 = wb.create_sheet("Resumen por Estado")
    for i, w in enumerate([22, 14, 80], 1):
        ws3.column_dimensions[get_column_letter(i)].width = w

    ws3.row_dimensions[1].height = 26
    ws3.row_dimensions[2].height = 18
    ws3.row_dimensions[3].height = 18

    activos = sum(1 for c in clientes if c.get("activo"))
    inactivos = sum(1 for c in clientes if not c.get("activo"))
    total_procesos = sum(c["total_procesos"] for c in clientes)

    ws3.merge_cells('A1:C1')
    ws3['A1'] = "DERECHOS ON — Resumen por Estado del Cliente"
    ws3['A1'].font = Font(name='Calibri', bold=True, size=18, color=NAVY)
    ws3['A1'].alignment = Alignment(horizontal='left', vertical='bottom')

    ws3.merge_cells('A2:C2')
    ws3['A2'] = f"Actualizado: {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    ws3['A2'].font = Font(name='Calibri', size=11, color=TEXT_MID)
    ws3['A2'].alignment = Alignment(horizontal='left', vertical='top')

    ws3.merge_cells('A3:C3')
    ws3['A3'] = f"Total clientes: {len(clientes)}  |  Procesos totales: {total_procesos}"
    ws3['A3'].font = Font(name='Calibri', size=10, color=TEXT_MID)
    ws3['A3'].alignment = Alignment(horizontal='left', vertical='top')

    # KPI Cards row 5
    kpi3_labels = ["Total", "Activos", "Inactivos"]
    kpi3_values = [len(clientes), activos, inactivos]
    kpi3_colors = [NAVY, TEAL, RED]
    for i, (lbl, val, clr) in enumerate(zip(kpi3_labels, kpi3_values, kpi3_colors), 1):
        style_kpi_card(ws3, 5, i, lbl, val, clr)

    # Detail table header row 7
    estado_headers = ["Estado", "Cantidad", "Clientes"]
    for col, h in enumerate(estado_headers, 1):
        cell = ws3.cell(row=7, column=col, value=h)
        style_header(cell)

    # Data rows
    estados_data = [
        ("Activo", activos, ", ".join(c["nombre"] for c in clientes if c.get("activo")), TEAL),
        ("Inactivo", inactivos, ", ".join(c["nombre"] for c in clientes if not c.get("activo")), RED),
    ]
    for i, (estado, cant, nombres, clr) in enumerate(estados_data, 1):
        row = 7 + i
        cell = ws3.cell(row=row, column=1, value=estado)
        cell.font = Font(name='Calibri', bold=True, size=11, color=clr)
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.border = Border(left=Side(style='thin', color=GRID_LINE), right=Side(style='thin', color=GRID_LINE),
                             top=Side(style='thin', color=GRID_LINE), bottom=Side(style='thin', color=GRID_LINE))
        cell.fill = PatternFill(start_color=LIGHT_BG, end_color=LIGHT_BG, fill_type='solid')

        cell = ws3.cell(row=row, column=2, value=cant)
        style_data(cell, bold=True, color=clr, align='center')

        cell = ws3.cell(row=row, column=3, value=nombres)
        style_data(cell, align='left')

    # Totals row
    total_row = 9
    ws3.cell(row=total_row, column=1, value="TOTAL").font = Font(name='Calibri', bold=True, size=10, color=WHITE)
    ws3.cell(row=total_row, column=1).fill = PatternFill(start_color=NAVY, end_color=NAVY, fill_type='solid')
    ws3.cell(row=total_row, column=1).alignment = Alignment(horizontal='center', vertical='center')
    ws3.cell(row=total_row, column=1).border = Border(
        left=Side(style='thin', color=GRID_LINE), right=Side(style='thin', color=GRID_LINE),
        top=Side(style='thin', color=GRID_LINE), bottom=Side(style='thin', color=GRID_LINE)
    )
    cell = ws3.cell(row=total_row, column=2, value=len(clientes))
    cell.font = Font(name='Calibri', bold=True, size=10, color=WHITE)
    cell.fill = PatternFill(start_color=NAVY, end_color=NAVY, fill_type='solid')
    cell.alignment = Alignment(horizontal='center', vertical='center')
    cell.border = Border(left=Side(style='thin', color=GRID_LINE), right=Side(style='thin', color=GRID_LINE),
                         top=Side(style='thin', color=GRID_LINE), bottom=Side(style='thin', color=GRID_LINE))
    ws3.cell(row=total_row, column=3).border = Border(
        left=Side(style='thin', color=GRID_LINE), right=Side(style='thin', color=GRID_LINE),
        top=Side(style='thin', color=GRID_LINE), bottom=Side(style='thin', color=GRID_LINE)
    )

    ws3.freeze_panes = 'A8'

    # ============================================================
    # Guardar y retornar
    # ============================================================
    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    filename = f"clientes_derechoson_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    return send_file(buffer, as_attachment=True, download_name=filename,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@app.route("/admin/clientes/<int:cid>/estado", methods=["POST"])
@requiere_admin
def admin_clientes_estado(cid):
    activo = 1 if request.form.get("activo") == "1" else 0
    db.ejecutar("UPDATE usuarios SET activo = ? WHERE id = ?", (activo, cid))
    flash("Estado del cliente actualizado.", "exito")
    return redirect(url_for("admin_clientes"))


# ------- cartera de clientes (estado por servicio)
def _estado_cartera(item):
    saldo = float(item["valor_total"] or 0) - float(item["pagado"] or 0)
    if saldo <= 0.01:
        return "Pagada"
    venc = fecha_parse(item.get("vencimiento", ""))
    if venc and venc < date.today():
        return "Vencida"
    if float(item.get("pagado", 0) or 0) <= 0:
        return "Por pagar"
    return "Al día"


@app.route("/admin/cartera")
@requiere_admin
def admin_cartera():
    cliente_id = request.args.get("cliente_id", type=int)
    filas = db.cartera_todas()
    if cliente_id:
        filas = [f for f in filas if f["cliente_id"] == cliente_id]
    registros = []
    for f in filas:
        f["saldo"] = float(f["valor_total"] or 0) - float(f["pagado"] or 0)
        f["estado"] = _estado_cartera(f)
        registros.append(f)
    total_cartera = sum(r["valor_total"] for r in registros)
    total_pagado = sum(r["pagado"] for r in registros)
    vencidas = sum(1 for r in registros if r["estado"] == "Vencida")
    extras = db.tarifario_extras()
    areas_propias = db.tarifario_areas()
    tuplas_propias = [(a["numero"], a["nombre"]) for a in areas_propias]
    catalogo, _indice = tarifas_conalbos.con_extras(extras, areas_propias)
    return render_template("admin/cartera.html", usuario=g.usuario, registros=registros,
                           clientes=db.clientes_todos(), cliente_id=cliente_id,
                           total_cartera=total_cartera, total_pagado=total_pagado,
                           total_saldo=total_cartera - total_pagado, vencidas=vencidas,
                           comprobantes=db.comprobantes_todos(),
                           tarifario=catalogo,
                           areas_tarifario=tarifas_conalbos.areas(
                               [a["nombre"] for a in areas_propias]),
                           areas_numericas=numeracion_tarifario.areas_numericas(catalogo),
                           opciones_alta=numeracion_tarifario.opciones_alta(
                               catalogo, areas_propias=tuplas_propias),
                           extras=extras,
                           areas_propias=areas_propias,
                           smmlv=tarifas_conalbos.SMMLV_VIGENTE,
                           marca=MARCA_DERECHOS_ON,
                           fuente_tarifario=tarifas_conalbos.FUENTE)


@app.route("/admin/cartera/crear", methods=["POST"])
@requiere_admin
def admin_cartera_crear():
    cliente_id = request.form.get("cliente_id")
    servicio = request.form.get("servicio", "").strip()
    if not cliente_id or not servicio:
        flash("Selecciona el cliente y nombra el servicio.", "error")
        return redirect(url_for("admin_cartera"))
    db.cartera_crear({
        "cliente_id": int(cliente_id), "servicio": servicio,
        "descripcion": request.form.get("descripcion", "").strip(),
        "valor_total": request.form.get("valor_total", "0"),
        "pagado": request.form.get("pagado", "0"),
        "vencimiento": request.form.get("vencimiento", "").strip()})
    flash("Registro de cartera agregado.", "exito")
    return redirect(url_for("admin_cartera"))


@app.route("/admin/cartera/<int:cid>/editar", methods=["POST"])
@requiere_admin
def admin_cartera_editar(cid):
    servicio = request.form.get("servicio", "").strip()
    if not servicio:
        flash("El servicio no puede quedar vacío.", "error")
        return redirect(url_for("admin_cartera"))
    db.cartera_editar(cid, {
        "servicio": servicio,
        "descripcion": request.form.get("descripcion", "").strip(),
        "valor_total": request.form.get("valor_total", "0"),
        "pagado": request.form.get("pagado", "0"),
        "vencimiento": request.form.get("vencimiento", "").strip()})
    flash("Registro de cartera actualizado.", "exito")
    return redirect(url_for("admin_cartera"))


@app.route("/admin/cartera/<int:cid>/eliminar", methods=["POST"])
@requiere_admin
def admin_cartera_eliminar(cid):
    db.cartera_eliminar(cid)
    flash("Registro de cartera eliminado.", "exito")
    return redirect(url_for("admin_cartera"))


# ------------------- tarifas Derechos On: alta manual con numeracion asistida
@app.route("/admin/cartera/tarifario/agregar", methods=["POST"])
@requiere_admin
def admin_tarifario_agregar():
    """Guarda una tarifa del despacho con la numeracion que continua en su area."""
    numero = (request.form.get("numero") or "").strip()
    servicio = (request.form.get("servicio") or "").strip()
    area_numero = (request.form.get("area_numero") or "").strip()
    valor = (request.form.get("valor") or "0").strip()
    if not servicio:
        flash("Escribe el nombre del servicio.", "error")
        return redirect(url_for("admin_cartera"))
    try:
        valor_n = float(valor.replace(".", "").replace(",", ".") if valor.count(".") > 1
                        else valor)
    except ValueError:
        valor_n = 0.0
    if valor_n <= 0:
        flash("El valor debe ser mayor que cero.", "error")
        return redirect(url_for("admin_cartera"))

    catalogo, indice = tarifas_conalbos.con_extras(db.tarifario_extras(), db.tarifario_areas())
    if not numero:
        numero = numeracion_tarifario.siguiente_numero(catalogo, area_numero or "1")
    clave = "%s %s" % (numero, servicio)
    if clave in indice or db.tarifario_extra_por_numero(numero):
        flash("Ya existe un servicio con esa numeración.", "error")
        return redirect(url_for("admin_cartera"))

    etiqueta = ""
    raiz = str(area_numero or numero).split(".")[0]
    # primero el nombre de un area propia del despacho, luego el del tarifario
    area_p = db.tarifario_area_por_numero(raiz)
    if area_p:
        etiqueta = area_p["nombre"]
    else:
        for r, lbl, _n in numeracion_tarifario.areas_numericas(catalogo):
            if r == raiz:
                etiqueta = lbl
                break
    smmlv_txt = (request.form.get("smmlv") or "").strip()
    db.tarifario_extra_crear(
        numero=numero, servicio=servicio, valor=valor_n,
        area=etiqueta or ("Tarifas " + MARCA_DERECHOS_ON),
        area_numero=raiz,
        smmlv=float(smmlv_txt) if smmlv_txt else None,
        nota=(request.form.get("nota") or "").strip(),
        fuente=(request.form.get("fuente") or "Tarifa fijada por el despacho").strip())
    flash("Servicio %s creado como Tarifa %s." % (clave, MARCA_DERECHOS_ON), "exito")
    return redirect(url_for("admin_cartera"))


@app.route("/admin/cartera/tarifario/<int:tid>/eliminar", methods=["POST"])
@requiere_admin
def admin_tarifario_eliminar(tid):
    fila = db.tarifario_extra_por_id(tid)
    db.tarifario_extra_eliminar(tid)
    if fila:
        flash("Tarifa %s %s (%s) eliminada."
              % (fila["numero"], fila["servicio"], MARCA_DERECHOS_ON), "exito")
    return redirect(url_for("admin_cartera"))


# ------------------------------------- areas del derecho propias del despacho

@app.route("/admin/cartera/area/agregar", methods=["POST"])
@requiere_admin
def admin_area_agregar():
    """
    Crea un area del derecho que no existe en CONALBOS.

    Se le asigna automaticamente la siguiente raiz numerica libre (despues de
    la 23), porque una raiz oficial 1..23 haria que sus items parecieran parte
    de la Resolucion 02/2002.
    """
    nombre = (request.form.get("nombre") or "").strip()
    if len(nombre) < 3:
        flash("El nombre del area debe tener al menos 3 caracteres.", "error")
        return redirect(url_for("admin_cartera") + "#panelAreas")
    if len(nombre) > 80:
        flash("El nombre del area es demasiado largo (maximo 80).", "error")
        return redirect(url_for("admin_cartera") + "#panelAreas")

    propias = db.tarifario_areas()
    catalogo, _indice = tarifas_conalbos.con_extras(db.tarifario_extras(), propias)
    nombres = {_normaliza(a["nombre"]) for a in propias}
    if _normaliza(nombre) in nombres or _normaliza(nombre) in {
            _normaliza(a) for a in tarifas_conalbos.areas()}:
        flash("El area &laquo;%s&raquo; ya existe en el tarifario." % nombre, "error")
        return redirect(url_for("admin_cartera") + "#panelAreas")

    raiz = numeracion_tarifario.siguiente_raiz(
        catalogo, [(a["numero"], a["nombre"]) for a in propias])
    db.tarifario_area_crear(raiz, nombre,
                            color=(request.form.get("color") or "").strip())
    flash("Area &laquo;%s&raquo; creada con la raiz %s. Sus tarifas se numeraran "
          "desde %s.1." % (nombre, raiz, raiz), "exito")
    return redirect(url_for("admin_cartera") + "#panelAreas")


@app.route("/admin/cartera/area/<int:aid>/eliminar", methods=["POST"])
@requiere_admin
def admin_area_eliminar(aid):
    """
    Elimina un area propia. Se rechaza si ya tiene tarifas: borrarla dejaria
    esos servicios sin grupo visible en la tabla.
    """
    area = db.tarifario_area_por_id(aid)
    if not area:
        flash("El area ya no existe.", "error")
        return redirect(url_for("admin_cartera") + "#panelAreas")
    raiz = str(area["numero"]).strip()
    en_uso = [e for e in db.tarifario_extras()
              if str(e.get("area_numero") or "").strip() == raiz
              or str(e.get("area") or "").strip() == area["nombre"]]
    if en_uso:
        flash("No se puede eliminar &laquo;%s&raquo;: tiene %d tarifa(s) "
              "asignada(s). Elimina o reasigna esas tarifas primero."
              % (area["nombre"], len(en_uso)), "error")
        return redirect(url_for("admin_cartera") + "#panelAreas")
    db.tarifario_area_eliminar(aid)
    flash("Area &laquo;%s&raquo; eliminada." % area["nombre"], "exito")
    return redirect(url_for("admin_cartera") + "#panelAreas")


TIPOS_FORMA_PAGO = [
    ("bancaria", "Transferencia / consignación bancaria"),
    ("movil", "Billetera móvil (Nequi / Daviplata)"),
    ("efectivo", "Efectivo en caja"),
    ("online", "Pago en línea / pasarela"),
    ("otro", "Otro medio"),
]


def _icono_forma_pago(tipo):
    return {
        "bancaria": "bank",
        "movil": "phone",
        "efectivo": "cash",
        "online": "globe",
        "otro": "credit",
    }.get(tipo, "credit")


@app.route("/admin/formas-pago")
@requiere_admin
def admin_formas_pago():
    return render_template("admin/formas_pago.html", usuario=g.usuario,
                           formas=db.formas_pago_lista(), tipos=TIPOS_FORMA_PAGO)


@app.route("/admin/formas-pago/crear", methods=["POST"])
@requiere_admin
def admin_formas_pago_crear():
    nombre = request.form.get("nombre", "").strip()
    if not nombre:
        flash("El nombre de la forma de pago es obligatorio.", "error")
        return redirect(url_for("admin_formas_pago"))
    db.forma_pago_crear({
        "nombre": nombre,
        "tipo": request.form.get("tipo", "bancaria"),
        "beneficiario": request.form.get("beneficiario", "").strip(),
        "datos": request.form.get("datos", "").strip(),
        "instrucciones": request.form.get("instrucciones", "").strip(),
        "orden": request.form.get("orden", "0"),
        "activa": request.form.get("activa", "0") == "1"})
    flash("Forma de pago creada. Aparecerá en el portal de clientes.", "exito")
    return redirect(url_for("admin_formas_pago"))


@app.route("/admin/formas-pago/<int:fid>/editar", methods=["POST"])
@requiere_admin
def admin_formas_pago_editar(fid):
    if not db.forma_pago_por_id(fid):
        abort(404)
    db.forma_pago_actualizar(fid, {
        "nombre": request.form.get("nombre", "").strip(),
        "tipo": request.form.get("tipo", "bancaria"),
        "beneficiario": request.form.get("beneficiario", "").strip(),
        "datos": request.form.get("datos", "").strip(),
        "instrucciones": request.form.get("instrucciones", "").strip(),
        "orden": request.form.get("orden", "0"),
        "activa": request.form.get("activa", "0") == "1"})
    flash("Forma de pago actualizada.", "exito")
    return redirect(url_for("admin_formas_pago"))


@app.route("/admin/formas-pago/<int:fid>/estado", methods=["POST"])
@requiere_admin
def admin_formas_pago_estado(fid):
    fp = db.forma_pago_por_id(fid)
    if not fp:
        abort(404)
    db.forma_pago_actualizar(fid, {"activa": 0 if fp["activa"] else 1})
    flash("Forma de pago " + ("desactivada" if fp["activa"] else "activada") + ".", "exito")
    return redirect(url_for("admin_formas_pago"))


@app.route("/admin/formas-pago/<int:fid>/eliminar", methods=["POST"])
@requiere_admin
def admin_formas_pago_eliminar(fid):
    db.forma_pago_eliminar(fid)
    flash("Forma de pago eliminada.", "exito")
    return redirect(url_for("admin_formas_pago"))


# ------- mi cuenta (seguridad)
@app.route("/admin/cuenta", methods=["GET", "POST"])
@requiere_admin
def admin_cuenta():
    if request.method == "POST":
        actual = request.form.get("actual", "")
        nuevo = request.form.get("nuevo", "")
        repetir = request.form.get("repetir", "")
        if not check_password_hash(g.usuario["password_hash"], actual):
            flash("La contraseña actual no es correcta.", "error")
        elif len(nuevo) < 6:
            flash("La nueva contraseña debe tener al menos 6 caracteres.", "error")
        elif nuevo != repetir:
            flash("La nueva contraseña no coincide con su repetición.", "error")
        else:
            db.ejecutar("UPDATE usuarios SET password_hash = ? WHERE id = ?",
                        (generate_password_hash(nuevo), g.usuario["id"]))
            flash("Contraseña actualizada. Úsala en el próximo ingreso.", "exito")
        return redirect(url_for("admin_cuenta"))
    return render_template("admin/cuenta.html", usuario=g.usuario)


# ------- notificaciones por correo
@app.route("/admin/notificaciones", methods=["GET", "POST"])
@requiere_admin
def admin_notificaciones():
    if request.method == "POST":
        datos = {
            "servidor_smtp": request.form.get("servidor_smtp", "").strip() or "smtp.hostinger.com",
            "puerto_smtp": _puerto_int(request.form.get("puerto_smtp"), 465),
            "correo": request.form.get("correo", "").strip(),
            "clave": request.form.get("clave", "").strip(),
            "destino": request.form.get("destino", "").strip(),
            "activo": request.form.get("activo", ""),
        }
        db.notif_config_guardar(datos)
        if request.form.get("accion") == "prueba" and datos["correo"] and datos["destino"]:
            try:
                webmail.enviar(datos, datos["destino"], "Prueba de notificación Derechos On",
                               "Este es un correo de prueba. Si lo recibes, las notificaciones del sitio están listas.")
                flash("Correo de prueba enviado a %s." % datos["destino"], "exito")
            except webmail.ErrorCorreo as e:
                flash("Prueba fallida: %s" % e, "error")
        else:
            flash("Configuración de notificaciones guardada.", "exito")
        return redirect(url_for("admin_notificaciones"))
    return render_template("admin/notificaciones.html", usuario=g.usuario,
                           cfg=db.notif_config_de())


# ------- mensajes de contacto
@app.route("/admin/contactos")
@requiere_admin
def admin_contactos():
    return render_template("admin/contactos.html", usuario=g.usuario,
                           contactos=db.contactos_todos())


@app.route("/admin/contactos/<int:cid>/estado", methods=["POST"])
@requiere_admin
def admin_contactos_estado(cid):
    db.contacto_estado(cid, request.form.get("leido") == "1")
    flash("Mensaje actualizado.", "exito")
    return redirect(url_for("admin_contactos"))


@app.route("/admin/contactos/<int:cid>/eliminar", methods=["POST"])
@requiere_admin
def admin_contactos_eliminar(cid):
    db.contacto_eliminar(cid)
    flash("Mensaje eliminado.", "exito")
    return redirect(url_for("admin_contactos"))


# ------- citas
@app.route("/admin/citas")
@requiere_admin
def admin_citas():
    return render_template("admin/citas.html", usuario=g.usuario,
                           citas=db.citas_todas())


@app.route("/admin/citas/<int:cid>/estado", methods=["POST"])
@requiere_admin
def admin_citas_estado(cid):
    estado = request.form.get("estado", "Pendiente")
    if estado in ("Pendiente", "Confirmada", "Cancelada"):
        db.cita_estado(cid, estado)
        flash("Cita actualizada.", "exito")
    return redirect(url_for("admin_citas"))


@app.route("/admin/citas/<int:cid>/eliminar", methods=["POST"])
@requiere_admin
def admin_citas_eliminar(cid):
    db.cita_eliminar(cid)
    flash("Cita eliminada.", "exito")
    return redirect(url_for("admin_citas"))


# ------- testimonios
@app.route("/admin/testimonios")
@requiere_admin
def admin_testimonios():
    return render_template("admin/testimonios.html", usuario=g.usuario,
                           testimonios=db.testimonios_todos())


@app.route("/admin/testimonios/crear", methods=["POST"])
@requiere_admin
def admin_testimonios_crear():
    db.testimonio_crear(request.form)
    flash("Testimonio agregado.", "exito")
    return redirect(url_for("admin_testimonios"))


@app.route("/admin/testimonios/<int:tid>/editar", methods=["POST"])
@requiere_admin
def admin_testimonios_editar(tid):
    db.testimonio_editar(tid, request.form)
    flash("Testimonio actualizado.", "exito")
    return redirect(url_for("admin_testimonios"))


@app.route("/admin/testimonios/<int:tid>/eliminar", methods=["POST"])
@requiere_admin
def admin_testimonios_eliminar(tid):
    db.testimonio_eliminar(tid)
    flash("Testimonio eliminado.", "exito")
    return redirect(url_for("admin_testimonios"))


@app.route("/admin/testimonios/<int:tid>/publicar", methods=["POST"])
@requiere_admin
def admin_testimonios_publicar(tid):
    db.testimonio_publicar(tid)
    flash("Testimonio publicado en la portada del sitio.", "exito")
    return redirect(url_for("admin_testimonios"))


@app.route("/admin/testimonios/<int:tid>/ocultar", methods=["POST"])
@requiere_admin
def admin_testimonios_ocultar(tid):
    db.testimonio_ocultar(tid)
    flash("Testimonio ocultado de la portada del sitio.", "exito")
    return redirect(url_for("admin_testimonios"))


# ------- reportes
def _respuesta_csv(nombre, encabezados, filas):
    buf = StringIO()
    buf.write("\ufeff")
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(encabezados)
    w.writerows(filas)
    return Response(buf.getvalue().encode("utf-8"),
                    mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition":
                             "attachment; filename=%s.csv" % nombre})


@app.route("/admin/reportes")
@requiere_admin
def admin_reportes():
    por_abogado = db.consultar(
        "SELECT a.nombre, COUNT(p.id) AS total, "
        "SUM(CASE WHEN p.estado = 'Resuelto a favor' THEN 1 ELSE 0 END) AS favor "
        "FROM abogados a LEFT JOIN procesos p ON p.abogado_id = a.id "
        "GROUP BY a.id ORDER BY total DESC")
    por_estado = db.consultar(
        "SELECT estado, COUNT(*) AS total FROM procesos "
        "GROUP BY estado ORDER BY total DESC")
    por_tipo = db.consultar(
        "SELECT tipo, COUNT(*) AS total FROM procesos "
        "GROUP BY tipo ORDER BY total DESC")
    totales = {
        "clientes": db.consultar("SELECT COUNT(*) AS n FROM usuarios WHERE rol='cliente'")[0]["n"],
        "procesos": db.consultar("SELECT COUNT(*) AS n FROM procesos")[0]["n"],
        "actuaciones": db.consultar("SELECT COUNT(*) AS n FROM actuaciones")[0]["n"],
        "documentos": db.consultar("SELECT COUNT(*) AS n FROM documentos")[0]["n"],
        "expedientes": db.consultar("SELECT COUNT(*) AS n FROM expedientes")[0]["n"],
        "abogados": db.consultar("SELECT COUNT(*) AS n FROM abogados WHERE activo = 1")[0]["n"],
        "citas_pendientes": db.consultar("SELECT COUNT(*) AS n FROM citas WHERE estado='Pendiente'")[0]["n"],
        "citas_confirmadas": db.consultar("SELECT COUNT(*) AS n FROM citas WHERE estado='Confirmada'")[0]["n"],
        "contactos_no_leidos": db.consultar("SELECT COUNT(*) AS n FROM contactos WHERE leido = 0")[0]["n"],
    }
    return render_template("admin/reportes.html", usuario=g.usuario,
                           por_abogado=por_abogado, por_estado=por_estado,
                           por_tipo=por_tipo, totales=totales)


@app.route("/admin/reportes/exportar")
@requiere_admin
def admin_reportes_exportar():
    """Exporta a Excel (.xlsx) con estilo Power BI corporativo."""
    import openpyxl
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
    from openpyxl.utils import get_column_letter
    from io import BytesIO
    from datetime import datetime
    from collections import Counter

    tipo = request.args.get("tipo", "procesos")

    # ============================================================
    # PALETA Y ESTILOS CORPORATIVOS (compartidos)
    # ============================================================
    NAVY      = '0A2D86'
    NAVY_DARK = '071C52'
    NAVY_LIGHT= 'E6EEFF'
    TEAL      = '01B8AA'
    AMBER     = 'F2B705'
    RED       = 'D64550'
    WHITE     = 'FFFFFF'
    LIGHT_BG  = 'F5F9FF'
    GRID_LINE = 'D3DCEF'
    TEXT_DARK = '1C2733'
    TEXT_MID  = '556279'
    TEXT_LIGHT= '8A94A6'

    def style_header(cell):
        cell.font = Font(name='Calibri', bold=True, size=11, color=WHITE)
        cell.fill = PatternFill(start_color=NAVY, end_color=NAVY, fill_type='solid')
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        cell.border = Border(
            left=Side(style='thin', color=GRID_LINE),
            right=Side(style='thin', color=GRID_LINE),
            top=Side(style='thin', color=GRID_LINE),
            bottom=Side(style='thin', color=GRID_LINE)
        )

    def style_data(cell, bold=False, color=TEXT_DARK, align='left'):
        cell.font = Font(name='Calibri', bold=bold, size=10, color=color)
        cell.alignment = Alignment(horizontal=align, vertical='center', wrap_text=True)
        cell.border = Border(
            left=Side(style='thin', color=GRID_LINE),
            right=Side(style='thin', color=GRID_LINE),
            top=Side(style='thin', color=GRID_LINE),
            bottom=Side(style='thin', color=GRID_LINE)
        )

    def style_kpi_label(cell):
        cell.font = Font(name='Calibri', size=9, color=TEXT_MID, bold=False)
        cell.alignment = Alignment(horizontal='center', vertical='bottom', wrap_text=True)

    def style_kpi_value(cell, color=NAVY):
        cell.font = Font(name='Calibri', bold=True, size=22, color=color)
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.fill = PatternFill(start_color=LIGHT_BG, end_color=LIGHT_BG, fill_type='solid')
        cell.border = Border(
            left=Side(style='thin', color=GRID_LINE),
            right=Side(style='thin', color=GRID_LINE),
            top=Side(style='thin', color=GRID_LINE),
            bottom=Side(style='thin', color=GRID_LINE)
        )

    def style_kpi_card(ws, row, col, label, value, color=NAVY):
        c = ws.cell(row=row, column=col, value=label)
        style_kpi_label(c)
        c = ws.cell(row=row+1, column=col, value=value)
        style_kpi_value(c, color)

    def header_block(ws, title, subtitle, max_col):
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max_col)
        ws['A1'] = "DERECHOS ON"
        ws['A1'].font = Font(name='Calibri', bold=True, size=22, color=NAVY)
        ws['A1'].alignment = Alignment(horizontal='left', vertical='bottom')
        ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=max_col)
        ws['A2'] = title
        ws['A2'].font = Font(name='Calibri', bold=True, size=14, color=TEXT_DARK)
        ws['A2'].alignment = Alignment(horizontal='left', vertical='top')
        ws.merge_cells(start_row=3, start_column=1, end_row=3, end_column=max_col)
        ws['A3'] = f"Actualizado: {datetime.now().strftime('%d/%m/%Y %H:%M')}   |   {subtitle}"
        ws['A3'].font = Font(name='Calibri', size=10, color=TEXT_MID)
        ws['A3'].alignment = Alignment(horizontal='left', vertical='top')
        for c in range(1, max_col+1):
            ws.cell(row=4, column=c).border = Border(bottom=Side(style='thin', color=NAVY))

    def write_table(ws, headers, rows, start_row=7, status_col=None, status_colors=None, col_widths=None):
        """Escribe encabezados y filas de datos con estilos corporativos."""
        for col, h in enumerate(headers, 1):
            cell = ws.cell(row=start_row, column=col, value=h)
            style_header(cell)
        if col_widths:
            for i, w in enumerate(col_widths, 1):
                ws.column_dimensions[get_column_letter(i)].width = w
        for i, row_data in enumerate(rows, 1):
            r = start_row + i
            for col, val in enumerate(row_data, 1):
                cell = ws.cell(row=r, column=col, value=val)
                is_status = (status_col and col == status_col)
                clr = TEXT_DARK
                bold = False
                aln = 'left'
                if is_status:
                    bold = True
                    aln = 'center'
                    clr = status_colors.get(val, TEXT_DARK) if status_colors else TEXT_DARK
                elif col == 1:
                    aln = 'center'
                style_data(cell, bold=bold, color=clr, align=aln)
        ws.freeze_panes = get_column_letter(1) + str(start_row + 1)
        ws.auto_filter.ref = f"{get_column_letter(1)}{start_row}:{get_column_letter(len(headers))}{start_row + len(rows)}"
        return start_row + len(rows)

    wb = openpyxl.Workbook()

    # ============================================================
    # TIPO: PROCESOS
    # ============================================================
    if tipo == "procesos":
        filas = db.consultar(
            "SELECT p.*, u.nombre AS cliente, u.email AS correo_cliente, a.nombre AS abogado "
            "FROM procesos p JOIN usuarios u ON u.id = p.cliente_id "
            "LEFT JOIN abogados a ON a.id = p.abogado_id "
            "ORDER BY p.fecha_actualizacion DESC")

        ws = wb.active
        ws.title = "Procesos"
        header_block(ws, "Listado de Procesos", f"Total: {len(filas)} procesos", 10)

        # KPIs
        estados = Counter(r["estado"] for r in filas)
        tipos = Counter(r["tipo"] for r in filas)
        kpi_labels = ["Total", "En trámite", "Resueltos", "Archivados", "Tipos"]
        kpi_values = [len(filas), sum(1 for r in filas if r["estado"] == "En trámite"),
                      sum(1 for r in filas if "Resuelto" in r["estado"]),
                      sum(1 for r in filas if r["estado"] == "Archivado"), len(tipos)]
        kpi_colors = [NAVY, TEAL, RED, TEXT_MID, AMBER]
        for i, (lbl, val, clr) in enumerate(zip(kpi_labels, kpi_values, kpi_colors), 1):
            style_kpi_card(ws, 5, i, lbl, val, clr)
        for c in range(1, 11):
            ws.cell(row=6, column=c).border = Border(bottom=Side(style='thin', color=GRID_LINE))

        headers = ["ID", "Proceso", "Cliente", "Correo", "Abogado", "Tipo", "Estado", "Despacho", "Apertura", "Actualización"]
        rows = [[r["id"], r["titulo"], r["cliente"], r["correo_cliente"],
                 r["abogado"] or "", r["tipo"], r["estado"], r["despacho"],
                 r["fecha_apertura"], r["fecha_actualizacion"]] for r in filas]
        status_colors = {"En trámite": TEAL, "Resuelto a favor": TEAL, "Resuelto en contra": RED,
                         "Archivado": TEXT_MID, "En estudio": AMBER}
        write_table(ws, headers, rows, status_col=7, status_colors=status_colors,
                    col_widths=[6, 36, 28, 28, 20, 18, 16, 22, 14, 14])

        # Hoja 2: Resumen por estado
        ws2 = wb.create_sheet("Por Estado")
        header_block(ws2, "Procesos agrupados por Estado", f"{len(estados)} estados distintos", 3)
        headers2 = ["Estado", "Cantidad", "%"]
        rows2 = [[e, c, f"{c/len(filas)*100:.1f}%"] for e, c in estados.most_common()]
        write_table(ws2, headers2, rows2, start_row=7, status_col=1, status_colors={})
        total_row = 7 + len(rows2)
        ws2.cell(row=total_row, column=1, value="TOTAL")
        ws2.cell(row=total_row, column=2, value=len(filas))
        ws2.cell(row=total_row, column=3, value="100%")
        for col in range(1, 4):
            cell = ws2.cell(row=total_row, column=col)
            cell.font = Font(name='Calibri', bold=True, size=10, color=WHITE)
            cell.fill = PatternFill(start_color=NAVY, end_color=NAVY, fill_type='solid')
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border = Border(left=Side(style='thin', color=GRID_LINE),
                                 right=Side(style='thin', color=GRID_LINE),
                                 top=Side(style='thin', color=GRID_LINE),
                                 bottom=Side(style='thin', color=GRID_LINE))

    # ============================================================
    # TIPO: ACTUACIONES
    # ============================================================
    elif tipo == "actuaciones":
        filas = db.actuaciones_todas()
        ws = wb.active
        ws.title = "Actuaciones"
        header_block(ws, "Historial de Actuaciones", f"Total: {len(filas)} actuaciones", 6)

        kpi_labels = ["Total", "Con fecha máxima", "Sin fecha máxima", "Procesos distintos"]
        proc_ids = set(r["proceso_id"] for r in filas if r.get("proceso_id"))
        kpi_values = [len(filas), sum(1 for r in filas if r.get("fecha_maxima")),
                      sum(1 for r in filas if not r.get("fecha_maxima")), len(proc_ids)]
        kpi_colors = [NAVY, TEAL, RED, AMBER]
        for i, (lbl, val, clr) in enumerate(zip(kpi_labels, kpi_values, kpi_colors), 1):
            style_kpi_card(ws, 5, i, lbl, val, clr)
        for c in range(1, 7):
            ws.cell(row=6, column=c).border = Border(bottom=Side(style='thin', color=GRID_LINE))

        headers = ["ID", "Proceso", "Cliente", "Fecha", "Fecha máxima", "Descripción"]
        rows = [[r["id"], r["proceso"], r["cliente"], r["fecha"],
                 r["fecha_maxima"] or "", r["descripcion"]] for r in filas]
        write_table(ws, headers, rows, start_row=7, col_widths=[6, 30, 28, 14, 14, 50])

    # ============================================================
    # TIPO: CLIENTES
    # ============================================================
    elif tipo == "clientes":
        # Reutiliza la exportación detallada existente (admin_clientes_exportar)
        from openpyxl import Workbook
        return admin_clientes_exportar()

    # ============================================================
    # TIPO: CITAS
    # ============================================================
    elif tipo == "citas":
        filas = db.citas_todas()
        ws = wb.active
        ws.title = "Citas"
        header_block(ws, "Listado de Citas", f"Total: {len(filas)} citas", 8)

        estados = Counter(r["estado"] for r in filas)
        kpi_labels = ["Total", "Pendientes", "Confirmadas", "Canceladas", "Realizadas"]
        kpi_values = [len(filas), estados.get("Pendiente", 0), estados.get("Confirmada", 0),
                      estados.get("Cancelada", 0), estados.get("Realizada", 0)]
        kpi_colors = [NAVY, AMBER, TEAL, RED, NAVY_DARK]
        for i, (lbl, val, clr) in enumerate(zip(kpi_labels, kpi_values, kpi_colors), 1):
            style_kpi_card(ws, 5, i, lbl, val, clr)
        for c in range(1, 9):
            ws.cell(row=6, column=c).border = Border(bottom=Side(style='thin', color=GRID_LINE))

        headers = ["Fecha", "Hora", "Nombre", "Correo", "Teléfono", "Abogado", "Motivo", "Estado"]
        rows = [[r["fecha"], r["hora"], r["nombre"], r["correo"],
                 r["telefono"] or "", r["abogado_nombre"] or "",
                 r["motivo"] or "", r["estado"]] for r in filas]
        status_colors = {"Pendiente": AMBER, "Confirmada": TEAL, "Cancelada": RED, "Realizada": NAVY}
        write_table(ws, headers, rows, start_row=7, status_col=8, status_colors=status_colors,
                    col_widths=[14, 10, 22, 28, 18, 20, 30, 14])

        # Hoja 2: Por estado
        ws2 = wb.create_sheet("Por Estado")
        header_block(ws2, "Citas agrupadas por Estado", f"{len(estados)} estados", 3)
        headers2 = ["Estado", "Cantidad", "%"]
        rows2 = [[e, c, f"{c/len(filas)*100:.1f}%"] for e, c in estados.most_common()]
        write_table(ws2, headers2, rows2, start_row=7)
        tr = 7 + len(rows2)
        for col in range(1, 4):
            cell = ws2.cell(row=tr, column=col, value=["TOTAL", len(filas), "100%"][col-1] if col < 3 else "100%")
            cell.font = Font(name='Calibri', bold=True, size=10, color=WHITE)
            cell.fill = PatternFill(start_color=NAVY, end_color=NAVY, fill_type='solid')
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border = Border(left=Side(style='thin', color=GRID_LINE),
                                 right=Side(style='thin', color=GRID_LINE),
                                 top=Side(style='thin', color=GRID_LINE),
                                 bottom=Side(style='thin', color=GRID_LINE))

    # ============================================================
    # TIPO: CONTACTOS
    # ============================================================
    elif tipo == "contactos":
        filas = db.contactos_todos()
        ws = wb.active
        ws.title = "Contactos"
        header_block(ws, "Mensajes de Contacto", f"Total: {len(filas)} mensajes", 7)

        leidos = Counter("Sí" if r["leido"] else "No" for r in filas)
        kpi_labels = ["Total", "Leídos", "Sin leer"]
        kpi_values = [len(filas), leidos.get("Sí", 0), leidos.get("No", 0)]
        kpi_colors = [NAVY, TEAL, RED]
        for i, (lbl, val, clr) in enumerate(zip(kpi_labels, kpi_values, kpi_colors), 1):
            style_kpi_card(ws, 5, i, lbl, val, clr)
        for c in range(1, 8):
            ws.cell(row=6, column=c).border = Border(bottom=Side(style='thin', color=GRID_LINE))

        headers = ["Fecha", "Nombre", "Correo", "Teléfono", "Asunto", "Leído", "Mensaje"]
        rows = [[r["creado_el"], r["nombre"], r["correo"], r["telefono"] or "",
                 r["asunto"] or "", "Sí" if r["leido"] else "No", r["mensaje"]] for r in filas]
        status_colors = {"Sí": TEAL, "No": RED}
        write_table(ws, headers, rows, start_row=7, status_col=6, status_colors=status_colors,
                    col_widths=[18, 22, 28, 18, 22, 10, 50])

        # Hoja 2: Por leído
        ws2 = wb.create_sheet("Por Estado")
        header_block(ws2, "Contactos agrupados por Leído", f"2 estados", 3)
        headers2 = ["Estado", "Cantidad", "%"]
        rows2 = [[e, c, f"{c/len(filas)*100:.1f}%"] for e, c in leidos.most_common()]
        write_table(ws2, headers2, rows2, start_row=7)
        tr = 7 + len(rows2)
        for col in range(1, 4):
            cell = ws2.cell(row=tr, column=col, value=["TOTAL", len(filas), "100%"][col-1] if col < 3 else "100%")
            cell.font = Font(name='Calibri', bold=True, size=10, color=WHITE)
            cell.fill = PatternFill(start_color=NAVY, end_color=NAVY, fill_type='solid')
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border = Border(left=Side(style='thin', color=GRID_LINE),
                                 right=Side(style='thin', color=GRID_LINE),
                                 top=Side(style='thin', color=GRID_LINE),
                                 bottom=Side(style='thin', color=GRID_LINE))

    else:
        abort(404)

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return Response(buffer.getvalue(),
                    mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename=reporte-{tipo}.xlsx"})


# ---------------- PDF del reporte operativo
@app.route("/admin/reportes/pdf")
@requiere_admin
def admin_reportes_pdf():
    from io import BytesIO
    from datetime import datetime
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle, Paragraph,
                                    Spacer)
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

    # Recopila los mismos datos que la vista HTML
    por_abogado = db.consultar(
        "SELECT a.nombre, COUNT(p.id) AS total, "
        "SUM(CASE WHEN p.estado = 'Resuelto a favor' THEN 1 ELSE 0 END) AS favor "
        "FROM abogados a LEFT JOIN procesos p ON p.abogado_id = a.id "
        "GROUP BY a.id ORDER BY total DESC")
    por_estado = db.consultar(
        "SELECT estado, COUNT(*) AS total FROM procesos "
        "GROUP BY estado ORDER BY total DESC")
    por_tipo = db.consultar(
        "SELECT tipo, COUNT(*) AS total FROM procesos "
        "GROUP BY tipo ORDER BY total DESC")
    totales = {
        "clientes": db.consultar("SELECT COUNT(*) AS n FROM usuarios WHERE rol='cliente'")[0]["n"],
        "procesos": db.consultar("SELECT COUNT(*) AS n FROM procesos")[0]["n"],
        "actuaciones": db.consultar("SELECT COUNT(*) AS n FROM actuaciones")[0]["n"],
        "documentos": db.consultar("SELECT COUNT(*) AS n FROM documentos")[0]["n"],
        "expedientes": db.consultar("SELECT COUNT(*) AS n FROM expedientes")[0]["n"],
        "abogados": db.consultar("SELECT COUNT(*) AS n FROM abogados WHERE activo = 1")[0]["n"],
        "citas_pendientes": db.consultar("SELECT COUNT(*) AS n FROM citas WHERE estado='Pendiente'")[0]["n"],
        "citas_confirmadas": db.consultar("SELECT COUNT(*) AS n FROM citas WHERE estado='Confirmada'")[0]["n"],
        "contactos_no_leidos": db.consultar("SELECT COUNT(*) AS n FROM contactos WHERE leido = 0")[0]["n"],
    }
    citas_totales = db.consultar("SELECT COUNT(*) AS n FROM citas")[0]["n"]
    contactos_totales = db.consultar("SELECT COUNT(*) AS n FROM contactos")[0]["n"]

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    estilos = getSampleStyleSheet()
    estilo_titulo = ParagraphStyle('TituloRep', parent=estilos['Title'],
                                   fontSize=18, leading=22, spaceAfter=6,
                                   textColor=colors.HexColor('#0a2d86'))
    estilo_sub = ParagraphStyle('SubRep', parent=estilos['Normal'],
                                fontSize=10, leading=13, spaceAfter=14,
                                textColor=colors.HexColor('#5b6472'))
    estilo_h2 = ParagraphStyle('H2Rep', parent=estilos['Heading2'],
                               fontSize=13, leading=16, spaceBefore=14, spaceAfter=6,
                               textColor=colors.HexColor('#0a2d86'))
    estilo_celda = ParagraphStyle('Celda', parent=estilos['Normal'],
                                  fontSize=9, leading=11)
    estilo_celda_c = ParagraphStyle('CeldaC', parent=estilo_celda,
                                    alignment=TA_CENTER)
    estilo_celda_r = ParagraphStyle('CeldaR', parent=estilo_celda,
                                    alignment=TA_RIGHT)

    elementos = []

    # Cabecera
    elementos.append(Paragraph("Reporte Operativo — Derechos On", estilo_titulo))
    elementos.append(Paragraph(f"Generado el {datetime.now().strftime('%d/%m/%Y %H:%M')}", estilo_sub))
    elementos.append(Spacer(1, 8))

    # KPIs totales
    elementos.append(Paragraph("Resumen General", estilo_h2))
    datos_kpi = [["Indicador", "Valor"]]
    for etiqueta, clave in (("Clientes", "clientes"), ("Procesos", "procesos"),
                            ("Actuaciones", "actuaciones"), ("Documentos", "documentos"),
                            ("Expedientes", "expedientes"), ("Abogados activos", "abogados"),
                            ("Citas pendientes", "citas_pendientes"),
                            ("Citas confirmadas", "citas_confirmadas"),
                            ("Total citas", "citas_totales"),
                            ("Mensajes sin leer", "contactos_no_leidos"),
                            ("Total contactos", "contactos_totales")):
        val = totales.get(clave, 0) if clave in totales else (citas_totales if clave == "citas_totales"
                                                                else contactos_totales if clave == "contactos_totales"
                                                                else 0)
        datos_kpi.append([etiqueta, str(val)])
    t_kpi = Table(datos_kpi, colWidths=[10*cm, 4*cm])
    t_kpi.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0a2d86')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e3eaf5')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f9ff')]),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elementos.append(t_kpi)
    elementos.append(Spacer(1, 10))

    # Procesos por abogado
    elementos.append(Paragraph("Procesos por Abogado", estilo_h2))
    datos_abg = [["Abogado", "Procesos", "A favor"]]
    for r in por_abogado:
        datos_abg.append([r["nombre"], str(r["total"]), str(r["favor"] or 0)])
    if len(datos_abg) == 1:
        datos_abg.append(["(sin datos)", "", ""])
    t_abg = Table(datos_abg, colWidths=[8*cm, 3*cm, 3*cm])
    t_abg.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0a2d86')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e3eaf5')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f9ff')]),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elementos.append(t_abg)
    elementos.append(Spacer(1, 10))

    # Procesos por estado
    elementos.append(Paragraph("Procesos por Estado", estilo_h2))
    datos_est = [["Estado", "Cantidad"]]
    for r in por_estado:
        datos_est.append([r["estado"], str(r["total"])])
    if len(datos_est) == 1:
        datos_est.append(["(sin datos)", ""])
    t_est = Table(datos_est, colWidths=[10*cm, 4*cm])
    t_est.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0a2d86')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (1, 0), (1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e3eaf5')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f9ff')]),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elementos.append(t_est)
    elementos.append(Spacer(1, 10))

    # Procesos por tipo
    elementos.append(Paragraph("Procesos por Tipo", estilo_h2))
    datos_tip = [["Tipo", "Cantidad"]]
    for r in por_tipo:
        datos_tip.append([r["tipo"] or "Sin tipo", str(r["total"])])
    if len(datos_tip) == 1:
        datos_tip.append(["(sin datos)", ""])
    t_tip = Table(datos_tip, colWidths=[10*cm, 4*cm])
    t_tip.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0a2d86')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (1, 0), (1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e3eaf5')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f9ff')]),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elementos.append(t_tip)

    doc.build(elementos)
    buffer.seek(0)
    return Response(buffer.getvalue(), mimetype="application/pdf",
                    headers={"Content-Disposition": "attachment; filename=reporte-operativo.pdf"})


# ------- panel de análisis
RANGOS_PANEL = [
    ("hoy", "Hoy"), ("7d", "7 días"), ("30d", "30 días"), ("90d", "90 días"),
    ("12m", "12 meses"), ("ano", "Año en curso"), ("todo", "Todo"),
]
EXPR_BUCKET = {"dia": "substr(%s,1,10)", "mes": "substr(%s,1,7)", "ano": "substr(%s,1,4)"}
NOM_GRAN = {"dia": "día", "mes": "mes", "ano": "año"}


def _buckets(d, h, g):
    """Lista de claves de agrupación (día, mes o año) entre dos fechas."""
    out = []
    if g == "dia":
        x = d
        while x <= h:
            out.append(x.isoformat())
            x += timedelta(days=1)
    elif g == "mes":
        y, m = d.year, d.month
        while (y, m) <= (h.year, h.month):
            out.append("%04d-%02d" % (y, m))
            m += 1
            if m > 12:
                m, y = 1, y + 1
    else:
        for y in range(d.year, h.year + 1):
            out.append(str(y))
    return out


def _etiqueta_bucket(b, g):
    """Etiqueta corta y descripción larga de un bucket."""
    if g == "dia":
        d = fecha_parse(b)
        return ("%d %s" % (d.day, MESES_ES[d.month - 1][:3]),
                "%d de %s de %d" % (d.day, MESES_ES[d.month - 1], d.year))
    if g == "mes":
        y, m = int(b[:4]), int(b[5:7])
        return ("%s %s" % (MESES_ES[m - 1][:3], b[2:4]),
                "%s de %d" % (MESES_ES[m - 1].capitalize(), y))
    return b, "Año %s" % b


def _periodo_panel(args):
    """Resuelve período (?r=) y granularidad (?g=) del panel de análisis."""
    hoy = date.today()
    clave = (args.get("r") or "7d").strip().lower()
    if clave not in [k for k, _ in RANGOS_PANEL]:
        clave = "7d"
    d = fecha_parse((args.get("desde") or "").strip())
    h = fecha_parse((args.get("hasta") or "").strip())
    personalizado = bool(d or h)
    if d and h:
        if d > h:
            d, h = h, d
    elif d:
        h = hoy
    elif h:
        d = h - timedelta(days=6)
    elif clave == "hoy":
        d = h = hoy
    elif clave == "30d":
        d, h = hoy - timedelta(days=29), hoy
    elif clave == "90d":
        d, h = hoy - timedelta(days=89), hoy
    elif clave == "12m":
        d, h = date(hoy.year - 1, hoy.month, 1), hoy
    elif clave == "ano":
        d, h = date(hoy.year, 1, 1), hoy
    elif clave == "todo":
        primero = db.consultar("SELECT MIN(substr(creado_el,1,10)) AS f FROM visitas")
        d = fecha_parse((primero[0]["f"] or "") if primero else "") or (hoy - timedelta(days=29))
        h = hoy
    else:
        d, h = hoy - timedelta(days=6), hoy
    d = max(min(d, hoy), date(2000, 1, 1))
    h = min(h, hoy)
    if d > h:
        d, h = h, d
    dias = (h - d).days + 1

    g = (args.get("g") or "auto").strip().lower()
    if g not in ("dia", "mes", "ano"):
        g = "auto"
    g_sel = g
    if g == "auto":
        g = "dia" if dias <= 92 else ("mes" if dias <= 900 else "ano")
    while g == "dia" and len(_buckets(d, h, g)) > 180:
        g = "mes"
    while g == "mes" and len(_buckets(d, h, g)) > 180:
        g = "ano"

    if personalizado:
        if dias == 1:
            etiqueta = "1 día"
        elif dias <= 60:
            etiqueta = "%d días" % dias
        elif dias <= 900:
            etiqueta = "%d meses" % max(1, round(dias / 30.0))
        else:
            etiqueta = "%d años" % max(1, round(dias / 365.0))
    else:
        etiqueta = {"hoy": "hoy", "7d": "7 días", "30d": "30 días",
                    "90d": "90 días", "12m": "12 meses", "ano": "año %d" % hoy.year,
                    "todo": "histórico"}[clave]

    def _corta(f):
        return "%d %s %d" % (f.day, MESES_ES[f.month - 1][:3], f.year)

    if d == h:
        periodo_texto = _corta(d)
    else:
        periodo_texto = "%s – %s" % (_corta(d), _corta(h))
    return {"rango": clave, "personalizado": personalizado, "desde": d, "hasta": h,
            "desde_iso": d.isoformat(), "hasta_iso": h.isoformat(), "dias": dias,
            "gran": g, "gran_sel": g_sel, "gran_nombre": NOM_GRAN[g],
            "etiqueta_periodo": etiqueta, "periodo_texto": periodo_texto,
            "periodo_largo": "Del %s al %s (%d días, agrupado por %s)" % (
                _corta(d), _corta(h), dias, NOM_GRAN[g])}


def _datos_panel(args=None):
    args = args if args is not None else request.args
    hoy = date.today()
    hoy_iso = hoy.isoformat()
    P = _periodo_panel(args)
    desde_iso, hasta_iso = P["desde_iso"], P["hasta_iso"]

    visitas_hoy = _contar("SELECT COUNT(*) AS n FROM visitas WHERE substr(creado_el,1,10)=?", (hoy_iso,))
    visitas_periodo = _contar(
        "SELECT COUNT(*) AS n FROM visitas WHERE substr(creado_el,1,10)>=? AND substr(creado_el,1,10)<=?",
        (desde_iso, hasta_iso))
    unicas_periodo = _contar(
        "SELECT COUNT(DISTINCT sesion) AS n FROM visitas "
        "WHERE substr(creado_el,1,10)>=? AND substr(creado_el,1,10)<=? AND sesion<>''",
        (desde_iso, hasta_iso))
    vuelta_periodo = _contar(
        "SELECT COUNT(*) AS n FROM visitas "
        "WHERE substr(creado_el,1,10)>=? AND substr(creado_el,1,10)<=? AND es_vuelta=1",
        (desde_iso, hasta_iso))
    inter_periodo = _contar(
        "SELECT COUNT(*) AS n FROM interacciones "
        "WHERE substr(creado_el,1,10)>=? AND substr(creado_el,1,10)<=?",
        (desde_iso, hasta_iso))

    # ---- serie por día, mes o año según el período elegido
    expr = EXPR_BUCKET[P["gran"]] % "creado_el"
    filas_serie = db.consultar(
        "SELECT %s AS b, COUNT(*) AS n FROM visitas "
        "WHERE substr(creado_el,1,10)>=? AND substr(creado_el,1,10)<=? GROUP BY b" % expr,
        (desde_iso, hasta_iso))
    mapa = {r["b"]: r["n"] for r in filas_serie}
    serie_visitas, max_serie = [], 1
    for b in _buckets(P["desde"], P["hasta"], P["gran"]):
        n = mapa.get(b, 0)
        etq, sub = _etiqueta_bucket(b, P["gran"])
        max_serie = max(max_serie, n)
        serie_visitas.append({"clave": b, "etq": etq, "sub": sub, "n": n})
    if max_serie < 4:
        max_serie = 4
    if P["gran"] == "dia" and serie_visitas:
        serie_visitas[-1]["es_hoy"] = True

    por_tipo = db.consultar(
        "SELECT tipo, COUNT(*) AS n FROM interacciones "
        "WHERE substr(creado_el,1,10)>=? AND substr(creado_el,1,10)<=? "
        "GROUP BY tipo ORDER BY n DESC", (desde_iso, hasta_iso))

    top_paginas = db.consultar(
        "SELECT pagina, COUNT(*) AS n FROM visitas "
        "WHERE substr(creado_el,1,10)>=? AND substr(creado_el,1,10)<=? AND pagina<>'' "
        "GROUP BY pagina ORDER BY n DESC LIMIT 8", (desde_iso, hasta_iso))

    # ---- cartera y pagos
    registros = db.cartera_todas()
    total_cartera = round(sum(float(r["valor_total"] or 0) for r in registros), 2)
    total_pagado = round(sum(float(r["pagado"] or 0) for r in registros), 2)
    total_saldo = round(total_cartera - total_pagado, 2)
    tasa_cobro = round(total_pagado / total_cartera * 100, 1) if total_cartera else 0

    estados = {}
    for r in registros:
        saldo = float(r["valor_total"] or 0) - float(r["pagado"] or 0)
        r["saldo"] = round(saldo, 2)
        r["estado"] = _estado_cartera(r)
        estados.setdefault(r["estado"], []).append(r)
    en_mora_items = estados.get("Vencida", [])
    por_vencer_items = [r for r in registros
                        if r["saldo"] > 0.01 and r.get("vencimiento")
                        and hoy_iso <= r["vencimiento"] <= (hoy + timedelta(days=30)).isoformat()]
    en_mora_saldo = round(sum(r["saldo"] for r in en_mora_items), 2)
    por_vencer_saldo = round(sum(r["saldo"] for r in por_vencer_items), 2)
    al_dia_saldo = round(total_saldo - en_mora_saldo - por_vencer_saldo, 2)
    donut = [
        {"label": "Al día / Pagada", "valor": round(total_cartera - en_mora_saldo - por_vencer_saldo, 2),
         "clase": "verde", "detalle": "Saldo al día o ya cubierto"},
        {"label": "Por vencer (30 días)", "valor": por_vencer_saldo,
         "clase": "ambar", "detalle": "Vencen dentro del próximo mes"},
        {"label": "Vencida", "valor": en_mora_saldo,
         "clase": "rojo", "detalle": "Saldo con vencimiento pasado"},
    ]

    fecha_comp = "substr(COALESCE(NULLIF(validado_el,''),cargado_el),1,10)"
    comp_estados = db.consultar(
        "SELECT estado, COUNT(*) AS n, SUM(importe) AS tot FROM comprobantes "
        "WHERE %s>=? AND %s<=? GROUP BY estado" % (fecha_comp, fecha_comp),
        (desde_iso, hasta_iso))
    comp = {r["estado"]: r for r in comp_estados}

    def cnum(estado, campo):
        r = comp.get(estado)
        return (r[campo] or 0) if r else 0

    comp_validados = {"n": cnum("Validado", "n"), "tot": round(cnum("Validado", "tot"), 2)}
    comp_pendientes = {"n": cnum("Pendiente", "n"), "tot": round(cnum("Pendiente", "tot"), 2)}
    comp_rechazados = {"n": cnum("Rechazado", "n"), "tot": round(cnum("Rechazado", "tot"), 2)}

    ultimos_comprobantes = db.consultar(
        "SELECT cp.*, u.nombre AS cliente, c.servicio AS servicio_cartera "
        "FROM comprobantes cp JOIN usuarios u ON u.id=cp.cliente_id "
        "LEFT JOIN cartera c ON c.id=cp.cartera_id "
        "WHERE cp.estado='Validado' AND substr(cp.validado_el,1,10)>=? "
        "AND substr(cp.validado_el,1,10)<=? ORDER BY cp.validado_el DESC LIMIT 5",
        (desde_iso, hasta_iso))

    expr_v = EXPR_BUCKET[P["gran"]] % "validado_el"
    filas_cobro = db.consultar(
        "SELECT %s AS b, SUM(importe) AS tot FROM comprobantes "
        "WHERE estado='Validado' AND validado_el<>'' AND substr(validado_el,1,10)>=? "
        "AND substr(validado_el,1,10)<=? GROUP BY b ORDER BY b" % expr_v,
        (desde_iso, hasta_iso))
    mapa_cobro = {r["b"]: r["tot"] for r in filas_cobro}
    serie_cobro, max_cobro = [], 0
    for b in _buckets(P["desde"], P["hasta"], P["gran"]):
        tot = round(mapa_cobro.get(b) or 0, 2)
        if not tot:
            continue
        etq, sub = _etiqueta_bucket(b, P["gran"])
        max_cobro = max(max_cobro, tot)
        serie_cobro.append({"clave": b, "etq": etq, "sub": sub, "tot": tot})
    serie_cobro = serie_cobro[-12:]

    # ---- redes sociales
    cfg = redes.leer_config()
    etiquetas = {"linkedin": "LinkedIn", "x": "X", "instagram": "Instagram"}
    plataformas = []
    for clave in ("linkedin", "x", "instagram"):
        c = cfg[clave]
        ultima = db.consultar(
            "SELECT * FROM redes_metricas WHERE plataforma=? ORDER BY id DESC LIMIT 1", (clave,))
        total_pub = _contar(
            "SELECT COUNT(*) AS n FROM publicaciones_redes WHERE plataforma=? AND estado='ok'",
            (clave,))
        plataformas.append({
            "clave": clave, "nombre": etiquetas[clave],
            "activa": bool(c["activa"]),
            "configurada": bool(c.get("token") or c.get("api_key")),
            "publicaciones": total_pub,
            "metrica": ultima[0] if ultima else None,
        })

    publicaciones = db.consultar(
        "SELECT pr.*, n.titulo FROM publicaciones_redes pr "
        "LEFT JOIN noticias n ON n.id=pr.articulo_id ORDER BY pr.id DESC LIMIT 8")
    historial_metricas = db.consultar(
        "SELECT fecha, plataforma, seguidores, alcance, impresiones, interacciones "
        "FROM redes_metricas ORDER BY id DESC LIMIT 10")

    conectadas = redes.plataformas_conectadas()
    sync_ultimo = db.red_sync_ultimo()
    sync_horas = None
    if sync_ultimo and sync_ultimo.get("ejecutado_el"):
        try:
            desde = datetime.strptime(str(sync_ultimo["ejecutado_el"])[:19],
                                      "%Y-%m-%d %H:%M:%S")
            sync_horas = max(0.0, (datetime.now() - desde).total_seconds() / 3600.0)
        except (TypeError, ValueError):
            sync_horas = None

    if REDES_AUTO_MINUTOS < 60:
        auto_texto = "cada %d minutos" % REDES_AUTO_MINUTOS
    elif REDES_AUTO_MINUTOS % 60 == 0:
        horas = REDES_AUTO_MINUTOS // 60
        auto_texto = "cada %d %s" % (horas, "hora" if horas == 1 else "horas")
    else:
        auto_texto = "cada %d h %d min" % (REDES_AUTO_MINUTOS // 60,
                                           REDES_AUTO_MINUTOS % 60)

    return dict(periodo=P, rango=P["rango"], etiqueta_periodo=P["etiqueta_periodo"],
        periodo_texto=P["periodo_texto"], periodo_largo=P["periodo_largo"],
        gran=P["gran"], gran_sel=P["gran_sel"], gran_nombre=P["gran_nombre"],
        dias_periodo=P["dias"], rango_presets=RANGOS_PANEL,
        visitas_hoy=visitas_hoy, visitas_periodo=visitas_periodo,
        unicas_periodo=unicas_periodo, vuelta_periodo=vuelta_periodo,
        inter_periodo=inter_periodo,
        serie_visitas=serie_visitas, max_serie=max_serie,
        por_tipo=por_tipo, top_paginas=top_paginas,
        registros=registros,
        total_cartera=total_cartera, total_pagado=total_pagado,
        total_saldo=total_saldo, tasa_cobro=tasa_cobro,
        en_mora=len(en_mora_items), en_mora_saldo=en_mora_saldo,
        por_vencer=len(por_vencer_items), por_vencer_saldo=por_vencer_saldo,
        al_dia_saldo=al_dia_saldo, donut=donut,
        comp_validados=comp_validados, comp_pendientes=comp_pendientes,
        comp_rechazados=comp_rechazados,
        ultimos_comprobantes=ultimos_comprobantes, serie_cobro=serie_cobro,
        max_cobro=max_cobro,
        plataformas=plataformas, publicaciones=publicaciones,
        historial_metricas=historial_metricas,
        redes_conectadas=[n for _, n in conectadas],
        sync_ultimo=sync_ultimo, sync_horas=sync_horas,
        redes_auto_activo=REDES_AUTO, redes_auto_texto=auto_texto)


@app.route("/admin/panel")
@requiere_admin
def admin_panel():
    return render_template("admin/panel.html", usuario=g.usuario, **_datos_panel())


@app.route("/admin/panel/informe")
@requiere_admin
def admin_panel_informe():
    try:
        pdf = informe.generar_informe(_datos_panel())
    except Exception as e:
        flash("No se pudo generar el informe PDF: %s" % e, "error")
        return redirect(url_for("admin_panel"))
    nombre = "informe-analisis-derechos-on-%s.pdf" % date.today().isoformat()
    return Response(pdf, mimetype="application/pdf",
                    headers={"Content-Disposition":
                             "attachment; filename=%s" % nombre})


@app.route("/admin/panel/metricas", methods=["POST"])
@requiere_admin
def admin_panel_metricas():
    volver = (request.form.get("vuelve") or "").strip()
    destino = url_for("admin_panel")
    if volver.startswith("?") and len(volver) < 400:
        destino += html_mod.escape(volver)
    clave = request.form.get("plataforma", "").strip().lower()
    if request.form.get("accion") == "auto":
        res = redes.registrar_automaticas("manual", forzar=True)
        if res.get("motivo") == "sin_redes":
            flash("No hay ninguna red conectada todavía. Activa y configura al menos "
                  "una en Redes para registrar métricas automáticamente.", "aviso")
        else:
            for linea in (res.get("detalle") or "").split(" · "):
                if linea:
                    flash(linea, "exito" if not res.get("errores") else "aviso")
            if res.get("omitido"):
                flash("No fue necesario actualizar: %s" % res.get("detalle"), "aviso")
    elif clave in ("linkedin", "x", "instagram"):
        flash("El registro manual se retiró: las métricas se toman automáticamente "
              "de las redes conectadas.", "aviso")
    else:
        flash("Solicitud no reconocida.", "error")
    return redirect(destino)


# ---------------------------------------------------------------- redes
# Registro automatico de metricas: cuando hay una red activa y configurada,
# las metricas se recojen solas cada REDES_AUTO_MINUTOS (6 h por defecto) y se
# guarda un snapshot por plataforma y dia. El lock en redes.py evita que los
# dos workers de gunicorn lo hagan a la vez.
REDES_AUTO = os.environ.get("REDES_AUTO", "1") != "0"
REDES_AUTO_MINUTOS = max(5, int(os.environ.get("REDES_AUTO_MINUTOS", "360")))
REDES_AUTO_ESPERA = int(os.environ.get("REDES_AUTO_ESPERA", "45"))
_redes_auto_hilo = None


def _bucle_redes_auto():
    time.sleep(REDES_AUTO_ESPERA)
    while True:
        try:
            redes.registrar_automaticas("auto", minutos=REDES_AUTO_MINUTOS)
        except Exception:                      # nunca debe tumbar el proceso
            pass
        time.sleep(REDES_AUTO_MINUTOS * 60)


def arrancar_redes_auto():
    """Enciende el hilo de metricas (una vez por proceso,salvo el padre del
    reloader de depuracion)."""
    global _redes_auto_hilo
    if not REDES_AUTO or _redes_auto_hilo is not None:
        return False
    if os.environ.get("WERKZEUG_RUN_MAIN") == "false":
        return False                          # proceso padre del reloader
    _redes_auto_hilo = threading.Thread(target=_bucle_redes_auto, name="redes-auto",
                                        daemon=True)
    _redes_auto_hilo.start()
    return True


# ---------------------------------------------------------------- CRM
CRM_PRIORIDADES = ("baja", "media", "alta", "urgente")
CRM_ESTADOS = ("pendiente", "en_proceso", "completada", "cancelada")
CRM_ESTADO_TXT = {"pendiente": "Pendiente", "en_proceso": "En proceso",
                  "completada": "Completada", "cancelada": "Cancelada"}
CRM_PRIORIDAD_TXT = {"baja": "Baja", "media": "Media", "alta": "Alta", "urgente": "Urgente"}


def _int_o_none(valor):
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def _crm_contexto(tipo, oid, usuario):
    otro = "cliente" if tipo == "abogado" else "abogado"
    return {
        "usuario": usuario,
        "rol_crm": tipo,
        "otro_tipo": otro,
        "otras_personas": crm_core.personas_disponibles(otro),
        "tareas": crm_core.tareas_de(tipo, oid),
        "resumen": crm_core.contar_estado(tipo, oid),
        "recordatorios": crm_core.recordatorios_de(tipo, oid),
        "prioridades": CRM_PRIORIDADES,
        "estados": CRM_ESTADOS,
        "estado_txt": CRM_ESTADO_TXT,
        "prioridad_txt": CRM_PRIORIDAD_TXT,
        "hoy": date.today().isoformat(),
    }


def _crm_tarea_contexto(tipo, oid, tarea):
    return {
        "rol_crm": tipo,
        "otro_tipo": "cliente" if tipo == "abogado" else "abogado",
        "tarea": tarea,
        "comentarios": crm_core.comentarios_tarea(tarea["id"]),
        "estados": CRM_ESTADOS,
        "prioridades": CRM_PRIORIDADES,
        "estado_txt": CRM_ESTADO_TXT,
        "prioridad_txt": CRM_PRIORIDAD_TXT,
        "hoy": date.today().isoformat(),
    }


def _crm_crear_tarea(rol_tipo, oid, datos):
    titulo = (datos.get("titulo") or "").strip()
    if not titulo:
        return None
    return crm_core.crear_tarea(
        titulo=titulo,
        descripcion=(datos.get("descripcion") or "").strip(),
        propietario_tipo=rol_tipo,
        propietario_id=oid,
        asignado_a_tipo=datos.get("asignado_tipo") or None,
        asignado_a_id=_int_o_none(datos.get("asignado_id")),
        prioridad=datos.get("prioridad") if datos.get("prioridad") in CRM_PRIORIDADES else "media",
        estado="pendiente",
        fecha_vencimiento=(datos.get("fecha_vencimiento") or None),
        recordatorio_fecha=(datos.get("recordatorio_fecha") or None),
    )


# ---- CRM abogado
@app.route("/abogado/crm")
@requiere_abogado
def abogado_crm():
    ctx = _crm_contexto("abogado", g.abogado["id"], g.usuario)
    ctx["abogado"] = g.abogado
    return render_template("abogado/crm.html", **ctx)


@app.route("/abogado/crm/tarea", methods=["POST"])
@requiere_abogado
def abogado_crm_tarea_crear():
    tid = _crm_crear_tarea("abogado", g.abogado["id"], request.form)
    if tid:
        flash("Tarea creada correctamente.", "exito")
    else:
        flash("La tarea necesita un título.", "error")
    return redirect(url_for("abogado_crm"))


@app.route("/abogado/crm/tarea/<int:tid>")
@requiere_abogado
def abogado_crm_tarea(tid):
    tarea = crm_core.tarea_visible_para(tid, "abogado", g.abogado["id"])
    if not tarea:
        abort(404)
    return render_template("abogado/crm_tarea.html", abogado=g.abogado,
                           **_crm_tarea_contexto("abogado", g.abogado["id"], tarea))


@app.route("/abogado/crm/tarea/<int:tid>/estado", methods=["POST"])
@requiere_abogado
def abogado_crm_tarea_estado(tid):
    if not crm_core.tarea_visible_para(tid, "abogado", g.abogado["id"]):
        abort(404)
    nuevo = request.form.get("estado")
    if nuevo in CRM_ESTADOS:
        if nuevo == "completada":
            crm_core.completar_tarea(tid)
        else:
            crm_core.actualizar_tarea(tid, estado=nuevo)
    return redirect(request.form.get("volver") or url_for("abogado_crm_tarea", tid=tid))


@app.route("/abogado/crm/tarea/<int:tid>/comentario", methods=["POST"])
@requiere_abogado
def abogado_crm_tarea_comentario(tid):
    if not crm_core.tarea_visible_para(tid, "abogado", g.abogado["id"]):
        abort(404)
    texto = (request.form.get("comentario") or "").strip()
    if texto:
        crm_core.agregar_comentario(tid, "abogado", g.abogado["id"], texto)
    return redirect(url_for("abogado_crm_tarea", tid=tid) + "#comentarios")


@app.route("/abogado/crm/recordatorio", methods=["POST"])
@requiere_abogado
def abogado_crm_recordatorio_crear():
    titulo = (request.form.get("titulo") or "").strip()
    fecha = request.form.get("fecha_programada") or ""
    if titulo and fecha:
        crm_core.crear_recordatorio(titulo=titulo,
                                    mensaje=(request.form.get("mensaje") or "").strip(),
                                    destinatario_tipo="abogado", destinatario_id=g.abogado["id"],
                                    tarea_id=_int_o_none(request.form.get("tarea_id")),
                                    fecha_programada=fecha)
    return redirect(url_for("abogado_crm"))


@app.route("/abogado/crm/recordatorio/<int:rid>/hecho", methods=["POST"])
@requiere_abogado
def abogado_crm_recordatorio_hecho(rid):
    crm_core.marcar_recordatorio_enviado(rid)
    return redirect(url_for("abogado_crm"))


# ------------------------------------------------- portal de asociaciones
IAT_TIPOS = ("Aprovechamiento", "No aprovechamiento", "Capacitación y formalización")
IAT_ESTADOS = ("Radicado", "En evaluación", "Aprobado", "Negado")


def _asociacion_datos(usuario):
    try:
        extra = json.loads(usuario.get("datos_extra") or "{}")
    except (TypeError, ValueError):
        extra = {}
    if not isinstance(extra, dict):
        extra = {}
    return extra


@app.route("/asociacion")
@requiere_asociacion
def asociacion_inicio():
    solicitudes = db.iat_de_usuario(g.usuario["id"])
    estados = {e: 0 for e in IAT_ESTADOS}
    for s in solicitudes:
        estados[s["estado"]] = estados.get(s["estado"], 0) + 1
    return render_template("asociacion/dashboard.html",
                           usuario=g.usuario,
                           extra=_asociacion_datos(g.usuario),
                           solicitudes=solicitudes[:5],
                           estados=estados,
                           total=len(solicitudes),
                           hoy=date.today())


@app.route("/asociacion/iat")
@requiere_asociacion
def asociacion_iat():
    return render_template("asociacion/iat.html",
                           usuario=g.usuario,
                           extra=_asociacion_datos(g.usuario),
                           solicitudes=db.iat_de_usuario(g.usuario["id"]),
                           tipos=IAT_TIPOS, estados=IAT_ESTADOS,
                           ia_activa=bool(ia_juridica.configurado()),
                           organizacion=(g.usuario.get("nombre") or ""),
                           hoy=date.today())


@app.route("/asociacion/iat/proyecto", methods=["POST"])
@requiere_asociacion
def asociacion_iat_crear():
    titulo = (request.form.get("titulo") or "").strip()
    descripcion = (request.form.get("descripcion") or "").strip()
    if not titulo or not descripcion:
        flash("El proyecto necesita título y descripción.", "error")
        return redirect(url_for("asociacion_iat"))
    tipo = request.form.get("tipo") or IAT_TIPOS[0]
    if tipo not in IAT_TIPOS:
        tipo = IAT_TIPOS[0]
    try:
        toneladas = float(request.form.get("toneladas") or 0)
    except ValueError:
        toneladas = 0
    try:
        censo = int(float(request.form.get("censo") or 0))
    except ValueError:
        censo = 0
    try:
        asociados_pct = float(request.form.get("asociados_pct") or 0)
    except ValueError:
        asociados_pct = 0
    formalizacion = request.form.get("formalizacion") or ""
    if formalizacion not in agente_iat.FORMALIZACION_OPCIONES:
        formalizacion = "en_formalizacion"
    meta_reduccion = request.form.get("meta_reduccion") or ""
    if meta_reduccion not in agente_iat.META_OPCIONES:
        meta_reduccion = ""
    puntaje_form = request.form.get("evaluacion_puntaje") or ""
    try:
        puntaje_form = int(float(puntaje_form))
        if puntaje_form < 0 or puntaje_form > 100:
            puntaje_form = ""
    except (TypeError, ValueError):
        puntaje_form = ""
    datos_proyecto = {
        "titulo": titulo[:200],
        "tipo": tipo,
        "municipio": (request.form.get("municipio") or "").strip()[:120],
        "descripcion": descripcion[:4000],
        "toneladas": max(0, toneladas),
        "censo": max(0, censo),
        "asociados_pct": max(0, min(100, asociados_pct)),
        "formalizacion": formalizacion,
        "meta_reduccion": meta_reduccion,
        "acuerdos": (request.form.get("acuerdos") or "").strip()[:800] or (descripcion[:600] if "operador" in descripcion else ""),
        "documento": (request.form.get("documento_archivo") or "").strip(),
        "checklist": bool(request.form.get("checklist")),
        "organizacion": (g.usuario.get("nombre") or ""),
        "evaluacion_puntaje": puntaje_form if puntaje_form != "" else None,
    }
    sid = db.iat_crear({
        "usuario_id": g.usuario["id"],
        "titulo": titulo[:200],
        "tipo": tipo,
        "descripcion": descripcion[:4000],
        "toneladas": max(0, toneladas),
        "municipio": datos_proyecto["municipio"],
        "datos": datos_proyecto,
    })
    fila = db.iat_por_id(sid)
    flash(f"Proyecto radicado con consecutivo {fila['radicado']}.", "exito")
    return redirect(url_for("asociacion_iat_detalle", sid=sid))


@app.route("/asociacion/iat/<int:sid>")
@requiere_asociacion
def asociacion_iat_detalle(sid):
    solicitud = db.iat_por_id(sid)
    if not solicitud or solicitud["usuario_id"] != g.usuario["id"]:
        abort(404)
    try:
        datos_proyecto = json.loads(solicitud.get("datos") or "{}")
    except (TypeError, ValueError):
        datos_proyecto = {}
    if not isinstance(datos_proyecto, dict):
        datos_proyecto = {}
    return render_template("asociacion/iat_proyecto.html",
                           usuario=g.usuario, solicitud=solicitud,
                           tipos=IAT_TIPOS, estados=IAT_ESTADOS,
                           datos=datos_proyecto,
                           ia_activa=bool(ia_juridica.configurado()))


@app.route("/asociacion/iat/<int:sid>/editar", methods=["POST"])
@requiere_asociacion
def asociacion_iat_editar(sid):
    solicitud = db.iat_por_id(sid)
    if not solicitud or solicitud["usuario_id"] != g.usuario["id"]:
        abort(404)
    if solicitud["estado"] not in ("Radicado", "En evaluación"):
        flash("El proyecto ya fue resuelto por la alcaldía y no admite cambios.", "error")
        return redirect(url_for("asociacion_iat_detalle", sid=sid))
    titulo = (request.form.get("titulo") or "").strip()
    descripcion = (request.form.get("descripcion") or "").strip()
    tipo = request.form.get("tipo") or solicitud["tipo"]
    if tipo not in IAT_TIPOS:
        tipo = solicitud["tipo"]
    try:
        toneladas = float(request.form.get("toneladas") or 0)
    except ValueError:
        toneladas = float(solicitud["toneladas"] or 0)
    try:
        censo = int(float(request.form.get("censo") or 0))
    except ValueError:
        censo = 0
    try:
        asociados_pct = float(request.form.get("asociados_pct") or 0)
    except ValueError:
        asociados_pct = 0
    formalizacion = request.form.get("formalizacion") or ""
    if formalizacion not in (agente_iat.FORMALIZACION_OPCIONES if agente_iat else ()) :
        formalizacion = "en_formalizacion"
    meta_reduccion = request.form.get("meta_reduccion") or ""
    if meta_reduccion not in (agente_iat.META_OPCIONES if agente_iat else ()):
        meta_reduccion = ""
    datos_previos = {}
    try:
        datos_previos = json.loads(solicitud.get("datos") or "{}")
    except (TypeError, ValueError):
        datos_previos = {}
    if not isinstance(datos_previos, dict):
        datos_previos = {}
    datos_actuales = dict(datos_previos)
    datos_actuales.update({
        "titulo": titulo[:200] or solicitud["titulo"],
        "tipo": tipo,
        "municipio": (request.form.get("municipio") or "").strip()[:120] or datos_actuales.get("municipio", ""),
        "descripcion": descripcion[:4000] or solicitud["descripcion"],
        "toneladas": max(0, toneladas),
        "censo": max(0, censo),
        "asociados_pct": max(0, min(100, asociados_pct)),
        "formalizacion": formalizacion,
        "meta_reduccion": meta_reduccion,
        "acuerdos": (request.form.get("acuerdos") or "").strip()[:800] or datos_actuales.get("acuerdos", ""),
        "documento": (request.form.get("documento_archivo") or "").strip() or datos_actuales.get("documento", ""),
        "checklist": bool(request.form.get("checklist")) or datos_actuales.get("checklist", False),
    })
    db.iat_actualizar(sid, {
        "titulo": titulo[:200] or solicitud["titulo"],
        "descripcion": descripcion[:4000] or solicitud["descripcion"],
        "tipo": tipo,
        "toneladas": max(0, toneladas),
        "municipio": datos_actuales["municipio"],
        "estado": solicitud["estado"],
        "observaciones": solicitud["observaciones"],
        "datos": json.dumps(datos_actuales, ensure_ascii=False),
    })
    flash("Proyecto actualizado.", "exito")
    return redirect(url_for("asociacion_iat_detalle", sid=sid))


@app.route("/asociacion/iat/<int:sid>/eliminar", methods=["POST"])
@requiere_asociacion
def asociacion_iat_eliminar(sid):
    solicitud = db.iat_por_id(sid)
    if not solicitud or solicitud["usuario_id"] != g.usuario["id"]:
        abort(404)
    if solicitud["estado"] != "Radicado":
        flash("Solo se pueden retirar proyectos aún no evaluados.", "error")
        return redirect(url_for("asociacion_iat_detalle", sid=sid))
    db.iat_eliminar(sid)
    flash("Proyecto retirado.", "exito")
    return redirect(url_for("asociacion_iat"))


IAT_ASISTENTE_NOMBRE = "Agente IAT"

# Directorio para los documentos que sube la asociación para su evaluación.
IAT_UPLOAD_DIR = os.path.join(UPLOAD_DIR, "iat")
os.makedirs(IAT_UPLOAD_DIR, exist_ok=True)
EXTENSIONES_IAT_DOC = {".txt", ".md", ".pdf", ".docx"}


def _extraer_documento(archivo, nombre_servido):
    """Extrae texto de TXT/MD/PDF/DOCX. Devuelve (texto, error)."""
    ext = os.path.splitext(nombre_servido)[1].lower()
    ruta = os.path.join(IAT_UPLOAD_DIR, nombre_servido)
    try:
        if ext in (".txt", ".md"):
            with open(ruta, "r", encoding="utf-8", errors="ignore") as f:
                return f.read(), None
        if ext == ".pdf":
            try:
                from pypdf import PdfReader
            except Exception:
                try:
                    from PyPDF2 import PdfReader
                except Exception:
                    try:
                        from pdfplumber import open as pdf_open
                    except Exception:
                        return "", ("El PDF no se pudo leer en el servidor. "
                                    "Convierte el documento a TXT o copia su texto en la descripción.")
                    with pdf_open(ruta) as pdf:
                        return "\n".join(p.extract_text() or "" for p in pdf.pages), None
            lector = PdfReader(ruta)
            return "\n".join((p.extract_text() or "") for p in lector.pages), None
        if ext == ".docx":
            try:
                import docx as docx_lib
            except Exception:
                return "", ("El DOCX no se pudo leer en el servidor. "
                            "Convierte el documento a TXT o copia su texto en la descripción.")
            doc = docx_lib.Document(ruta)
            return "\n".join(p.text for p in doc.paragraphs), None
    except Exception as e:
        return "", "No se pudo leer el documento: %s" % str(e)[:180]
    return "", "Formato no soportado para extraer texto."


@app.route("/api/asociacion/iat/subir", methods=["POST"])
@requiere_asociacion
def iat_documento_subir():
    """Permite a la asociación cargar su proyecto. Se extrae el texto y queda
    guardado junto al archivo original para su evaluación."""
    archivo = request.files.get("documento")
    if not archivo or not archivo.filename:
        return jsonify({"ok": False, "error": "Selecciona un archivo para subir."})
    original = os.path.basename(archivo.filename.replace("\\", "/"))
    ext = os.path.splitext(original)[1].lower()
    if ext not in EXTENSIONES_IAT_DOC:
        return jsonify({"ok": False,
                        "error": "Formato no permitido. Usa TXT, MD, PDF o DOCX."})
    nombre_guardado = uuid.uuid4().hex + ext
    archivo.save(os.path.join(IAT_UPLOAD_DIR, nombre_guardado))
    texto, error = _extraer_documento(archivo, nombre_guardado)
    if error:
        try:
            os.remove(os.path.join(IAT_UPLOAD_DIR, nombre_guardado))
        except OSError:
            pass
        return jsonify({"ok": False, "error": error})
    sidecar = os.path.join(IAT_UPLOAD_DIR, uuid.uuid4().hex + ".txt")
    try:
        with open(sidecar, "w", encoding="utf-8") as f:
            f.write(texto)
    except OSError:
        sidecar = ""
    _registrar_interaccion("iat_documento", detalle=(original or "")[:120])
    return jsonify({
        "ok": True,
        "archivo": original,
        "guardado": nombre_guardado,
        "texto": texto[:15000],
        "tamano": len(texto),
    })


@app.route("/api/asociacion/iat/evaluar", methods=["POST"])
@requiere_asociacion
def iat_evaluar():
    """Evalúa el proyecto con rúbrica determinista (puntaje REAL) y, si la IA
    está configurada, redacta el informe con fortalezas, debilidades y cambios."""
    if not agente_iat:
        return jsonify({"ok": False, "error": "El agente IAT no está disponible."})
    datos = request.get_json(silent=True) or {}
    proyecto = dict(datos.get("proyecto") or {})
    documento_texto = str(datos.get("documento_texto") or "").strip()
    if documento_texto:
        proyecto["documento"] = proyecto.get("documento") or "documento_cargado"
        if str(proyecto.get("descripcion") or "").strip():
            proyecto["descripcion"] = proyecto["descripcion"] + "\n\n" + documento_texto[:8000]
        else:
            proyecto["descripcion"] = documento_texto[:8000]
    proyecto["checklist"] = bool(proyecto.get("checklist"))

    evaluacion = agente_iat.evaluar(proyecto)
    puntaje = evaluacion["puntaje"]

    informe = None
    if ia_juridica.configurado():
        try:
            sistema = ("Eres el AGENTE IAT de Derechos On: especialista en el Incentivo al "
                       "Aprovechamiento y Tratamiento de Residuos Sólidos. Redactas, en "
                       "markdown, el INFORME DE EVALUACIÓN de un proyecto de aprovechamiento. "
                       "El PUNTAJE lo calculó el sistema con una rúbrica verificable; tu tarea "
                       "es EXPLICARLO con secciones: ## Puntaje, ## Fortalezas, ## Debilidades, "
                       "## Cambios requeridos (lista priorizada uno por línea) y una recomendación "
                       "final de máx. 3 líneas. NUNCA cambies el puntaje del sistema ni inventes "
                       "normas: si dudas de una norma, remite al marco IAT (Ley 1753 de 2015, "
                       "Decreto 802 de 2022 y Resolución 547 de 2022). Sé concreto, en español "
                       "colombiano, sin HTML.")
            base = ("DATOS DEL PROYECTO:\n%s\n\n"
                    "PUNTAJE CALCULADO POR EL SISTEMA (NO MODIFICAR): %d/100\n\n"
                    "DESGLOSE (criterio / puntos / máximo):\n%s\n\n"
                    "BASE DE FORTALEZAS:\n%s\n\n"
                    "BASE DE DEBILIDADES:\n%s\n\n"
                    "BASE DE CAMBIOS:\n%s\n") % (
                json.dumps(proyecto, ensure_ascii=False)[:8000],
                puntaje,
                "\n".join("· %s: %d/%d" % (d["criterio"], d["puntos"], d["max"])
                          for d in evaluacion["desglose"]),
                "\n".join("- " + f for f in evaluacion["fortalezas"]),
                "\n".join("- " + d for d in evaluacion["debilidades"]),
                "\n".join("- " + c for c in evaluacion["cambios"]),
            )
            r = ia_juridica.consultar(
                [{"role": "user", "content": base}],
                max_tokens=1800, temperatura=0.4, sistema=sistema)
            informe = (r.get("texto") or "").strip() or None
        except Exception:
            informe = None

    instrumentos = agente_iat.instrumentos(proyecto, evaluacion)
    _registrar_interaccion("iat_evaluar", detalle="puntaje %d/100" % puntaje)
    return jsonify({
        "ok": True,
        "puntaje": puntaje,
        "desglose": evaluacion["desglose"],
        "fortalezas": evaluacion["fortalezas"],
        "debilidades": evaluacion["debilidades"],
        "cambios": evaluacion["cambios"],
        "informe": informe,
        "instrumentos": instrumentos,
    })


@app.route("/api/asociacion/iat/agente", methods=["POST"])
@requiere_asociacion
def iat_agente_chat():
    """Asistente IAT con IA en streaming (SSE). Si la IA no está disponible usa
    el motor determinista de `agente_iat.guiar` para no dejar de funcionar."""
    if not agente_iat:
        return Response(_evento("error", texto="El agente IAT no está disponible en este momento."),
                        mimetype="text/event-stream")
    datos = request.get_json(silent=True) or {}
    mensaje = str(datos.get("mensaje") or "").strip()
    proyecto = dict(datos.get("proyecto") or {})

    if not mensaje:
        return Response(_evento("error", texto="Escribe qué necesitas para ayudarte con el proyecto."),
                        mimetype="text/event-stream")
    if len(mensaje) > LARGO_MAX_CHAT:
        mensaje = mensaje[:LARGO_MAX_CHAT]
        aviso = "Recorté tu mensaje a %d caracteres para poder procesarlo." % LARGO_MAX_CHAT
    else:
        aviso = ""

    espera = _rate_limit_chat(limite=30, segundos=300)
    if espera:
        return Response(_evento("error", texto=(
            "Has hecho muchas consultas seguidas. Espera unos minutos antes de continuar.")),
            mimetype="text/event-stream")

    proyecto_nuevo, extraidos = agente_iat.extraer(mensaje, proyecto)

    def guardar(rol, contenido):
        hist = session.get("iat_historial") or []
        hist.append({"rol": rol, "contenido": contenido[:2000]})
        session["iat_historial"] = hist[-12:]

    def generar():
        proy = dict(proyecto_nuevo)
        yield _evento("inicio", aviso=aviso,
                      ia=bool(ia_juridica.configurado()), extraidos=extraidos)

        mensajes = []
        for turno in (session.get("iat_historial") or [])[-8:]:
            if not isinstance(turno, dict):
                continue
            texto = (turno.get("contenido") or "").strip()
            if not texto:
                continue
            mensajes.append({"role": "assistant" if turno.get("rol") == "asistente" else "user",
                             "content": texto[:4000]})
        mensajes.append({"role": "user", "content": mensaje})

        sistema = agente_iat.SISTEMA_IAT
        try:
            marco = (db.contenido_todos().get("iat_marco_normativo_html") or "").strip()
        except Exception:
            marco = ""
        if marco:
            sistema += ("\n\nMARCO NORMATIVO DEL IAT (base legal del despacho, actualizada por el "
                        "equipo jurídico; úsala para citar normas y fechas con precisión):\n" + marco)
        sistema += ("\n\nMATERIAL DE NORMATIVIDAD (referencia):\n"
                    + agente_iat.normativa_para(proy.get("municipio")))
        try:
            contexto = _contexto_despacho()
        except Exception:
            contexto = ""
        if contexto:
            sistema += "\n\nINFORMACION REAL DEL DESPACHO (promociona solo si encaja de forma natural, sin inventar):\n" + contexto
        sistema += ("\n\nDATOS ACTUALES DEL PROYECTO (los captura la ficha de la asociación; "
                    "usa estos datos, no otros):\n" + json.dumps(proy, ensure_ascii=False)[:6000])

        texto_completo = ""
        uso_ia = False
        ia_visible = False
        if ia_juridica.configurado():
            try:
                for trozo in ia_juridica.consultar_stream(mensajes, sistema=sistema,
                                                          max_tokens=1600, temperatura=0.4):
                    if trozo:
                        ia_visible = True
                    texto_completo += trozo
                    yield _evento("delta", texto=trozo)
                uso_ia = True
            except Exception:
                texto_completo = ""
                if ia_visible:
                    yield _evento("reinicio")

        if not uso_ia:
            texto, opciones, proy = agente_iat.guiar(mensaje, proyecto)
            texto_completo = texto
            for trozo in _trocear(texto, 26):
                yield _evento("delta", texto=trozo)
            yield _evento("opciones", opciones=opciones)

        texto_limpio = texto_completo.strip()
        if texto_limpio:
            yield _evento("fin", texto=texto_limpio, datos=proy)
            guardar("usuario", mensaje)
            guardar("asistente", texto_limpio)
        else:
            yield _evento("error", texto="No pude responder en este momento. Intenta de nuevo en un rato.")

    respuesta = Response(stream_with_context(generar()), mimetype="text/event-stream")
    respuesta.headers["Cache-Control"] = "no-cache, no-transform"
    respuesta.headers["X-Accel-Buffering"] = "no"
    respuesta.headers["Connection"] = "keep-alive"
    try:
        _registrar_interaccion("iat_agente", detalle=mensaje[:120])
    except Exception:
        pass
    return respuesta


@app.route("/abogado/base", methods=["GET", "POST"])
@requiere_abogado
def abogado_base():
    """Base jurídica y jurisprudencial de las organizaciones de recicladores
    (marco del IAT, jurisprudencia y reconocimiento). La mantiene el equipo
    jurídico y alimenta al agente IAT del portal de asociaciones. Incluye el
    motor de búsqueda y de actualización normativa/jurisprudencial."""
    secciones = [
        ("iat_marco_normativo_html", "Marco normativo del IAT",
         "Normas de creación y reglamentación del Incentivo al Aprovechamiento y Tratamiento de Residuos Sólidos."),
        ("iat_jurisprudencia_html", "Jurisprudencia de la Corte Constitucional",
         "Línea de tiempo desde la sentencia hito T-724 de 2003 hasta las providencias más recientes."),
        ("reconocimiento_html", "Reconocimiento de asociaciones de recicladores",
         "Requisitos nacionales, departamentales y municipales para el reconocimiento y la formalización."),
    ]
    if request.method == "POST":
        cambios = {clave: (request.form.get(clave) or "").strip()
                   for clave, _, _ in secciones if (request.form.get(clave) or "").strip()}
        if cambios:
            db.contenido_guardar(cambios)
            flash("Base jurídica y jurisprudencial actualizada.", "exito")
        return redirect(url_for("abogado_base"))

    consulta = (request.args.get("q") or "").strip()
    r = motor_normativo.buscar(consulta) if consulta else None
    return render_template("abogado/base_juridica.html", abogado=g.abogado,
                           secciones=secciones, C=db.contenido_todos(),
                           motor_resumen=db.motor_resumen(),
                           fuentes=db.motor_fuentes_lista(),
                           pendientes=db.motor_normas_lista(estado="pendiente", limite=40),
                           aprobadas=db.motor_normas_lista(estado="aprobada", limite=40),
                           consulta=consulta, resultado=r)


@app.route("/abogado/base/fuentes", methods=["POST"])
@requiere_abogado
def abogado_base_fuentes_crear():
    nombre = (request.form.get("nombre") or "").strip()
    url = (request.form.get("url") or "").strip()
    if not nombre or not re.match(r"^https?://", url):
        flash("Escribe un nombre y una URL oficial válida (https://…).", "error")
        return redirect(url_for("abogado_base"))
    db.motor_fuente_crear(nombre,
                          (request.form.get("tipo") or "norma"),
                          (request.form.get("area") or ""),
                          url)
    flash("Fuente agregada. Se vigilará en la próxima revisión automática.", "exito")
    return redirect(url_for("abogado_base"))


@app.route("/abogado/base/fuentes/<int:fid>", methods=["POST"])
@requiere_abogado
def abogado_base_fuentes_accion(fid):
    accion = request.form.get("accion") or ""
    if accion == "eliminar":
        db.motor_fuente_eliminar(fid)
        flash("Fuente eliminada del motor.", "exito")
    elif accion == "activar":
        db.motor_fuente_actualizar(fid, {"activo": 1})
        flash("Fuente activada.", "exito")
    elif accion == "desactivar":
        db.motor_fuente_actualizar(fid, {"activo": 0})
        flash("Fuente pausada.", "exito")
    elif accion == "revisar":
        r = motor_normativo.revisar_fuente(fid, forzar=True)
        if r.get("ok"):
            flash("Fuente revisada: %d candidatos, %d nuevos." %
                  (r.get("candidatos", 0), r.get("nuevos", 0)), "exito")
        else:
            flash("La fuente no respondió: %s" % r.get("error", "error"), "error")
    elif accion == "limpiar":
        db.motor_fuente_actualizar(fid, {"huella": "", "novedades": 0, "ultimo_cambio": None})
        flash("Contador de novedades reiniciado.", "exito")
    return redirect(url_for("abogado_base"))


@app.route("/abogado/base/normas", methods=["POST"])
@requiere_abogado
def abogado_base_norma_crear():
    titulo = (request.form.get("titulo") or "").strip()
    if not titulo:
        flash("Escribe el título de la norma o providencia.", "error")
        return redirect(url_for("abogado_base"))
    nuevo = db.motor_norma_crear({
        "titulo": titulo,
        "tipo": (request.form.get("tipo") or "norma"),
        "categoria": (request.form.get("categoria") or ""),
        "numero": (request.form.get("numero") or ""),
        "fecha": (request.form.get("fecha") or ""),
        "area": (request.form.get("area") or ""),
        "url": (request.form.get("url") or ""),
        "resumen": (request.form.get("resumen") or ""),
        "origen": "manual", "estado": "aprobada",
    })
    if not nuevo:
        flash("Esa URL ya estaba registrada en el catálogo.", "error")
    else:
        flash("Norma incorporada al catálogo (aprobada).", "exito")
    return redirect(url_for("abogado_base"))


@app.route("/abogado/base/normas/<int:nid>", methods=["POST"])
@requiere_abogado
def abogado_base_norma_accion(nid):
    accion = request.form.get("accion") or ""
    if not db.motor_norma_por_id(nid):
        flash("La norma ya no existe.", "error")
        return redirect(url_for("abogado_base"))
    if accion == "aprobar":
        db.motor_norma_estado(nid, "aprobada")
        flash("Norma aprobada y añadida al catálogo vigente.", "exito")
    elif accion == "descartar":
        db.motor_norma_estado(nid, "descartada")
        flash("Norma descartada.", "exito")
    elif accion == "eliminar":
        db.motor_norma_eliminar(nid)
        flash("Registro eliminado del catálogo.", "exito")
    elif accion == "reabrir":
        db.motor_norma_estado(nid, "pendiente")
        flash("Norma devuelta a pendiente.", "exito")
    return redirect(url_for("abogado_base"))


@app.route("/abogado/base/motor/actualizar", methods=["POST"])
@requiere_abogado
def abogado_base_motor_actualizar():
    r = motor_normativo.revisar_todas(disparador="manual")
    if not r.get("ok"):
        flash("No se pudo revisar (¿ya hay una actualización en curso?): %s"
              % r.get("error", "error"), "error")
    else:
        flash("Revisión completada: %d fuentes, %d con cambios, %d candidatos nuevos."
              % (r.get("revisadas", 0), r.get("cambios", 0), r.get("nuevos", 0)), "exito")
    return redirect(url_for("abogado_base"))


@app.route("/abogado/base/catalogo/cargar", methods=["POST"])
@requiere_abogado
def abogado_base_catalogo_cargar():
    n = motor_normativo.sembrar_desde_base()
    if n:
        flash("Se cargaron %d normas/providencias del IAT desde la base jurídica." % n, "exito")
    else:
        flash("La base jurídica no aportó registros nuevos (ya estaban en el catálogo).", "exito")
    return redirect(url_for("abogado_base"))


if __name__ == "__main__":
    db.iniciar()
    # al arrancar solo se sincronizan los contratos sin firmar; los firmados
    # quedan intactos siempre
    _retext_contratos()
    arrancar_redes_auto()
    motor_normativo.arrancar()
    try:
        motor_normativo.sembrar_desde_base()
    except Exception:
        pass
    host = os.environ.get("HOST", "0.0.0.0")
    puerto = int(os.environ.get("PORT", "5000"))
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"
    app.run(host=host, port=puerto, debug=debug)