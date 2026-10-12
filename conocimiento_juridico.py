# -*- coding: utf-8 -*-
"""Biblioteca juridica del asistente Jarvis: texto oficial de normas colombianas.

El modulo descarga el texto vigente de las normas desde portales oficiales
(principalmente el SISJUR de la Secretaria Juridica Distrital de Bogota), lo
normaliza a texto plano, lo separa por articulos y lo guarda en cache con la
fecha de consulta. Consultar un articulo concreto es local y casi instantaneo;
la descarga solo ocurre cuando la cache vence.

Garantias de diseño, en orden de importancia:

1. Nunca se presenta texto sin verificar. Cada entrada del registro se valida
   contra el titulo real del documento descargado antes de usarse (ver
   `verificar_registro`). Esto evita colisiones como "Ley 23 de 1991": el
   numero aparece en la ley del Codigo de Policia, mientras que el Codigo
   Sustantivo del Trabajo se expide por el Decreto 2663 de 1950.
2. La verificacion TLS nunca se desactiva. Si el almacen de certificados del
   sistema esta mas actualizado que certifi, se usa `truststore`; si no esta
   disponible, se sigue con certifi.
3. Solo se consultan dominios de una lista blanca, siempre por HTTPS.
4. Ante cualquier fallo se devuelve una lista vacia. El chat nunca se cae
   por culpa de la red.
5. Todo fragmento devuelto lleva su URL y la fecha en que se consulto, para
   que un abogado pueda cotejarlo.

Nota sobre vigencia: las fuentes oficiales se actualizan (por ejemplo el
Decreto 2663 de 1950 ya trae el artículo 3 modificado por la Ley 2466 de
2025). Por eso la cache caduca y el texto se vuelve a bajar.
"""
import os
import re
import json
import time
import hashlib
import threading
import datetime

try:  # truststore usa el almacen de certificados del sistema (mas completo)
    import truststore
    truststore.inject_into_ssl()
except Exception:  # pragma: no cover - el paquete es opcional
    truststore = None

import requests

# --------------------------------------------------------------------------- #
# Configuracion                                                              #
# --------------------------------------------------------------------------- #

TIEMPO_CONEXION = 8
TIEMPO_LECTURA = 20
MAX_BYTES = 6 * 1024 * 1024
DIAS_CACHE = 30
MAX_FRAGMENTOS = 6
MAX_CHARS_CONTEXTO = 7000

BASE_SISJUR = "https://www.alcaldiabogota.gov.co/sisjur/normas/Norma1.jsp?i=%s"
DOMINIOS_OK = ("www.alcaldiabogota.gov.co", "alcaldiabogata.gov.co")

RAIZ = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(RAIZ, "cache", "normas")

# Palabras que stop filtered. Cortas y sin valor juridico propio.
VACIAS = set("""de la el los las un una unos unas y o u en del al por con para que
se su sus lo es son ser esta este estos estas como mas pero sin sobre entre
cuando donde quien cual cuales me mi te tu tuya su tiene tengo hay ha hacer
pode puedo puedo hacer casoSituacion entonces pues ya le les nos nuestro""".split())

_lock = threading.Lock()


# --------------------------------------------------------------------------- #
# Registro de normas
# --------------------
# Cada entrada se valida en dos pasos antes de usarse:
#   exige  -> palabras que deben salir en el encabezado del documento oficial
#   pistas -> huellas del cuerpo; al menos dos deben aparecer en el texto
#
# El control existe porque hay numeros de norma repetidos o mal indexados por
# los buscadores: "Ley 23 de 1991" es el Codigo de Policia, no el Codigo
# Sustantivo del Trabajo (que se expide por el Decreto 2663 de 1950). Sin
# verificar, el asistente citaría la norma equivocada con total seguridad, que
# es el peor fallo posible aquí.
#
#   claves  palabras por las que suele preguntar el usuario
#   exige   identidad del encabezado
#   pistas  identidad del cuerpo

NORMAS = [
    {
        "clave": "CST",
        "titulo": "Codigo Sustantivo del Trabajo (Decreto 2663 de 1950)",
        "id": "33104",
        "exige": ["2663", "1950", "Nivel Nacional"],
        "pistas": ["SUSTANTIVO DEL TRABAJO", "ARTICULO 206", "ARTICULO 189"],
        "claves": ["despido", "despedir", "liquidacion", "salario", "salarios",
                   "contrato", "laboral", "trabajador", "empleador", "horas",
                   "jornada", "vacaciones", "cesantia", "intereses", "indemnizacion",
                   "periodo de prueba", "teletrabajo", "sindicato",
                   "paro", "huelga", "acoso laboral", "embargo", "prestacion",
                   "auxilio", "pension", "ARL", "riesgo laboral", "recibo de pago",
                   "comisiones", "trabajo no remunerado"],
    },
    {
        "clave": "CPT",
        "titulo": "Codigo Procesal del Trabajo (Decreto 2158 de 1948)",
        "id": "5259",
        "exige": ["2158", "1948"],
        "pistas": ["PROCEDIMIENTOS", "PROCESO DEL TRABAJO", "Artículo 2"],
        "claves": ["conciliacion", "demanda laboral", "tribunal", "ejecutivo",
                   "sentencia", "proceso laboral", "prueba laboral"],
    },
    {
        "clave": "CPACA",
        "titulo": "Codigo de Procedimiento Administrativo y de lo Contencioso Administrativo (Ley 1437 de 2011)",
        "id": "41249",
        "exige": ["1437", "2011"],
        "pistas": ["PROCEDIMIENTO ADMINISTRATIVO", "Artículo 76", "ACTOR"],
        "claves": ["entidad", "entidades", "administrativa", "administrativo",
                   "servicio publico", "contratacion", "licitacion", "resolucion",
                   "acto administrativo", "sancion", "concurso", "multa",
                   "tutela", "reclamo", "derecho de peticion", "reclamacion",
                   "expediente", "notificacion", "silencio", "nulidad", "recurso"],
    },
    {
        "clave": "CPACA_2021",
        "titulo": "Ley 2080 de 2021 (reformas al CPACA)",
        "id": "105225",
        "exige": ["2080", "2021"],
        "pistas": ["CPACA", "reforma", "Artículo 1"],
        "claves": ["control automatico", "congestion", "reforma cpaca"],
    },
    {
        "clave": "CGP",
        "titulo": "Codigo General del Proceso (Ley 1564 de 2012)",
        "id": "48425",
        "exige": ["1564", "2012"],
        "pistas": ["GENERAL DEL PROCESO", "Artículo 125", "Artículo 1"],
        "claves": ["civil", "ejecucion", "proceso civil", "prueba", "sentencia",
                   "recurso de apelacion", "reposicion", "jurisdiccion", "embargo",
                   "perjuicios", "liquidacion", "sujeto procesal", "insolvencia",
                   "concurso", "acreedor", "deudor", "liquidacion patrimonial",
                   "persona natural no comerciante"],
    },
    {
        "clave": "CIVIL",
        "titulo": "Codigo Civil (Ley 57 de 1887)",
        "id": "120723",
        "exige": ["57", "1887"],
        "pistas": ["CÓDIGO CIVIL", "Código Civil", "adopción de Códigos"],
        "claves": ["contrato", "arrendamiento", "compraventa", "obligacion",
                   "deuda", "clausula", "penalidad", "intereses moratorios",
                   "prescripcion", "reivindicacion", "posesion", "responsabilidad",
                   "inmueble", "herencia", "testamento", "servidumbre", "locacion"],
    },
    {
        "clave": "COMERCIO",
        "titulo": "Codigo de Comercio (Decreto 410 de 1971)",
        "id": "41102",
        "exige": ["410", "1971"],
        "pistas": ["APLICABILIDAD DE LA LEY COMERCIAL", "comerciantes", "CAPÍTULO V"],
        "claves": ["sociedad", "sociedades", "SAS", "Ltda", "limitada",
                   "accionista", "socio", "comerciante", "mercantil", "titulo valor",
                   "factura", "proveedor", "cliente", "empresa", "estatuto",
                   "registro mercantil", "camara de comercio", "sancion mercantil",
                   "inhabilitacion", "obediencia",
                   "accion de","nulidad",
                   "representacion", "conflito de interes"],
    },
    {
        "clave": "LEY1581",
        "titulo": "Ley 1581 de 2012 (proteccion de datos personales)",
        "id": "49981",
        "exige": ["1581", "2012"],
        "pistas": ["datos personales", "habeas data", "tratamiento"],
        "claves": ["datos personales", "dato personal", "privacidad", "habeas data",
                   "tratamiento de datos", "base de datos", "superintendencia de datos",
                   "titular", "responsable del tratamiento", "filtracion",
                   "confidencialidad", "informacion personal"],
    },
    {
        "clave": "LEY820",
        "titulo": "Ley 820 de 2003 (regimen de arrendamiento de vivienda urbana)",
        "id": "8738",
        "exige": ["820", "2003"],
        "pistas": ["vivienda urbana", "arrendamiento", "locador"],
        "claves": ["arrendamiento", "arrendador", "arrendataria", "inquilino",
                   "canon", "deposito", "garantia", "vivienda", "locacion",
                   "contrato de arrendamiento", "desahucio", "ejecucion"],
    },
    {
        "clave": "LEY1116",
        "titulo": "Ley 1116 de 2006 (regimen de insolvencia empresarial)",
        "id": "22657",
        "exige": ["1116", "2006"],
        "pistas": ["reorganización", "liquidación", "créditos"],
        "claves": ["liquidacion", "reorganizacion", "quiebra", "liquidacion judicial",
                   "credores", "acreedores", "insolvencia", "insolvente",
                   "concurso", "concurso mercantil", "reestructuracion",
                   "acuerdo de reorganizacion", "adjudicacion", "promotor",
                   "persona natural", "persona juridica", "empresa", "empresarial",
                   "proceso de insolvencia", "liquidacion patrimonial",
                   "insolvencia de persona natural", "deudor no comerciante"],
    },
    {
        "clave": "LEY2466",
        "titulo": "Ley 2466 de 2025 (reforma laboral)",
        "id": "181933",
        "exige": ["2466", "2025"],
        "pistas": ["reforma", "Código Sustantivo del Trabajo", "Artículo 1"],
        "claves": ["reforma laboral", "nuevo regimen", "ley 2466",
                   "recargo nocturno", "jornada maxima"],
    },
]


def _normalizado(s):
    """Minusculas sin tildes ni signos, para comparar titulos."""
    s = str(s or "").lower()
    s = re.sub(r"[áàä]", "a", s)
    s = re.sub(r"[éèë]", "e", s)
    s = re.sub(r"[íìï]", "i", s)
    s = re.sub(r"[óòö]", "o", s)
    s = re.sub(r"[úùü]", "u", s)
    s = re.sub(r"[ç]", "c", s)
    return re.sub(r"[^a-z0-9 ]+", " ", s)


def _url_de(entrada):
    return BASE_SISJUR % str(entrada["id"])


# --------------------------------------------------------------------------- #
# Descarga y cache                                                            #
# --------------------------------------------------------------------------- #

def _cache_de(entrada):
    return os.path.join(CACHE, "%s.json" % entrada["clave"])


def _huella(entrada):
    """Huella de la identidad esperada de una norma.

    Se guarda dentro del archivo de cache. Si alguien corrige el id, el titulo
    o las pistas de verificacion de una entrada, la cache vieja queda
    descartada en vez de seguir sirviendo el documento equivocado.
    """
    crudo = "|".join([
        str(entrada.get("clave")),
        str(entrada.get("id")),
        str(entrada.get("titulo")),
        ",".join(entrada.get("exige") or ()),
        ",".join(entrada.get("pistas") or ()),
    ])
    return hashlib.sha1(crudo.encode("utf-8")).hexdigest()


def _descargar(url):
    """Descarga una URL autorizada. Devuelve bytes o None."""
    if not url.lower().startswith("https://"):
        return None
    host = url.split("/")[2].lower()
    if not any(host == d or host.endswith("." + d) for d in DOMINIOS_OK):
        return None
    try:
        resp = requests.get(
            url,
            timeout=(TIEMPO_CONEXION, TIEMPO_LECTURA),
            stream=True,
            headers={
                # Identificarse honestamente evita bloqueos y facilita auditar
                # el trafico desde el portal oficial.
                "User-Agent": "DerechosOnBot/1.0 (+consulta normativa; contacto: contacto@derechoson.co)",
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "es-CO,es;q=0.9",
            },
        )
        if resp.status_code != 200:
            return None
        crudo = bytearray()
        for trozo in resp.iter_content(16384):
            crudo.extend(trozo)
            if len(crudo) > MAX_BYTES:
                return None
        return bytes(crudo)
    except Exception:
        return None


def _a_texto(crudo):
    """Convierte los bytes de una pagina a texto plano legible."""
    if not crudo:
        return ""
    for codificacion in ("utf-8", "latin-1"):
        try:
            html_ = crudo.decode(codificacion)
            break
        except UnicodeDecodeError:
            continue
    else:
        return ""
    # Si la pagina declara otra codificacion y la lectura falla, no insistimos.
    html_ = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html_)
    html_ = re.sub(r"(?i)<br\s*/?>", "\n", html_)
    html_ = re.sub(r"(?i)</(p|div|tr|h[1-6]|li)>", "\n", html_)
    html_ = re.sub(r"(?s)<!--.*?-->", " ", html_)
    html_ = re.sub(r"(?s)<[^>]+>", " ", html_)

    import html as html_mod
    texto = html_mod.unescape(html_)
    texto = texto.replace("\xa0", " ")
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r"\n[ \t]*\n+", "\n", texto)
    return texto.strip()


def cargar_norma(entrada, forzar=False):
    """Devuelve {titulo, articulos, url, fecha} de una norma, usando cache.

    Nunca lanza excepcion: si algo falla devuelve None y el chat sigue
    funcionando con lo que ya tenia. La cache se acepta solo si esta vigente y
    su huella coincide con la identidad esperada de la entrada.
    """
    ruta = _cache_de(entrada)
    huella = _huella(entrada)

    if not forzar:
        try:
            if (time.time() - os.path.getmtime(ruta)) < DIAS_CACHE * 86400:
                with open(ruta, "r", encoding="utf-8") as fh:
                    guardado = json.load(fh)
                if guardado.get("articulos") and guardado.get("huella") == huella:
                    return guardado
        except Exception:
            pass

    # Una sola descarga por clave a la vez: varios visitantes pueden preguntar
    # lo mismo al mismo tiempo y no deben pisarse el archivo temporal.
    with _lock:
        try:
            if not forzar and (time.time() - os.path.getmtime(ruta)) < DIAS_CACHE * 86400:
                with open(ruta, "r", encoding="utf-8") as fh:
                    guardado = json.load(fh)
                if guardado.get("articulos") and guardado.get("huella") == huella:
                    return guardado
        except Exception:
            pass

        url = _url_de(entrada)
        texto = _a_texto(_descargar(url))
        if not texto:
            return None

        # Verificacion de identidad en dos pasos: encabezado (exige) y huella del
        # cuerpo (pistas). Si el documento oficial no es el que creiamos estar
        # bajando, se descarta antes de tocar la cache.
        if not _coincide(texto[:2500], entrada["exige"]):
            return None
        pistas = entrada.get("pistas") or []
        if pistas and sum(1 for p in pistas
                          if _normalizado(p) in _normalizado(texto)) < 2:
            return None

        articulos = _separar_articulos(texto)
        if not articulos:
            return None

        datos = {
            "clave": entrada["clave"],
            "titulo": entrada["titulo"],
            "url": url,
            "fecha": datetime.date.today().isoformat(),
            "huella": huella,
            "articulos": articulos,
        }
        try:
            os.makedirs(CACHE, exist_ok=True)
            tmp = "%s.%d.tmp" % (ruta, os.getpid())
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(datos, fh, ensure_ascii=False)
            os.replace(tmp, ruta)
        except Exception:
            pass
        return datos


def _coincide(texto, exigidas):
    """True si todas las palabras exigidas aparecen en el texto del titulo."""
    bajo = _normalizado(texto)
    for palabra in exigidas:
        if _normalizado(palabra) not in bajo:
            return False
    return True


# --------------------------------------------------------------------------- #
# Separacion en articulos                                                     #
# --------------------------------------------------------------------------- #

RE_ARTICULO = re.compile(
    r"(?:^|\n|\s)ART[IÍ]CULO\s+([0-9]+[A-Z]?(?:\.[0-9]+)*)"
    r"(?:\s*(?:[-–]\s*)?(?:[A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ\s,.\-()]{2,60}?))?\s*[.:]",
    re.IGNORECASE)


def _separar_articulos(texto):
    """Parte el texto oficial en articulos indexables."""
    marcas = list(RE_ARTICULO.finditer(texto))
    if not marcas:
        return []
    salida = []
    for k, m in enumerate(marcas):
        fin = marcas[k + 1].start() if k + 1 < len(marcas) else len(texto)
        cuerpo = texto[m.start():fin].strip()
        cuerpo = re.sub(r"\s+", " ", cuerpo)
        if len(cuerpo) < 40:
            continue
        salida.append({
            "ref": "Art. " + m.group(1),
            "texto": cuerpo[:2600],
        })
        if len(salida) >= 900:
            break
    return salida


# --------------------------------------------------------------------------- #
# Busqueda                                                                    #
# --------------------------------------------------------------------------- #

def _terminos(texto):
    palabras = _normalizado(texto).split()
    return {p for p in palabras if len(p) > 2 and p not in VACIAS}


def _normas_candidatas(consulta):
    """Puntua las normas del registro segun el tema de la consulta."""
    bajo = _normalizado(consulta)
    puntuadas = []
    for entrada in NORMAS:
        puntos = 0
        for clave in entrada.get("claves", ()):
            if _normalizado(clave) in bajo:
                puntos += 3 if " " in clave else 2
        if puntos:
            puntuadas.append((puntos, entrada))
    puntuadas.sort(key=lambda x: -x[0])
    return [e for _p, e in puntuadas[:4]]


MAX_ARTICULOS_POR_NORMA = 3


def fragmentos(consulta, limite=MAX_FRAGMENTOS, forzar=False):
    """Devuelve los articulos mas relevantes para una consulta del visitante.

    Cada elemento trae: ref, texto, norma, url, fecha y score. Es la funcion
    que usa el chat para fundamentar su respuesta.
    """
    if not str(consulta or "").strip():
        return []

    consulta_n = _normalizado(consulta)
    consulta_t = _terminos(consulta)
    numeros = set(re.findall(r"\b(?:art|articulo|articulos)\s*(\d+)", consulta_n))
    encontrados = []

    for entrada in _normas_candidatas(consulta):
        datos = cargar_norma(entrada, forzar=forzar)
        if not datos:
            continue
        nombre_n = _normalizado(datos["titulo"])

        # El articulo debe compartir palabras con la pregunta. Un articulo que
        # no comparte nada no aporta y solo genera ruido para el modelo.
        de_esta_norma = []
        for art in datos["articulos"]:
            comunes = consulta_t & _terminos(art["texto"])
            if not comunes:
                continue
            score = len(comunes) * 2
            # Si el usuario menciona el numero de articulo, es un golpe directo.
            if art["ref"].split()[-1] in numeros:
                score += 25
            # Bonificacion si el articulo esta en el titulo de la norma.
            score += 2 if entrada["clave"].split("_")[0].lower() in nombre_n else 0
            if score <= 0:
                continue
            de_esta_norma.append((score, art))

        # Varios articulos de la misma norma: una pregunta tipica ("preaviso y
        # cesantia") necesita mas de un articulo del Codigo del Trabajo.
        de_esta_norma.sort(key=lambda x: -x[0])
        for score, art in de_esta_norma[:MAX_ARTICULOS_POR_NORMA]:
            encontrados.append({
                "norma": datos["titulo"],
                "clave": datos["clave"],
                "ref": art["ref"],
                "texto": art["texto"],
                "url": datos["url"],
                "fecha": datos["fecha"],
                "score": score,
            })

    # El texto oficial repite articulos (cada reforma vuelve a copiar el
    # articulo anterior). Sin deduplicar, la misma cita aparece dos veces y el
    # modelo la presenta como si fueran dos normas distintas.
    unicos = {}
    for frag in encontrados:
        llave = (frag["clave"], frag["ref"])
        actual = unicos.get(llave)
        if actual is None or frag["score"] > actual["score"]:
            unicos[llave] = frag

    # Reparto por turnos: se alterna entre normas para que una sola no ocupe
    # todos los cupos y el usuario reciba legislacion de varios campos.
    grupos = {}
    for frag in unicos.values():
        grupos.setdefault(frag["clave"], []).append(frag)
    for lista in grupos.values():
        lista.sort(key=lambda x: -x["score"])
    # El turno lo lleva la norma mas relevante, no el orden del diccionario.
    grupos = dict(sorted(grupos.items(),
                         key=lambda par: -par[1][0]["score"]))

    orden = []
    while grupos:
        for clave in list(grupos):
            lista = grupos[clave]
            orden.append(lista.pop(0))
            if not lista:
                del grupos[clave]
    return orden[:limite]


def redactar(frags, max_chars=MAX_CHARS_CONTEXTO):
    """Arma el bloque de texto oficial a partir de fragmentos ya recuperados.

    Reparte `max_chars` entre los fragmentos por relevancia (score) en vez de
    dejar que el primero agote el presupuesto: para una respuesta util casi
    siempre conviene citar varios articulos aunque sean recortados.
    """
    if not frags:
        return ""

    encabezado = ("TEXTO OFICIAL VERIFICADO DE LA NORMATIVA COLOMBIANA. "
                  "Citalo textualmente y no lo reescribas:\n\n")
    presupuesto = max(200, max_chars - len(encabezado))
    # Cada bloque lleva cabecera de metadatos (clave, ref, url, fecha).
    cuota_texto = max(300, presupuesto // len(frags) - 320)

    partes = []
    usados = 0
    for frag in frags:
        bloque = ("[%s · %s] (fuente oficial: %s, consultado el %s)\n%s"
                  % (frag["clave"], frag["ref"], frag["url"], frag["fecha"],
                     frag["texto"][:cuota_texto]))
        if usados + len(bloque) > presupuesto:
            break
        partes.append(bloque)
        usados += len(bloque)

    if not partes:
        return ""
    return encabezado + "\n\n".join(partes)


def contexto(consulta, limite=MAX_FRAGMENTOS, max_chars=MAX_CHARS_CONTEXTO):
    """Texto listo para pegarse al prompt del asistente."""
    return redactar(fragmentos(consulta, limite=limite), max_chars=max_chars)


def urls_de(consulta, limite=MAX_FRAGMENTOS, frags=None):
    """URLs de las normas efectivamente consultadas, para mostrarlas al usuario."""
    if frags is None:
        frags = fragmentos(consulta, limite=limite)
    salida = []
    vistos = set()
    for frag in frags:
        if frag["url"] in vistos:
            continue
        vistos.add(frag["url"])
        salida.append({
            "t": "%s · %s" % (frag["clave"], frag["ref"]),
            "d": frag["norma"],
            "url": frag["url"],
            "fecha": frag["fecha"],
        })
    return salida


def verificar_registro(refrescar=False):
    """Comprueba que cada entrada del registro apunte al documento correcto.

    Pensado para correr a mano antes de publicar cambios en el registro.
    """
    informe = []
    for entrada in NORMAS:
        datos = cargar_norma(entrada, forzar=refrescar)
        if not datos:
            informe.append({"clave": entrada["clave"], "ok": False,
                            "detalle": "no se pudo descargar o no coincide el titulo"})
            continue
        informe.append({
            "clave": entrada["clave"],
            "ok": True,
            "detalle": "%s articulos · %s" % (len(datos["articulos"]), datos["url"]),
        })
    return informe


def limpiar_cache():
    """Borra la cache local de normas."""
    try:
        for nombre in os.listdir(CACHE):
            os.remove(os.path.join(CACHE, nombre))
        return True
    except Exception:
        return False