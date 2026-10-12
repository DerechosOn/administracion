# -*- coding: utf-8 -*-
"""Motor de búsqueda y actualización normativa y jurisprudencial del IAT.

Está dedicado al tema del Incentivo al Aprovechamiento y Tratamiento de Residuos
(IAT) y a las organizaciones de recicladores de oficio. Su finalidad es mantener
al abogado actualizado en ese tema, no ser una base jurídica general.

Hace dos cosas:

1. BUSQUEDA: consulta el catálogo de normas/providencias del IAT, las secciones
   de la base jurídica del IAT y devuelve resultados unificados con su enlace
   oficial.

2. ACTUALIZACION: vigila las fuentes oficiales del sector (MinVivienda, UAESP,
   Corte Constitucional, Diario Oficial, Función Pública). Cuando el contenido
   de una fuente cambia, extrae los posibles títulos nuevos que traten del IAT
   (recicladores, aprovechamiento, residuos, aseo, PGIRS, RUOR, etc.) y los deja
   como candidatos "pendientes" para que el equipo jurídico los revise.

El motor NO publica nada por sí solo: todo lo que descubre queda en estado
"pendiente" hasta que una persona lo aprueba.
"""
import os
import re
import html as _html
import hashlib
import threading
import time
import unicodedata

import requests

import db

UA = {"User-Agent": "Mozilla/5.0 (compatible; DerechosOnBot/1.0; +https://derechoson.co)",
      "Accept-Language": "es-CO,es;q=0.9"}
TIEMPO_LIMITE = 20
MAX_CANDIDATOS = 30

# Páginas de la base jurídica que también se indexan en la búsqueda.
CLAVES_BASE = ("iat_marco_normativo_html", "iat_jurisprudencia_html", "reconocimiento_html")

# Palabras clave del tema IAT. El motor solo propone normas/providencias que
# traten del aprovechamiento de residuos y los recicladores de oficio. Son
# palabras de materia (no nombres de entidad) para evitar que todo el dominio
# de un portal coincida por su nombre.
PALABRAS_IAT = (
    "reciclador", "recicladores", "reciclaje", "reciclable", "aprovechamiento",
    "residuo", "pgirs", "ruor", "incentivo al aprovechamiento", "relleno sanitario",
    "disposicion final", "economia circular", "censo de recicladores",
    "organizacion de recicladores", "organizaciones de recicladores",
    "servicio de aprovechamiento", "prestador de aprovechamiento",
    "gestor de aprovechamiento", "formalizacion de recicladores",
    "servicio de aseo", "aseo y aprovechamiento", "residuos solidos",
    "material reciclable", "recicladores de oficio",
)

_candado = threading.Lock()


def _normaliza(texto):
    texto = (texto or "").strip().lower()
    return "".join(c for c in unicodedata.normalize("NFD", texto)
                   if unicodedata.category(c) != "Mn")


def _terminos(texto):
    return [t for t in re.findall(r"[a-z0-9áéíóúñ]{4,}", _normaliza(texto))]


def _sin_tags(html_texto):
    texto = re.sub(r"(?is)<(script|style).*?</\1>", " ", html_texto or "")
    texto = re.sub(r"(?s)<[^>]+>", " ", texto)
    return re.sub(r"\s+", " ", _html.unescape(texto)).strip()


def _huella(texto):
    return hashlib.sha1((texto or "").encode("utf-8", "ignore")).hexdigest()


def _fetch(url):
    r = requests.get(url, headers=UA, timeout=TIEMPO_LIMITE, verify=False)
    return r.status_code, r.text


def _absolutizar(base, href):
    href = (href or "").strip()
    if href.startswith(("http://", "https://")):
        return href
    if href.startswith("//"):
        return "https:" + href
    if href.startswith("/"):
        raiz = re.match(r"https?://[^/]+", base)
        return (raiz.group(0) if raiz else base.rstrip("/")) + href
    return base.rstrip("/") + "/" + href


def _categoria(titulo):
    t = _normaliza(titulo)
    for clave, etiqueta in (("sentencia", "Sentencia"), ("decreto", "Decreto"),
                            ("resolucion", "Resolución"), ("acuerdo", "Acuerdo"),
                            ("circular", "Circular"), ("ley", "Ley"),
                            ("concepto", "Concepto"), ("auto ", "Auto")):
        if clave in t:
            return etiqueta
    return ""


def _anio(texto):
    m = re.search(r"\b(19|20)\d{2}\b", texto or "")
    return m.group(0) if m else ""


def _es_iat(texto):
    n = _normaliza(texto)
    return any(p in n for p in PALABRAS_IAT)


RE_NORMA = re.compile(r"(?i)\b(ley|decreto|resoluci[oó]n|acuerdo|sentencia|auto|"
                      r"circular|concepto|ordenanza)\b")
RE_NUM_ANIO = re.compile(r"\b\d{1,4}\b[^\d]{0,40}\b(19|20)\d{2}\b")


def _parece_norma(texto):
    """¿El texto parece el título de una norma o providencia?"""
    return bool(RE_NORMA.search(texto) or RE_NUM_ANIO.search(texto))


def _candidatos(html_texto, base_url):
    """Extrae títulos de normas/providencias DEL TEMA IAT de una página."""
    vistos = set()
    salida = []
    for m in re.finditer(r"(?is)<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", html_texto or ""):
        href, inner = m.group(1), _sin_tags(m.group(2))
        href = _absolutizar(base_url, href)
        inner = inner.strip()
        if len(inner) < 8 or len(inner) > 220:
            continue
        # Debe tratar del IAT y parecer una norma/providencia (no una etiqueta
        # de menú como "Aprovechamiento" o "Disposición final").
        if not _es_iat(inner) or not _parece_norma(inner):
            continue
        if href in vistos:
            continue
        vistos.add(href)
        salida.append({
            "titulo": re.sub(r"\s+", " ", inner)[:200],
            "url": href,
            "categoria": _categoria(inner),
            "fecha": _anio(inner),
        })
        if len(salida) >= MAX_CANDIDATOS:
            break
    return salida


def revisar_fuente(fid, forzar=False):
    """Revisa una fuente. Devuelve dict con el resultado de la revisión."""
    fuente = next((f for f in db.motor_fuentes_lista() if f["id"] == int(fid)), None)
    if not fuente:
        return {"ok": False, "error": "Fuente no encontrada"}
    res = {"ok": True, "fuente": fuente["nombre"], "cambio": False,
           "candidatos": 0, "nuevos": 0, "error": ""}
    try:
        codigo, texto = _fetch(fuente["url"])
    except Exception as e:
        db.motor_fuente_actualizar(fid, {"ultima_revision": db._ahora(),
                                         "ultimo_error": "%s: %s" % (type(e).__name__, str(e)[:200])})
        res["ok"] = False
        res["error"] = str(e)[:200]
        return res

    if codigo >= 400:
        db.motor_fuente_actualizar(fid, {"ultima_revision": db._ahora(),
                                         "ultimo_error": "HTTP %s" % codigo})
        res["ok"] = False
        res["error"] = "HTTP %s" % codigo
        return res

    primera = not fuente["huella"]
    huella = _huella(texto)
    cambio = (not primera) and huella != fuente["huella"]
    if forzar or cambio or primera:
        candidatos = _candidatos(texto, fuente["url"])
        res["candidatos"] = len(candidatos)
        for c in candidatos:
            nuevo = db.motor_norma_crear({
                "titulo": c["titulo"], "tipo": fuente["tipo"],
                "categoria": c["categoria"], "fecha": c["fecha"],
                "area": fuente["area"], "url": c["url"],
                "fuente_id": fuente["id"], "origen": "motor", "estado": "pendiente",
            })
            if nuevo:
                res["nuevos"] += 1
        res["cambio"] = cambio

    campos = {"huella": huella, "ultima_revision": db._ahora(), "ultimo_error": ""}
    if cambio:
        campos["ultimo_cambio"] = db._ahora()
        campos["novedades"] = int(fuente["novedades"] or 0) + res["nuevos"]
    db.motor_fuente_actualizar(fid, campos)
    return res


def revisar_todas(disparador="manual", forzar=False):
    """Revisa todas las fuentes activas. Evita ejecuciones simultáneas."""
    if not _candado.acquire(blocking=False):
        return {"ok": False, "error": "Ya hay una actualización en curso"}
    try:
        resumen = {"ok": True, "disparador": disparador, "revisadas": 0,
                   "cambios": 0, "nuevos": 0, "errores": []}
        for f in db.motor_fuentes_lista(solo_activas=True):
            r = revisar_fuente(f["id"], forzar=forzar)
            resumen["revisadas"] += 1
            if not r.get("ok"):
                resumen["errores"].append({"fuente": f["nombre"], "error": r.get("error", "")})
                continue
            if r.get("cambio"):
                resumen["cambios"] += 1
            resumen["nuevos"] += r.get("nuevos", 0)
        return resumen
    finally:
        _candado.release()


# --------------------------------------------------------------------------- #
# Búsqueda                                                                     #
# --------------------------------------------------------------------------- #
def _buscar_catalogo(q, limite):
    terminos = _terminos(q)
    if not terminos:
        return []
    condicion = " OR ".join(
        ["(titulo LIKE ? OR resumen LIKE ? OR numero LIKE ? OR area LIKE ? OR emisor LIKE ?)"
         for _ in terminos])
    params = []
    for t in terminos:
        like = "%" + t + "%"
        params.extend([like, like, like, like, like])
    filas = db.consultar(
        "SELECT * FROM motor_normas WHERE estado <> 'descartada' AND (%s) "
        "ORDER BY (estado='aprobada') DESC, id DESC LIMIT ?" % condicion,
        tuple(params) + (int(limite),))
    return [{
        "origen": "catálogo", "tipo": f["tipo"], "titulo": f["titulo"],
        "detalle": f.get("resumen") or (f.get("categoria") or "") + " " + (f.get("fecha") or ""),
        "url": f.get("url") or "", "estado": f.get("estado", ""), "id": f["id"],
    } for f in filas]


def _buscar_base(q, limite):
    terminos = _terminos(q)
    if not terminos:
        return []
    contenido = db.contenido_todos()
    resultados = []
    for clave, valor in contenido.items():
        if clave not in CLAVES_BASE:
            continue
        texto = _sin_tags(valor)
        if not texto:
            continue
        for bloque in re.split(r"(?<=[.;])\s+", texto):
            nb = _normaliza(bloque)
            coincidencias = sum(1 for t in terminos if t in nb)
            if coincidencias >= max(1, len(terminos) // 2):
                resultados.append({
                    "origen": "base jurídica IAT", "tipo": "sección",
                    "titulo": clave.replace("_html", "").replace("_", " "),
                    "detalle": bloque.strip()[:400], "url": "", "estado": "", "id": None,
                })
                break
        if len(resultados) >= limite:
            break
    return resultados


def buscar(q, limite=30):
    """Búsqueda integrada del tema IAT: catálogo + base jurídica del IAT."""
    q = (q or "").strip()
    if not q:
        return {"consulta": "", "resultados": [], "total": 0}
    resultados = []
    resultados += _buscar_catalogo(q, limite)
    resultados += _buscar_base(q, limite)
    return {"consulta": q, "resultados": resultados[:limite], "total": len(resultados)}


# --------------------------------------------------------------------------- #
# Siembra del catálogo a partir de la base jurídica del IAT                    #
# --------------------------------------------------------------------------- #
def extraer_de_base():
    """Extrae normas y providencias del IAT desde las secciones de la base."""
    contenido = db.contenido_todos()
    encontrados = []

    for clave in ("iat_marco_normativo_html", "reconocimiento_html"):
        html_ = contenido.get(clave) or ""
        for m in re.finditer(r"(?is)<(?:b|strong)>(.*?)</(?:b|strong)>", html_):
            t = _sin_tags(m.group(1)).strip()
            if 5 <= len(t) <= 150 and _parece_norma(t):
                encontrados.append((re.sub(r"\s+", " ", t), "norma"))

    html_j = contenido.get("iat_jurisprudencia_html") or ""
    for m in re.finditer(r'(?is)<span class="tl-fecha">(.*?)</span>', html_j):
        t = _sin_tags(m.group(1)).strip()
        if not t:
            continue
        t = re.sub(r"\s*/\s*", " de ", t)
        if re.match(r"(?i)^(t|c|su)-\d", t):
            t = "Sentencia " + t
        encontrados.append((re.sub(r"\s+", " ", t), "jurisprudencia"))
    for m in re.finditer(r"(?is)<b>(Sentencia[^<]{2,120}?\d{4}[^<]{0,20})</b>", html_j):
        t = _sin_tags(m.group(1)).strip()
        if len(t) >= 8:
            encontrados.append((re.sub(r"\s+", " ", t), "jurisprudencia"))

    # Deduplica por título conservando el orden.
    vistos, titulos = set(), []
    for titulo, tipo in encontrados:
        k = _normaliza(titulo)
        if k in vistos:
            continue
        vistos.add(k)
        titulos.append((titulo, tipo))
    return titulos


def sembrar_desde_base():
    """Carga en el catálogo las normas/providencias ya citadas en la base IAT."""
    nuevos = 0
    for titulo, tipo in extraer_de_base():
        if db.motor_norma_existe_titulo(titulo):
            continue
        nuevo = db.motor_norma_crear({
            "titulo": titulo, "tipo": tipo, "categoria": _categoria(titulo),
            "fecha": _anio(titulo), "area": "IAT", "origen": "base",
            "estado": "aprobada",
        })
        if nuevo:
            nuevos += 1
    return nuevos


# --------------------------------------------------------------------------- #
# Actualización automática                                                     #
# --------------------------------------------------------------------------- #
_motor_hilo = None
MOTOR_AUTO = os.environ.get("MOTOR_NORMAS_AUTO", "1") != "0"
MOTOR_HORAS = float(os.environ.get("MOTOR_NORMAS_HORAS", "24") or 24)
MOTOR_ESPERA = float(os.environ.get("MOTOR_NORMAS_ESPERA", "600") or 600)


def _bucle():
    time.sleep(MOTOR_ESPERA)
    while True:
        try:
            revisar_todas(disparador="auto")
        except Exception:
            pass
        time.sleep(max(1, MOTOR_HORAS) * 3600)


def arrancar():
    """Enciende el hilo de actualización automática (una vez por proceso)."""
    global _motor_hilo
    if not MOTOR_AUTO or _motor_hilo is not None:
        return False
    if os.environ.get("WERKZEUG_RUN_MAIN") == "false":
        return False                          # proceso padre del reloader
    _motor_hilo = threading.Thread(target=_bucle, name="motor-normativo", daemon=True)
    _motor_hilo.start()
    return True