# -*- coding: utf-8 -*-
"""Marketing digital: auditoria de posicionamiento y viabilidad en redes.

El modulo trabaja en dos niveles:

1. Diagnostico local (gratis, sin depender de terceros): lee el HTML de la
   pagina y revisa los factores On-Page que Google, Bing y DuckDuckGo tienen
   en cuenta, mas la viabilidad de compartir el contenido en LinkedIn,
   Facebook, Instagram y X.
2. Plan paso a paso con IA: cuando hay clave configurada (IA_CLAVE en
   /etc/derechoson.env o en la tabla de contenido), el diagnostico se envia a
   Claude y se convierte en una hoja de ruta priorizada.

No usa bs4 ni lxml: todo se resuelve con html.parser de la libreria estandar
para no sumar dependencias al servidor.
"""
import ipaddress
import json
import re
import socket
import unicodedata
from html.parser import HTMLParser
from urllib.parse import urlparse, urljoin

import requests

TIMEOUT = 20
MAX_BYTES = 1500000
USER_AGENT = ("Mozilla/5.0 (compatible; DerechosOnAuditor/1.0; "
              "+http://localhost/admin/marketing)")

REDES = [
    {"id": "linkedin", "nombre": "LinkedIn", "tono": "profesional",
     "titulo": (40, 120), "resumen": (90, 400), "hashtags": (3, 6)},
    {"id": "facebook", "nombre": "Facebook", "tono": "cercano",
     "titulo": (30, 90), "resumen": (80, 350), "hashtags": (2, 5)},
    {"id": "instagram", "nombre": "Instagram", "tono": "visual",
     "titulo": (20, 90), "resumen": (120, 500), "hashtags": (6, 15)},
    {"id": "x", "nombre": "X", "tono": "breve",
     "titulo": (25, 70), "resumen": (80, 280), "hashtags": (1, 3)},
]

MOTORES = [
    {"id": "google", "nombre": "Google",
     "nota": "Es el motor que mas peso tiene. Usa el titulo, la meta description, "
             "los datos estructurados y las señales de experiencia para mostrar "
             "resultados enriquecidos."},
    {"id": "bing", "nombre": "Bing",
     "nota": "Alimenta ademas el indice de DuckDuckGo. Acepta los datos "
             "estructurados de Google y premia IndexNow para indexar rapido."},
    {"id": "duckduckgo", "nombre": "DuckDuckGo",
     "nota": "Toma sus resultados del indice de Bing, sin etiquetado propio: "
             "si estas bien en Bing, ya estas bien aqui."},
]

PESOS_TECNICOS = {
    "titulo": 14, "descripcion": 14, "canonical": 6, "h1": 12, "encabezados": 6,
    "lang": 4, "viewport": 8, "https": 8, "og": 8, "twitter": 4, "jsonld": 8,
    "alt": 5, "enlaces": 5, "palabras": 8, "slug": 4, "fecha": 4, "autor": 3,
    "imagen_og": 4, "sitemap": 6, "robots": 5, "velocidad": 4, "livianas": 3,
    "keyword": 8, "verificacion": 2,
}


class MarketingError(Exception):
    """Error legible para el administrador."""


# ----------------------------------------------------------------- utilidades
def _sin_acentos(texto):
    return "".join(c for c in unicodedata.normalize("NFD", str(texto or ""))
                   if unicodedata.category(c) != "Mn").lower()


def _palabras(texto):
    return re.findall(r"[A-Za-z\u00C0-\u024F]+", str(texto or ""))


def _etiqueta(puntaje):
    if puntaje >= 80:
        return "Bien posicionable"
    if puntaje >= 60:
        return "Mejorable"
    if puntaje >= 40:
        return "Debil"
    return "Critico"


def _viabilidad(puntaje):
    if puntaje >= 75:
        return "Alta"
    if puntaje >= 50:
        return "Media"
    return "Baja"


def _hallazgo(clave, titulo, estado, detalle, consejo, peso=None):
    return {"clave": clave, "titulo": titulo, "estado": estado,
            "detalle": detalle, "consejo": consejo,
            "peso": PESOS_TECNICOS.get(clave, 4) if peso is None else peso}


# ------------------------------------------------------------- descarga segura
def _ip_publica(host):
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        raise MarketingError("No se pudo resolver el dominio %s." % host)
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            continue
        if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
                or ip.is_multicast or ip.is_unspecified):
            raise MarketingError("Ese dominio apunta a una red interna. Por "
                                 "seguridad solo se analizan sitios publicos.")


def _validar_url(url):
    url = (url or "").strip()
    if not url:
        raise MarketingError("Escribe la direccion web que quieres analizar.")
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    datos = urlparse(url)
    if datos.scheme not in ("http", "https"):
        raise MarketingError("Solo se pueden analizar direcciones http o https.")
    if not datos.hostname:
        raise MarketingError("La direccion no es valida.")
    return url


def descargar(url, propio=False):
    """Descarga el HTML respetando un limite de tamaño y sin redes internas.

    `propio=True` se usa para las paginas del propio despacho (en desarrollo la
    URL es 127.0.0.1 y el bloqueo de redes internas no aplica).
    """
    url = _validar_url(url)
    if not propio:
        _ip_publica(urlparse(url).hostname)
    try:
        r = requests.get(url, timeout=TIMEOUT, stream=True, allow_redirects=True,
                         headers={"User-Agent": USER_AGENT,
                                  "Accept": "text/html,application/xhtml+xml"})
    except requests.RequestException as exc:
        raise MarketingError("No se pudo descargar la pagina (%s)." % exc)
    if r.status_code >= 400:
        raise MarketingError("El sitio respondio con codigo HTTP %s." % r.status_code)
    tipo = (r.headers.get("Content-Type") or "").lower()
    if tipo and "html" not in tipo and "xml" not in tipo:
        raise MarketingError("Esa direccion no devuelve una pagina HTML (%s)." % tipo)
    crudo = bytearray()
    for trozo in r.iter_content(65536):
        crudo.extend(trozo)
        if len(crudo) >= MAX_BYTES:
            break
    codificacion = r.encoding or "utf-8"
    html = bytes(crudo[:MAX_BYTES]).decode(codificacion, "replace")
    return {"url": r.url, "status": r.status_code, "html": html,
            "bytes": len(crudo), "truncado": len(crudo) >= MAX_BYTES}


def validar_url(url):
    """Completa el esquema si falta y descarta direcciones que no sean web."""
    return _validar_url(url)


def _consultar_ruta(url, ruta):
    """Revisa robots.txt o sitemap.xml de un sitio propio."""
    try:
        r = requests.get(urljoin(url, ruta), timeout=10,
                         headers={"User-Agent": USER_AGENT})
    except requests.RequestException:
        return None
    if r.status_code >= 400:
        return False
    return r.text


# ------------------------------------------------------------- lector de HTML
class _Lector(HTMLParser):
    def __init__(self):
        HTMLParser.__init__(self, convert_charrefs=True)
        self.titulo = []
        self.meta = {}
        self.canonical = ""
        self.html_lang = ""
        self.imagenes = []
        self.enlaces = []
        self.encabezados = []
        self.jsonld = []
        self.scripts = 0
        self.texto = []
        self._pila = []
        self._jsonld_bufer = None
        self._jsonld_tipo = None
        self._salto = None
        self._h_actual = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self._pila.append(tag)
        if tag == "html":
            self.html_lang = (a.get("lang") or "").strip()
        elif tag == "title":
            self._salto = "title"
        elif tag == "meta":
            clave = (a.get("name") or a.get("property") or a.get("itemprop") or "").strip().lower()
            if clave:
                self.meta.setdefault(clave, (a.get("content") or "").strip())
        elif tag == "link":
            rel = (a.get("rel") or "").lower()
            if "canonical" in rel and not self.canonical:
                self.canonical = (a.get("href") or "").strip()
        elif tag == "img":
            self.imagenes.append({"src": a.get("src") or "",
                                  "alt": (a.get("alt") or "").strip(),
                                  "loading": (a.get("loading") or "").strip().lower(),
                                  "formato": (a.get("src") or "").split(".")[-1].lower()})
        elif tag == "a":
            self.enlaces.append(a.get("href") or "")
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._h_actual = [int(tag[1]), []]
            self.encabezados.append(self._h_actual)
        elif tag == "script":
            self.scripts += 1
            tipo = (a.get("type") or "").lower()
            if "ld+json" in tipo:
                self._jsonld_bufer = []
                self._jsonld_tipo = a.get("type")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if self._pila:
            self._pila.pop()

    def handle_endtag(self, tag):
        if tag == "title":
            self._salto = None
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._h_actual = None
        elif tag == "script" and self._jsonld_bufer is not None:
            try:
                self.jsonld.append(json.loads("".join(self._jsonld_bufer)))
            except (ValueError, TypeError):
                self.jsonld.append({})
            self._jsonld_bufer = None
        while self._pila and self._pila[-1] != tag:
            self._pila.pop()
        if self._pila:
            self._pila.pop()

    def handle_data(self, datos):
        if self._jsonld_bufer is not None:
            self._jsonld_bufer.append(datos)
            return
        if self._salto == "title":
            self.titulo.append(datos)
            return
        if self._h_actual is not None:
            self._h_actual[1].append(datos)
            return
        if not (self._pila and self._pila[-1] in ("script", "style")):
            self.texto.append(datos)


def metricas(html, url=""):
    """Extrae las medidas On-Page que alimentan los informes."""
    lector = _Lector()
    try:
        lector.feed(html or "")
        lector.close()
    except Exception:
        pass
    titulo = re.sub(r"\s+", " ", "".join(lector.titulo)).strip()
    texto = re.sub(r"\s+", " ", " ".join(p for p in lector.texto if p and p.strip())).strip()
    encabezados = [(n, re.sub(r"\s+", " ", "".join(b)).strip()) for n, b in lector.encabezados]
    meta = lector.meta
    og = {k[3:]: v for k, v in meta.items() if k.startswith("og:")}
    tw = {k[8:]: v for k, v in meta.items() if k.startswith("twitter:")}
    tipos_jsonld = []
    for bloque in lector.jsonld:
        if isinstance(bloque, dict):
            tipo = bloque.get("@type")
            if isinstance(tipo, list):
                tipos_jsonld += [str(t) for t in tipo]
            elif tipo:
                tipos_jsonld.append(str(tipo))
        elif isinstance(bloque, list):
            for item in bloque:
                if isinstance(item, dict) and item.get("@type"):
                    tipos_jsonld.append(str(item.get("@type")))
    base = urlparse(url).netloc if url else ""
    internos = [e for e in lector.enlaces
                if e.startswith("/") or (base and e.startswith(base))]
    externos = [e for e in lector.enlaces
                if e.startswith("http") and base and base not in e]
    h1 = [t for n, t in encabezados if n == 1 and t]
    primer_parrafo = ""
    for frase in re.split(r"(?<=[.!?])\s+", texto):
        if len(_palabras(frase)) > 12:
            primer_parrafo = frase.strip()
            break
    return {
        "url": url,
        "titulo": titulo,
        "titulo_len": len(titulo),
        "descripcion": meta.get("description", ""),
        "descripcion_len": len(meta.get("description", "")),
        "canonical": lector.canonical,
        "lang": lector.html_lang,
        "viewport": meta.get("viewport", ""),
        "https": (urlparse(url).scheme == "https") if url else False,
        "og": og,
        "twitter": tw,
        "jsonld": tipos_jsonld,
        "imagenes": lector.imagenes,
        "imagenes_sin_alt": sum(1 for i in lector.imagenes if not i["alt"]),
        "imagenes_lazy": sum(1 for i in lector.imagenes if i["loading"] == "lazy"),
        "imagenes_webp": sum(1 for i in lector.imagenes
                             if i["formato"] in ("webp", "avif")),
        "enlaces_internos": len(internos),
        "enlaces_externos": len(externos),
        "encabezados": encabezados,
        "h1": h1,
        "h1_count": len(h1),
        "h2_count": sum(1 for n, _ in encabezados if n == 2),
        "palabras": len(_palabras(texto)),
        "primer_parrafo": primer_parrafo,
        "texto": texto,
        "scripts": lector.scripts,
        "bytes": len(html or ""),
        "fecha": (meta.get("article:published_time", "")
                  or _fecha_de_jsonld(lector.jsonld)),
        "autor": (meta.get("article:author", "") or _autor_de_jsonld(lector.jsonld)),
        "slug": urlparse(url).path.strip("/").split("/")[-1] if url else "",
        "msvalidate": bool(meta.get("msvalidate.01") or meta.get("bing:siteverification")),
    }


def _recorrer(bloque, clave):
    """Busca una clave dentro de un JSON-LD, sin importar el nivel."""
    if isinstance(bloque, dict):
        if clave in bloque and bloque[clave]:
            return bloque[clave]
        for valor in bloque.values():
            encontrado = _recorrer(valor, clave)
            if encontrado:
                return encontrado
    elif isinstance(bloque, list):
        for item in bloque:
            encontrado = _recorrer(item, clave)
            if encontrado:
                return encontrado
    return ""


def _fecha_de_jsonld(bloques):
    for bloque in bloques:
        valor = _recorrer(bloque, "datePublished")
        if valor:
            return str(valor)[:10]
    return ""


def _autor_de_jsonld(bloques):
    for bloque in bloques:
        valor = _recorrer(bloque, "author")
        if isinstance(valor, dict):
            return str(valor.get("name") or "")
        if valor:
            return str(valor)
    return ""


# ------------------------------------------------------ diagnostico On-Page
def revisar_tecnica(m, ctx):
    """Factores On-Page comunes a los tres buscadores."""
    h = []
    propio = ctx.get("propio", False)
    es_articulo = ctx.get("tipo") == "articulo"

    # Titulo
    if not m["titulo"]:
        h.append(_hallazgo("titulo", "Titulo de la pagina", "error",
                           "La pagina no tiene etiqueta <title>.",
                           "Define un <title> de 30 a 60 caracteres con la palabra clave "
                           "principal; es el texto mas peso que muestra el buscador."))
    elif not 30 <= m["titulo_len"] <= 60:
        h.append(_hallazgo("titulo", "Titulo de la pagina", "aviso",
                           "El <title> tiene %d caracteres (ideal 30-60)." % m["titulo_len"],
                           "Recorta o completa el titulo: Google corta alrededor de los "
                           "60 caracteres y oculta el resto."))
    else:
        h.append(_hallazgo("titulo", "Titulo de la pagina", "ok",
                           "%d caracteres, dentro del rango recomendado." % m["titulo_len"],
                           ""))

    # Meta description
    if not m["descripcion"]:
        h.append(_hallazgo("descripcion", "Meta description", "error",
                           "No hay meta description.",
                           "Agrega <meta name=\"description\"> con 70 a 155 caracteres: es "
                           "el texto que el buscador muestra bajo el resultado y el que "
                           "define el clic."))
    elif not 70 <= m["descripcion_len"] <= 155:
        h.append(_hallazgo("descripcion", "Meta description", "aviso",
                           "%d caracteres (ideal 70-155)." % m["descripcion_len"],
                           "Ajusta el resumen para que se lea completo en una linea."))
    else:
        h.append(_hallazgo("descripcion", "Meta description", "ok",
                           "%d caracteres." % m["descripcion_len"], ""))

    # Canonical
    if m["canonical"]:
        h.append(_hallazgo("canonical", "URL canonica", "ok", m["canonical"], ""))
    else:
        h.append(_hallazgo("canonical", "URL canonica", "aviso",
                           "No se declara <link rel=\"canonical\">.",
                           "Declara la URL canonica para evitar que el buscador "
                           "considere duplicadas las variantes con parametros."))

    # H1
    if m["h1_count"] == 0:
        h.append(_hallazgo("h1", "Encabezado principal", "error",
                           "La pagina no tiene <h1>.",
                           "Agrega un unico <h1> con la palabra clave: es el tema real "
                           "de la pagina para el buscador."))
    elif m["h1_count"] > 1:
        h.append(_hallazgo("h1", "Encabezado principal", "aviso",
                           "Hay %d etiquetas <h1>." % m["h1_count"],
                           "Deja un solo <h1> y baja el resto de titulos a <h2>."))
    else:
        largo = len(m["h1"][0])
        estado = "ok" if 15 <= largo <= 70 else "aviso"
        h.append(_hallazgo("h1", "Encabezado principal", estado,
                           "Un <h1> de %d caracteres: %s" % (largo, m["h1"][0][:70]),
                           "" if estado == "ok" else
                           "Ajusta el H1 para que se lea completo en el resultado."))

    # Jerarquia
    if m["h2_count"] >= 2:
        h.append(_hallazgo("encabezados", "Jerarquia de titulos", "ok",
                           "%d subtitulos <h2> ordenan el contenido." % m["h2_count"], ""))
    else:
        h.append(_hallazgo("encabezados", "Jerarquia de titulos", "aviso",
                           "Solo %d <h2>; el texto queda en un solo bloque." % m["h2_count"],
                           "Divide el contenido en 3 o 4 apartados con <h2> que "
                           "respondan preguntas reales de la gente."))

    # lang
    h.append(_hallazgo("lang", "Idioma declarado", "ok" if m["lang"] else "error",
                       "lang=\"%s\"" % m["lang"] if m["lang"] else 'Falta <html lang="es-CO">',
                       'Declara <html lang="es-CO"> para que Google clasifique el idioma '
                       "y muestre el resultado al publico correcto." if not m["lang"] else ""))

    # viewport
    h.append(_hallazgo("viewport", "Diseño movil", "ok" if m["viewport"] else "error",
                       "Viewport declarado." if m["viewport"] else "Falta meta viewport.",
                       "Agrega <meta name=\"viewport\" content=\"width=device-width, "
                       "initial-scale=1.0\">: sin esto Google penaliza en movil."
                       if not m["viewport"] else ""))

    # https
    h.append(_hallazgo("https", "Conexion segura", "ok" if m["https"] else "aviso",
                       "HTTPS activo." if m["https"] else "El sitio responde por HTTP.",
                       "Activa el certificado HTTPS: Google da prioridad al sitio seguro y "
                       "marca los otros como 'No seguro'." if not m["https"] else ""))

    # Open Graph
    faltan = [k for k in ("title", "description", "image", "url", "type") if not m["og"].get(k)]
    if not m["og"]:
        h.append(_hallazgo("og", "Open Graph (compartir en redes)", "error",
                           "No hay etiquetas og:.",
                           'Agrega og:title, og:description, og:image, og:url y og:type. '
                           "Sin esto, al compartir el enlace se ve el titulo pelado y sin "
                           "imagen."))
    elif faltan:
        h.append(_hallazgo("og", "Open Graph (compartir en redes)", "aviso",
                           "Falta og:%s." % ", og:".join(faltan),
                           'Completa las etiquetas Open Graph que faltan; la imagen debe '
                           "medir 1200x630 px."))
    else:
        h.append(_hallazgo("og", "Open Graph (compartir en redes)", "ok",
                           "Las 5 etiquetas Open Graph estan completas.", ""))

    # Twitter/X card
    h.append(_hallazgo("twitter", "Tarjeta para X", "ok" if m["twitter"].get("card") else "aviso",
                       "twitter:card=%s" % m["twitter"].get("card", "")
                       if m["twitter"].get("card") else "Sin twitter:card.",
                       'Agrega <meta name="twitter:card" content="summary_large_image"> '
                       "para que el enlace se vea como imagen grande."))

    # Datos estructurados
    utiles = ("Article", "BlogPosting", "NewsArticle", "NewsMediaOrganization",
              "LocalBusiness", "Organization", "FAQPage", "HowTo", "Service",
              "WebPage", "Person", "BreadcrumbList")
    encontrados = [t for t in m["jsonld"] if any(u.lower() in t.lower() for u in utiles)]
    if encontrados:
        h.append(_hallazgo("jsonld", "Datos estructurados", "ok",
                           ", ".join(sorted(set(encontrados))[:4]),
                           "Puedes ampliar con FAQPage para ganar espacio en el resultado."))
    else:
        h.append(_hallazgo("jsonld", "Datos estructurados", "error",
                           "No hay JSON-LD.",
                           "Agrega datos estructurados Article/NewsArticle (y LocalBusiness "
                           "para el despacho). Habilitan resultado enriquecido, autor y "
                           "fecha en el buscador."))

    # Texto alternativo
    if not m["imagenes"]:
        h.append(_hallazgo("alt", "Texto alternativo", "aviso", "La pagina no tiene imagenes.",
                           "Una imagen de 1200x630 con su texto alternativo mejora el "
                           "compartido y la busqueda de imagenes.", 2))
    elif m["imagenes_sin_alt"]:
        h.append(_hallazgo("alt", "Texto alternativo", "aviso",
                           "%d de %d imagenes sin alt." % (m["imagenes_sin_alt"], len(m["imagenes"])),
                           'Describe cada imagen con alt="..."; ademas sirve para SEO y '
                           "accesibilidad."))
    else:
        h.append(_hallazgo("alt", "Texto alternativo", "ok",
                           "Las %d imagenes tienen alt." % len(m["imagenes"]), ""))

    # Enlaces
    if m["enlaces_internos"] >= 3:
        h.append(_hallazgo("enlaces", "Enlaces internos", "ok",
                           "%d enlaces internos." % m["enlaces_internos"], ""))
    else:
        h.append(_hallazgo("enlaces", "Enlaces internos", "aviso",
                           "%d enlaces internos." % m["enlaces_internos"],
                           "Enlaza desde otros articulos del sitio: es la forma mas "
                           "barata de subir paginas al classement."))

    # Extension del texto
    palabras = m["palabras"]
    if palabras < 150:
        estado, consejo = "error", ("Amplia el texto a 300 palabras o mas: por debajo de "
                                    "150 el buscador lo considera thin content.")
    elif palabras < 300:
        estado, consejo = "aviso", ("Sube a 300 palabras o mas, respondo lo que la gente "
                                    "pregunta en cada seccion.")
    elif palabras > 2500:
        estado, consejo = "aviso", ("Divide el contenido en varias paginas: por encima de "
                                    "2.500 palabras la lectura y el posicionamiento se diluyen.")
    else:
        estado, consejo = "ok", ""
    h.append(_hallazgo("palabras", "Extension del contenido", estado,
                       "%d palabras de texto visible." % palabras, consejo))

    # URL legible
    slug = m["slug"]
    if not slug:
        h.append(_hallazgo("slug", "URL legible", "aviso", "La URL termina en /.",
                           "Conviene que las paginas tengan un nombre descriptivo "
                           "(/articulo/reclamacion-laboral)."))
    else:
        problemas = []
        if len(slug) > 75:
            problemas.append("es muy larga (%d caracteres)" % len(slug))
        if _sin_acentos(slug) != slug.lower():
            problemas.append("usa mayusculas o tildes")
        if " " in slug or "_" in slug:
            problemas.append("tiene espacios o guiones bajos")
        if problemas:
            h.append(_hallazgo("slug", "URL legible", "aviso",
                               "/%s: %s." % (slug, "; ".join(problemas)),
                               "Usa minusculas, guiones y menos de 75 caracteres; la URL "
                               "es parte del mensaje de la pagina."))
        else:
            h.append(_hallazgo("slug", "URL legible", "ok", "/%s" % slug, ""))

    # Fecha y autor (E-E-A-T), solo en articulos
    if es_articulo:
        h.append(_hallazgo("fecha", "Fecha de publicacion", "ok" if m["fecha"] else "aviso",
                           m["fecha"] or "Sin datePublished en los datos estructurados.",
                           "Declara datePublished y dateModified en el JSON-LD: Google "
                           "muestra la fecha y toma la pagina como contenido fresco."
                           if not m["fecha"] else ""))
        h.append(_hallazgo("autor", "Autor identificable", "ok" if m["autor"] else "aviso",
                           m["autor"] or "Sin autor en los datos estructurados.",
                           "Declara author con el nombre y la URL del perfil del abogado: "
                           "es una señal de experiencia y confianza (E-E-A-T)."
                           if not m["autor"] else ""))

    # Imagen para compartir
    if not m["og"].get("image") and not m["imagenes"]:
        h.append(_hallazgo("imagen_og", "Imagen para compartir", "aviso",
                           "Sin og:image ni imagen principal.",
                           "Crea una imagen de 1200x630 px por articulo: es la que aparece "
                           "al compartir el enlace y sube el clic.", 3))

    # Sitemap y robots
    if propio:
        robots = ctx.get("robots")
        if robots is False:
            h.append(_hallazgo("robots", "robots.txt", "aviso",
                               "No responde o devuelve error.",
                               'Publica robots.txt con "Allow: /" y la linea Sitemap: '
                               "apunta al mapa del sitio."))
        elif robots:
            tiene_sitemap = "sitemap" in robots.lower()
            h.append(_hallazgo("robots", "robots.txt", "ok" if tiene_sitemap else "aviso",
                               "robots.txt disponible%s." % (" con Sitemap" if tiene_sitemap
                                                             else " sin linea Sitemap"),
                               "" if tiene_sitemap else
                               "Agrega la linea Sitemap: en robots.txt para que los "
                               "motores descubran las paginas nuevas."))
        else:
            h.append(_hallazgo("robots", "robots.txt", "aviso", "No se pudo verificar.",
                               "Verifica que robots.txt exista y no bloquee a Googlebot.",
                               2))
        sitemap = ctx.get("sitemap")
        if sitemap is False:
            h.append(_hallazgo("sitemap", "Mapa del sitio", "error",
                               "No hay sitemap.xml.",
                               'Publica /sitemap.xml con las URL de portada, areas y '
                               "articulos, y declaralo en Search Console y Bing Webmaster."))
        elif sitemap is True:
            h.append(_hallazgo("sitemap", "Mapa del sitio", "ok", "sitemap.xml disponible.", ""))
        else:
            h.append(_hallazgo("sitemap", "Mapa del sitio", "aviso",
                               "No se pudo verificar.",
                               "Revisa que el sitemap.xml sea accesible.", 2))
    else:
        h.append(_hallazgo("sitemap", "Mapa del sitio y robots.txt", "ok",
                           "Se evaluan en el administrador del sitio.", "", 0))

    # Velocidad aproximada
    peso = m["bytes"] / 1024.0
    if m["bytes"] and peso > 400:
        h.append(_hallazgo("velocidad", "Peso del HTML", "aviso",
                           "%.0f KB de HTML y %d scripts." % (peso, m["scripts"]),
                           "Reduce scripts e imagenes: el Core Web Vitals es factor de "
                           "posicionamiento desde 2023."))
    else:
        h.append(_hallazgo("velocidad", "Peso del HTML", "ok",
                           "%.0f KB de HTML y %d scripts." % (peso, m["scripts"]), ""))

    # Imagenes ligeras
    total_img = len(m["imagenes"])
    if total_img and m["imagenes_lazy"] < total_img:
        h.append(_hallazgo("livianas", "Carga de imagenes", "aviso",
                           "%d de %d imagenes sin loading=\"lazy\"." % (m["imagenes_lazy"], total_img),
                           'Agrega loading="lazy" a las imagenes bajo el primer pantallazo '
                           "y sirvelas en WebP."))
    elif total_img:
        h.append(_hallazgo("livianas", "Carga de imagenes", "ok",
                           "Las %d imagenes usan lazy loading." % total_img, ""))
    else:
        h.append(_hallazgo("livianas", "Carga de imagenes", "ok", "Sin imagenes que optimizar.", ""))

    # Palabra clave
    clave = ctx.get("clave") or ""
    if clave:
        places = []
        if _sin_acentos(clave) in _sin_acentos(m["titulo"]):
            places.append("titulo")
        if _sin_acentos(clave) in _sin_acentos(m["h1"][0] if m["h1"] else ""):
            places.append("H1")
        if _sin_acentos(clave) in _sin_acentos(m["primer_parrafo"]):
            places.append("primer parrafo")
        if any(_sin_acentos(clave) in _sin_acentos(t) for n, t in m["encabezados"] if n == 2):
            places.append("subtitulos")
        if len(places) >= 3:
            h.append(_hallazgo("keyword", "Palabra clave \"%s\"" % clave, "ok",
                               "Aparece en %s." % ", ".join(places), ""))
        elif places:
            h.append(_hallazgo("keyword", "Palabra clave \"%s\"" % clave, "aviso",
                               "Solo aparece en %s." % ", ".join(places),
                               "Incluyela tambien en el primer parrafo y en un subtitulo "
                               "para reforzar la relevancia."))
        else:
            h.append(_hallazgo("keyword", "Palabra clave \"%s\"" % clave, "error",
                               "No aparece en titulo, H1 ni primer parrafo.",
                               "Reescribe el titulo y la introduccion usando la palabra "
                               "clave de forma natural."))
    else:
        h.append(_hallazgo("keyword", "Palabra clave", "ok",
                           "Sin palabra clave indicada: el analisis se centra en la pagina.",
                           "", 0))

    return h


def _filtro(hallazgos, claves):
    return [x for x in hallazgos if x["clave"] in claves]


def _puntaje(hallazgos):
    total = sum(x["peso"] for x in hallazgos) or 1
    logro = sum(x["peso"] if x["estado"] == "ok"
                else (x["peso"] * 0.5 if x["estado"] == "aviso" else 0)
                for x in hallazgos)
    return int(round(100.0 * logro / total))


COMUNES = ("titulo", "descripcion", "canonical", "h1", "encabezados", "lang",
           "viewport", "https", "og", "twitter", "jsonld", "alt", "enlaces",
           "palabras", "slug", "fecha", "autor", "imagen_og", "sitemap",
           "robots", "velocidad", "livianas", "keyword")


def revisar_motores(m, ctx):
    """Arma el informe por buscador a partir del diagnostico comun."""
    base = revisar_tecnica(m, ctx)
    motores = []
    for motor in MOTORES:
        if motor["id"] == "google":
            hall = _filtro(base, COMUNES)
        elif motor["id"] == "bing":
            hall = _filtro(base, COMUNES)
            hall.append(_hallazgo(
                "verificacion", "Verificacion en Bing Webmaster", "ok" if m["msvalidate"] else "aviso",
                "Meta de verificacion presente." if m["msvalidate"] else "Sin meta msvalidate.01.",
                "" if m["msvalidate"] else
                "Verifica el sitio en Bing Webmaster Tools y agrega la meta "
                "msvalidate.01: es la unica forma de solicitar inclusion rapida.",
                peso=2))
        else:
            hall = _filtro(base, ("titulo", "descripcion", "h1", "encabezados",
                                  "enlaces", "palabras", "lang", "og", "slug"))
            hall.append(_hallazgo(
                "jsonld", "Datos estructurados", "ok" if m["jsonld"] else "aviso",
                "Datos estructurados: %s." % ", ".join(sorted(set(m["jsonld"]))[:3])
                if m["jsonld"] else "Sin datos estructurados.",
                "" if m["jsonld"] else
                "DuckDuckGo hereda de Bing: los datos estructurados ayudan a ambos.",
                peso=4))
        motores.append({
            "id": motor["id"],
            "nombre": motor["nombre"],
            "nota": motor["nota"],
            "puntaje": _puntaje(hall),
            "hallazgos": hall,
            "errores": sum(1 for x in hall if x["estado"] == "error"),
            "avisos": sum(1 for x in hall if x["estado"] == "aviso"),
        })
    return motores


# ---------------------------------------------------------- viabilidad en redes
def revisar_redes(contenido, url=""):
    """Evalua si el contenido sirve para cada red social.

    `contenido` trae titulo, resumen, texto, imagen y etiqueta del articulo; si
    no hay articulo se usan los datos de la pagina (titulo y descripcion).
    """
    titulo = (contenido.get("titulo") or "").strip()
    resumen = (contenido.get("resumen") or "").strip()
    texto = (contenido.get("texto") or "").strip()
    imagen = (contenido.get("imagen") or "").strip()
    completo = ("%s %s" % (titulo, texto)).strip()
    palabras = len(_palabras(completo))
    hashtags = len(set(re.findall(r"#(\w{3,})", completo)))
    interrogacion = bool(re.search(r"[?¿]", titulo))
    numero = bool(re.search(r"\d", titulo))
    megafono = any(p in _sin_acentos(completo) for p in
                   ("nuevo", "nueva", "tipos de", "como ", "que hacer", "error",
                    "reclamacion", "derecho", "sentencia", "abogado", "tribunal"))
    largo_bueno = 300 <= palabras <= 2000
    lista = re.search(r"^[\-\*•]|^\s{2,}[\-\*•]|\n\s*[\-\*•]", texto, re.M) is not None
    salida = []
    for red in REDES:
        r = []
        tmin, tmax = red["titulo"]
        lmin, lmax = red["resumen"]
        hmin, hmax = red["hashtags"]

        if not titulo:
            r.append(("error", "Sin titulo", "No hay titulo que sostenga la red.",
                      "Escribe un titulo claro: es el texto que se ve en la vista previa."))
        elif not tmin <= len(titulo) <= tmax:
            r.append(("aviso", "Titulo de %d caracteres" % len(titulo),
                      "Para %s lo comodo es entre %d y %d." % (red["nombre"], tmin, tmax),
                      "Ajusta el titulo al rango de %s sin perder la palabra clave." % red["nombre"]))
        else:
            r.append(("ok", "Titulo de %d caracteres" % len(titulo), "Rango recomendado.", ""))

        if resumen:
            if not lmin <= len(resumen) <= lmax:
                r.append(("aviso", "Resumen de %d caracteres" % len(resumen),
                          "%s funciona mejor con %d-%d." % (red["nombre"], lmin, lmax),
                          "Reescribe el resumen como texto listo para copiar y pegar."))
            else:
                r.append(("ok", "Resumen de %d caracteres" % len(resumen), "Rango recomendado.", ""))
        else:
            r.append(("error", "Sin resumen", "No hay texto base para la publicacion.",
                      "El resumen es el parrafo que se comparte: sin el, cada publicacion "
                      "se arma a mano."))

        if red["id"] == "instagram":
            if imagen:
                r.append(("ok", "Tiene imagen", "La pieza visual es el requisito de la red.", ""))
            else:
                r.append(("error", "Sin imagen", "Instagram es una red visual.",
                          "Crea una pieza de 1080x1350 px por articulo: es obligatoria para "
                          "que la publicacion tenga alcance."))
        else:
            if imagen:
                r.append(("ok", "Tiene imagen", "La vista previa se muestra con imagen.", ""))
            else:
                r.append(("aviso", "Sin imagen", "El enlace se comparte sin miniatura.",
                          "Sin imagen el alcance baja; reutiliza la del articulo."))

        if hashtags == 0:
            r.append(("aviso", "Sin hashtags", "El texto no tiene hashtags.",
                      "Agrega entre %d y %d hashtags al final del texto: son el canal de "
                      "descubrimiento en %s." % (hmin, hmax, red["nombre"])))
        elif hashtags < hmin:
            r.append(("aviso", "%d hashtag(s)" % hashtags, "Pocos para la red.",
                      "Sube a %d-%d hashtags relevantes del area jurdica." % (hmin, hmax)))
        elif hashtags > hmax:
            r.append(("aviso", "%d hashtags" % hashtags, "Exceso de etiquetas.",
                      "Baja a %d-%d: en %s el exceso se toma como spam." % (hmin, hmax, red["nombre"])))
        else:
            r.append(("ok", "%d hashtags" % hashtags, "Cantidad adecuada.", ""))

        if not largo_bueno:
            r.append(("aviso", "%d palabras" % palabras,
                      "El contenido es %s." % ("corto" if palabras < 300 else "muy largo"),
                      "Apunta a 300-2.000 palabras: es el rango que mejor se consume en "
                      "redes y en buscadores."))
        else:
            r.append(("ok", "%d palabras" % palabras, "Extension adecuada.", ""))

        if not (megafono and (interrogacion or numero)):
            r.append(("aviso", "Abertura debil", "El titulo no abre con una pregunta ni con un dato.",
                      "Abre con una pregunta o una cifra concreta: las primeras dos lineas "
                      "deciden si la gente sigue leyendo."))
        else:
            r.append(("ok", "Abertura con gancho", "Titulo con pregunta o dato.", ""))

        if not lista and red["id"] in ("linkedin", "facebook"):
            r.append(("aviso", "Sin lista ni pasos", "El texto es un bloque corrido.",
                      "Convierte los puntos en una lista con vinetas: en %s se lee mucho "
                      "mas rapido." % red["nombre"]))
        if red["id"] == "x" and len(resumen) > 280:
            r.append(("aviso", "Supera los 280 caracteres", "No cabe en un post.",
                      "Deja un resumen de 280 caracteres o arma un hilo."))

        puntos = {"ok": 1.0, "aviso": 0.45, "error": 0.0}
        puntaje = int(round(100 * sum(puntos[e[0]] for e in r) / len(r)))
        salida.append({
            "id": red["id"], "nombre": red["nombre"],
            "puntaje": puntaje, "viabilidad": _viabilidad(puntaje),
            "url": url, "razones": [{"estado": e[0], "titulo": e[1], "detalle": e[2],
                                     "consejo": e[3]} for e in r],
            "publicacion": publicacion_sugerida(red, contenido, url),
        })
    return salida


def publicacion_sugerida(red, contenido, url=""):
    """Arma un borrador de publicacion con la estructura de cada red."""
    titulo = (contenido.get("titulo") or "Tu articulo").strip()
    resumen = (contenido.get("resumen") or "").strip()
    area = (contenido.get("etiqueta") or "").strip()
    base = area.lower() or "derecho"
    etiquetas = {"#%s" % base.replace(" ", ""), "#abogadocolombiano", "#derechocolombiano"}
    if red["id"] == "x":
        cuerpo = (resumen or titulo)[:280]
        return {"titulo": titulo[:70],
                "texto": "%s\n\n%s%s" % (cuerpo, url, " ".join(sorted(etiquetas)[:2])),
                "hashtags": sorted(etiquetas)[:2],
                "formato": "Post o hilo de 3 mensajes con el enlace al final."}
    if red["id"] == "instagram":
        return {"titulo": titulo[:90],
                "texto": "%s\n\n%s\n\n%s" % (titulo, resumen,
                                            " ".join(sorted(etiquetas))[:180]),
                "hashtags": sorted(etiquetas),
                "formato": "Carrusel de 6 slides: portada con el titular y una slide por "
                           "pregunta frecuente."}
    if red["id"] == "facebook":
        return {"titulo": titulo[:90],
                "texto": "%s\n\n%s\n\n%s%s" % (titulo, resumen, url, " ".join(sorted(etiquetas)[:3])),
                "hashtags": sorted(etiquetas)[:3],
                "formato": "Publicacion con enlace, imagen de 1200x630 y la pregunta de "
                           "cierre para gerar comentarios."}
    return {"titulo": titulo[:120],
            "texto": "%s\n\n%s\n\n%s\n\n%s" % (titulo, resumen, url,
                                                 "Escribenos y te orientamos sin costo."),
            "hashtags": sorted(etiquetas)[:4],
            "formato": "Post con gancho, 4 vinetas, enlace y cierre con llamada a la accion."}


# ------------------------------------------------------------------ informe IA
SISTEMA_MARKETING = """\
Eres un consultor de marketing digital que trabaja para el despacho de abogados
Derechos On (Colombia). Trabajas con auditorias On-Page y de redes sociales.

Reglas:
- Responde SIEMPRE en espanol colombiano, claro y concreto, como un consultor
  que conversa con el abogado.
- No inventes datos que no esten en la auditoria. Si un dato no aparece, recommends
  como medirlo.
- Prioriza: primero lo que bloquea la indexacion, luego lo que mas impacto tiene y
  al final las mejoras menores. Numeras los pasos del 1 al 8.
- Cada paso debe decir QUE hacer, DONDE (ruta o etiqueta) y COMO (como minimo).
- Cierra con un plan de 30 dias y con 3 ideas de publicacion para redes.
- No uses bloques de codigo ni menus. Usa texto plano con guiones.
"""


def plan_ia(informe):
    """Convierte el diagnostico en una hoja de ruta paso a paso."""
    import ia_juridica
    if not ia_juridica.configurado():
        raise MarketingError(
            "La IA no esta configurada. Define IA_CLAVE en /etc/derechoson.env y "
            "reinicia el servicio; el diagnostico tecnico ya quedo guardado.")
    motores = informe.get("motores") or []
    redes = informe.get("redes") or []
    lineas = ["PAGINA ANALIZADA: %s" % (informe.get("url") or informe.get("objetivo") or ""),
              "PUNTAJE PROMEDIO DE BUSCADORES: %s/100" % informe.get("puntaje", 0)]
    for motor in motores:
        problemas = [x for x in motor["hallazgos"] if x["estado"] != "ok"]
        lineas.append("")
        lineas.append("%s: %d/100 (%d errores, %d avisos)" % (
            motor["nombre"].upper(), motor["puntaje"], motor["errores"], motor["avisos"]))
        for x in problemas:
            lineas.append("- [%s] %s: %s" % (x["estado"].upper(), x["titulo"], x["detalle"]))
    for red in redes:
        problemas = [x for x in red["razones"] if x["estado"] != "ok"]
        lineas.append("")
        lineas.append("%s: viabilidad %s (%d/100)" % (
            red["nombre"].upper(), red["viabilidad"], red["puntaje"]))
        for x in problemas:
            lineas.append("- [%s] %s" % (x["estado"].upper(), x["titulo"]))
    contexto = contenido_resumido(informe)
    if contexto:
        lineas += ["", "CONTENIDO A POSICIONAR:", contexto[:3000]]
    respuesta = ia_juridica.consultar(
        [{"role": "user",
          "content": "Genera la hoja de ruta paso a paso para posicionar este "
                     "contenido, a partir de esta auditoria:\n\n" + "\n".join(lineas)}],
        max_tokens=3000, temperatura=0.4, sistema=SISTEMA_MARKETING)
    return respuesta.get("texto", "")


def contenido_resumido(informe):
    """Trozo de texto del contenido analizado, para que la IA lo conozca."""
    c = informe.get("contenido") or {}
    partes = []
    if c.get("titulo"):
        partes.append("TITULO: %s" % c["titulo"])
    if c.get("etiqueta"):
        partes.append("AREA: %s" % c["etiqueta"])
    if c.get("resumen"):
        partes.append("RESUMEN: %s" % c["resumen"][:600])
    if c.get("texto"):
        partes.append("TEXTO: %s" % c["texto"][:3000])
    return "\n".join(partes)


def resumen_ejecutivo(motores, redes, tecnico):
    """Texto corto con lo que hay que corregir primero."""
    errores = [x for motor in motores for x in motor["hallazgos"] if x["estado"] == "error"]
    avisos = [x for motor in motores for x in motor["hallazgos"] if x["estado"] == "aviso"]
    unicos = {}
    for x in errores + avisos:
        unicos.setdefault(x["clave"], x)
    lineas = []
    if not motores:
        return "No se pudo generar el resumen."
    promedio = int(round(sum(m["puntaje"] for m in motores) / float(len(motores))))
    lineas.append("Puntaje promedio de buscadores: %d/100 (%s)." % (
        promedio, ", ".join("%s %d" % (m["nombre"], m["puntaje"]) for m in motores)))
    if errores:
        claves = {x["clave"]: x["titulo"] for x in errores}
        lineas.append("Bloqueos (%d): %s." % (len(errores), ", ".join(claves.values())))
    else:
        lineas.append("Sin bloqueos criticos de indexacion.")
    if avisos:
        top = [x["titulo"] for x in avisos][:4]
        lineas.append("Mejoras pendientes: %s." % ", ".join(top))
    mejores = [r for r in redes if r["viabilidad"] == "Alta"]
    flojas = [r for r in redes if r["viabilidad"] == "Baja"]
    if mejores:
        lineas.append("Listas para publicar: %s." % ", ".join(r["nombre"] for r in mejores))
    if flojas:
        lineas.append("Requieren trabajo antes de publicar: %s."
                      % ", ".join(r["nombre"] for r in flojas))
    return " ".join(lineas)
