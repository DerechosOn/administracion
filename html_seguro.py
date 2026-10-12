# -*- coding: utf-8 -*-
"""Limpieza de HTML para el cuerpo de los contratos.

El contenido del documento lo escriben el administrador y la IA de apoyo, pero
se muestra en el portal del cliente. Aqui se deja pasar solo una lista blanca
de etiquetas y atributos: nada de scripts, estilos en linea, iframes ni
atributos ``on*``.
"""
import re
from html.parser import HTMLParser

PERMITIDAS = {
    "p", "br", "hr", "div", "span", "section", "article",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "strong", "b", "em", "i", "u", "s", "strike", "sub", "sup", "small", "mark",
    "ul", "ol", "li", "dl", "dt", "dd",
    "blockquote", "pre", "code", "q", "cite", "abbr",
    "table", "thead", "tbody", "tfoot", "tr", "td", "th", "caption", "col", "colgroup",
    "a", "img", "figure", "figcaption",
}

# Etiquetas cuyo contenido se descarta por completo (no basta con quitar la etiqueta).
DESCARTAR = {"script", "style", "iframe", "object", "embed", "form", "input", "button",
             "select", "textarea", "link", "meta", "base", "svg", "math", "noscript",
             "template", "title", "head"}

SIN_CIERRE = {"br", "hr", "img", "col"}

ATRIBUTOS = {"class", "title", "lang", "dir"}
ATRIBUTOS_ETIQUETA = {
    "a": {"href", "target", "rel"},
    "td": {"colspan", "rowspan", "align", "valign"},
    "th": {"colspan", "rowspan", "align", "valign", "scope"},
    "ol": {"start", "type"},
    "img": {"src", "alt", "width", "height"},
}

URL_SEGURA = re.compile(r"^(https?:///|/|\.{0,2}/|[a-z0-9._~\-/#?=&%+:]+$)", re.I)
PELIGROSO = re.compile(r"(javascript|vbscript|data)\s*:", re.I)


def _url_valida(valor):
    valor = (valor or "").strip()
    if not valor or PELIGROSO.search(valor):
        return None
    if valor.startswith("/") or valor.startswith("./") or valor.startswith("../"):
        return valor
    if valor.startswith("https://") or valor.startswith("http://"):
        return valor
    if valor.startswith("#"):
        return valor
    return None


class _Limpia(HTMLParser):
    def __init__(self):
        HTMLParser.__init__(self, convert_charrefs=True)
        self.salida = []
        self.omitiendo = []
        self.abiertas = []

    # -- utilidades -------------------------------------------------
    def _datos(self, etiqueta, attrs):
        permitidos = ATRIBUTOS | ATRIBUTOS_ETIQUETA.get(etiqueta, set())
        limpio = []
        destino = {}
        for nombre, valor in attrs:
            nombre = (nombre or "").lower()
            if nombre.startswith("on") or nombre not in permitidos:
                continue
            destino[nombre] = valor or ""
        if "href" in destino:
            url = _url_valida(destino["href"])
            if url is None:
                destino.pop("href")
            else:
                destino["href"] = url
        if "src" in destino:
            url = _url_valida(destino["src"])
            if url is None:
                destino.pop("src")
            else:
                destino["src"] = url
        if destino.get("target") == "_blank":
            destino["rel"] = "noopener noreferrer"
        for nombre, valor in destino.items():
            limpio.append(' %s="%s"' % (nombre, _esc(valor)))
        return "".join(limpio)

    # -- eventos ----------------------------------------------------
    def handle_starttag(self, etiqueta, attrs):
        etiqueta = etiqueta.lower()
        if self.omitiendo:
            if etiqueta in DESCARTAR:
                self.omitiendo.append(etiqueta)
            return
        if etiqueta in DESCARTAR:
            self.omitiendo.append(etiqueta)
            return
        if etiqueta not in PERMITIDAS:
            return
        self.salida.append("<%s%s>" % (etiqueta, self._datos(etiqueta, attrs)))
        if etiqueta not in SIN_CIERRE:
            self.abiertas.append(etiqueta)

    def handle_startendtag(self, etiqueta, attrs):
        etiqueta = etiqueta.lower()
        if self.omitiendo or etiqueta not in PERMITIDAS:
            return
        self.salida.append("<%s%s />" % (etiqueta, self._datos(etiqueta, attrs)))

    def handle_endtag(self, etiqueta):
        etiqueta = etiqueta.lower()
        if self.omitiendo:
            if etiqueta in self.omitiendo:
                while self.omitiendo:
                    if self.omitiendo.pop() == etiqueta:
                        break
            return
        if etiqueta in SIN_CIERRE or etiqueta not in self.abiertas:
            return
        while self.abiertas:
            abierta = self.abiertas.pop()
            self.salida.append("</%s>" % abierta)
            if abierta == etiqueta:
                break

    def handle_data(self, datos):
        if self.omitiendo:
            return
        self.salida.append(_esc(datos))

    def handle_entityref(self, nombre):
        if not self.omitiendo:
            self.salida.append("&amp;%s;" % nombre)

    def handle_charref(self, nombre):
        if not self.omitiendo:
            self.salida.append("&amp;#%s;" % nombre)

    def handle_comment(self, datos):
        return

    def handle_decl(self, decl):
        return

    def unknown_decl(self, datos):
        return

    def handle_pi(self, datos):
        return

    def resultado(self):
        while self.abiertas:
            self.salida.append("</%s>" % self.abiertas.pop())
        return "".join(self.salida)


def _esc(texto):
    return (texto.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def limpiar(texto, max_caracteres=200000):
    """Devuelve el HTML depurado. Si no queda contenido, devuelve ""."""
    if not texto:
        return ""
    texto = str(texto)[:max_caracteres]
    parser = _Limpia()
    try:
        parser.feed(texto)
        parser.close()
    except Exception:
        return ""
    salida = parser.resultado()
    salida = re.sub(r"\s+$", "", salida)
    return salida


def a_texto(html, max_caracteres=12000):
    """Convierte el HTML del documento en texto plano para enviarlo a la IA."""
    if not html:
        return ""
    plano = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    plano = re.sub(r"(?i)<br\s*/?>", "\n", plano)
    plano = re.sub(r"(?i)</(p|div|h[1-6]|li|tr|table|blockquote)>", "\n", plano)
    plano = re.sub(r"(?i)<li[^>]*>", "- ", plano)
    plano = re.sub(r"(?i)</t[dh]>", " | ", plano)
    plano = re.sub(r"<[^>]+>", "", plano)
    plano = (plano.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<")
                  .replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'"))
    plano = re.sub(r"[ \t]+", " ", plano)
    plano = re.sub(r"\n{3,}", "\n\n", plano)
    plano = plano.strip()
    if len(plano) > max_caracteres:
        plano = plano[:max_caracteres].rsplit("\n", 1)[0] + "\n[…texto recortado…]"
    return plano
