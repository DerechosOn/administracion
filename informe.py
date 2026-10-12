# -*- coding: utf-8 -*-
"""Derechos On — Generación del informe de análisis en PDF (estilo corporativo).

Recibe el diccionario de datos del panel (`_datos_panel`) y produce un PDF A4
con portada de encabezado corporativo (logo, fecha del informe, paginación),
KPIs, gráficas (barras y dona), tablas de pagos/cartera/redes y notas al pie.
"""
import os
from html import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle, Image, KeepTogether)
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.graphics.shapes import Drawing, Rect, String, Line
from reportlab.graphics.charts.piecharts import Pie
from reportlab.lib.utils import ImageReader

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# logo-pdf.png es el mismo logo sin los margenes blancos del lienzo original
# (42 px a la izquierda, 150 a la derecha, 16 arriba y 37 abajo): sin recortar,
# el 18 % del ancho se pierde y la marca sale mas pequena de lo posible.
LOGO = os.path.join(BASE_DIR, "static", "img", "logo-pdf.png")
if not os.path.exists(LOGO):
    LOGO = os.path.join(BASE_DIR, "static", "img", "logo.png")

NAVY = colors.HexColor("#12224B")
AZUL = colors.HexColor("#1B4FD8")
TEAL = colors.HexColor("#01B8AA")
AMBAR = colors.HexColor("#E8A400")
ROJO = colors.HexColor("#D64550")
VERDE = colors.HexColor("#1AAB40")
GRIS_TEXTO = colors.HexColor("#5A6472")
GRIS_SUAVE = colors.HexColor("#F3F5F9")
MORADO = colors.HexColor("#744EC2")

ANCHO = A4[0] - 32 * mm
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
         "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def _dinero(n):
    try:
        z = int(round(abs(float(n))))
    except (TypeError, ValueError):
        z = 0
    s = "{:,}".format(z).replace(",", ".")
    return ("$" + s) if float(n or 0) >= 0 else ("-$" + s)


def _num(n):
    try:
        return "0" if n is None else "{:,}".format(int(n)).replace(",", ".")
    except (TypeError, ValueError):
        return "0"


def _pct(n):
    try:
        return ("%.1f" % float(n)).replace(".", ",") + "%"
    except (TypeError, ValueError):
        return "0%"


def _fecha_es(d=None):
    from datetime import date
    d = d or date.today()
    return "%d de %s de %d" % (d.day, MESES[d.month - 1], d.year)


TRAFICO = ["#1B4FD8", "#01B8AA", "#F2B705", "#D64550"]


def _estilos():
    t = ParagraphStyle("t", fontName="Helvetica", fontSize=13, leading=16,
                       textColor=NAVY, spaceAfter=2)
    sub = ParagraphStyle("sub", fontName="Helvetica", fontSize=9, leading=12,
                         textColor=GRIS_TEXTO, spaceAfter=8)
    chip = ParagraphStyle("chip", fontName="Helvetica-Bold", fontSize=8,
                          leading=10, textColor=NAVY)
    kpi_titulo = ParagraphStyle("kt", fontName="Helvetica", fontSize=7.5,
                                leading=9, textColor=GRIS_TEXTO)
    kpi_valor = ParagraphStyle("kv", fontName="Helvetica-Bold", fontSize=17,
                               leading=20, textColor=NAVY)
    cap = ParagraphStyle("cap", fontName="Helvetica-Oblique", fontSize=7.5,
                         leading=10, textColor=GRIS_TEXTO)
    celda = ParagraphStyle("cc", fontName="Helvetica", fontSize=8, leading=10,
                           textColor=NAVY)
    celda_d = ParagraphStyle("cd", fontName="Helvetica", fontSize=8, leading=10,
                             textColor=GRIS_TEXTO)
    celda_der = ParagraphStyle("cr", fontName="Helvetica", fontSize=8, leading=10,
                               textColor=NAVY, alignment=TA_RIGHT)
    celda_b = ParagraphStyle("cb", fontName="Helvetica-Bold", fontSize=8,
                             leading=10, textColor=colors.white)
    celda_bd = ParagraphStyle("cbd", fontName="Helvetica-Bold", fontSize=8,
                              leading=10, textColor=NAVY, alignment=TA_RIGHT)
    leg = ParagraphStyle("leg", fontName="Helvetica", fontSize=8, leading=12,
                         textColor=NAVY)
    nota = ParagraphStyle("nota", fontName="Helvetica", fontSize=7, leading=10,
                          textColor=GRIS_TEXTO)
    return dict(t=t, sub=sub, chip=chip, kapo=kpi_titulo, kval=kpi_valor,
                cap=cap, celda=celda, celda_d=celda_d, celda_der=celda_der,
                celda_b=celda_b, celda_bd=celda_bd, leg=leg, nota=nota)


def _seccion(S, num, texto):
    rotulo = Paragraph("&nbsp;", S["chip"])
    inner = Table([[rotulo, Paragraph(escape(texto), S["t"])]],
                  colWidths=[2.6 * mm, ANCHO - 2.6 * mm])
    inner.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), AZUL),
        ("LEFTPADDING", (0, 0), (0, 0), 4), ("RIGHTPADDING", (0, 0), (0, 0), 0),
        ("TOPPADDING", (0, 0), (0, 0), 3), ("BOTTOMPADDING", (0, 0), (0, 0), 3),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    tab = Table([[inner, Paragraph("<font size=9 color='#1B4FD8'>%02d</font>" % num, S["celda"])]],
                colWidths=[ANCHO - 10 * mm, 10 * mm])
    tab.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (0, 0), 0), ("RIGHTPADDING", (1, 0), (1, 0), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("ALIGN", (1, 0), (1, 0), "RIGHT")]))
    return tab


def _c(v):
    return v if isinstance(v, colors.Color) else colors.HexColor(v)


def _kpi(S, titulo, valor, color):
    c = _c(color)
    c1 = Paragraph(escape(titulo), S["kapo"])
    c2 = Paragraph("<font color='%s'>%s</font>" % (c.hexval(), escape(valor)), S["kval"])
    c3 = Table([[c1], [c2]], colWidths=[(ANCHO - 3 * mm) / 4 - 3 * mm])
    c3.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("LINEBELOW", (0, 0), (0, 0), 1.2, c),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    return c3


def _fila_kpi(S, items):
    celdas = [_kpi(S, t, v, c) for t, v, c in items]
    for _ in range(4 - len(celdas)):
        celdas.append(Table([[""]], colWidths=[(ANCHO - 3 * mm) / 4 - 3 * mm],
                            style=[("LEFTPADDING", (0, 0), (-1, -1), 3)]))
    tab = Table([celdas], colWidths=[(ANCHO - 3 * mm) / 4] * 4)
    tab.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#E1E6EE")),
        ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return tab


def _grafico_barras(etiquetas, valores, maximo, color=AZUL, ancho=ANCHO,
                    alto=42 * mm, hoy=0):
    n = len(valores)
    d = Drawing(ancho, alto)
    if n == 0:
        return d
    plot_x0 = 15 * mm
    plot_x1 = ancho - 2 * mm
    plot_w = plot_x1 - plot_x0
    base_y = 8 * mm
    plot_h = alto - 16 * mm
    vmax = max(4.0, float(maximo or 1) * 1.12)
    niveles = 4
    for i in range(niveles + 1):
        yy = base_y + plot_h * i / niveles
        v = vmax * i / niveles
        d.add(Line(plot_x0, yy, plot_x1, yy,
                   strokeColor=colors.HexColor("#E1E6EE"), strokeWidth=0.4))
        d.add(String(2 * mm, yy - 1.5, "%d" % round(v), fontName="Helvetica",
                     fontSize=6, fillColor=GRIS_TEXTO))
    slot = plot_w / n
    barra_w = slot * 0.62
    for i, v in enumerate(valores):
        hh = plot_h * (float(v or 0) / vmax)
        x = plot_x0 + slot * i + (slot - barra_w) / 2
        c = colors.HexColor("#01B8AA") if hoy is not None and len(valores) > 0 and i >= hoy else color
        d.add(Rect(x, base_y, barra_w, max(hh, 0.5 * mm),
                   fillColor=c, strokeColor=None))
        if n <= 8 and hh > 3 * mm:
            d.add(String(x + barra_w / 2, base_y + hh + 0.8 * mm, "%d" % round(v or 0),
                         fontName="Helvetica", fontSize=6.5, fillColor=NAVY,
                         textAnchor="middle"))
    for i, e in enumerate(etiquetas):
        if e:
            d.add(String(plot_x0 + slot * i + slot / 2, base_y - 2.5 * mm,
                         str(e), fontName="Helvetica", fontSize=6,
                         fillColor=GRIS_TEXTO, textAnchor="middle"))
    d.add(Line(plot_x0, base_y, plot_x1, base_y,
               strokeColor=colors.HexColor("#AEB6C4"), strokeWidth=0.6))
    return d


def _grafico_dona(donut, total, alto=46 * mm):
    d = Drawing(ANCHO, alto)
    colores = [VERDE if c["clase"] == "verde" else AMBAR if c["clase"] == "ambar" else ROJO
               for c in donut]
    pie = Pie()
    pie.x = 6 * mm
    pie.y = alto / 2 - 8 * mm
    pie.width = 34 * mm
    pie.height = 34 * mm
    pie.data = [c["valor"] for c in donut] if total > 0 else [1]
    pie.labels = None
    pie.slices.strokeColor = colors.white
    pie.slices.strokeWidth = 1
    pie.slices[0].fillColor = colores[0] if total > 0 else colors.HexColor("#C9D2DE")
    if total > 0:
        pie.slices[1].fillColor = colores[1]
        pie.slices[2].fillColor = colores[2]
    pie.startAngle = 90
    pie.direction = "clockwise"
    pie.innerRadiusFraction = 0.62
    d.add(pie)
    return d, colores


def _tabla_estilo(S):
    t = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#E1E6EE")),
        ("BACKGROUND", (0, 1), (-1, -1), colors.white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, GRIS_SUAVE]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
    ])
    return t


def _fila_sin_datos(S, ncols, ancho):
    p = Paragraph("<i>Sin registros en el período.</i>", S["celda_d"])
    inner = Table([[p]], colWidths=[ancho])
    inner.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), GRIS_SUAVE),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 5)]))
    return inner


def _chip(S, texto):
    p = Paragraph('<font face="Helvetica-Bold" color="#12224B">%s</font>' % escape(texto), S["chip"])
    t = Table([[p]], colWidths=[0.25 * ANCHO])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), GRIS_SUAVE),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    return t


class _CanvasPaginas(pdfcanvas.Canvas):
    """Canvas de dos pasadas: pinta el pie con el total de páginas al final."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._estados = []

    def showPage(self):
        self._estados.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._estados)
        for estado in self._estados:
            self.__dict__.update(estado)
            _pie_pagina(self, total)
            pdfcanvas.Canvas.showPage(self)
        pdfcanvas.Canvas.save(self)


def _pie_pagina(c, total):
    c.saveState()
    c.setStrokeColor(colors.HexColor("#DCE2EA"))
    c.setLineWidth(0.6)
    c.line(16 * mm, 14 * mm, A4[0] - 16 * mm, 14 * mm)
    c.setFont("Helvetica", 7)
    c.setFillColor(GRIS_TEXTO)
    c.drawString(16 * mm, 10 * mm, "Derechos On \xb7 Informe confidencial de uso interno")
    c.drawRightString(A4[0] - 16 * mm, 10 * mm,
                      "P\xe1gina %d de %d" % (c._pageNumber, total))
    c.restoreState()


def _t(v):
    """Convierte una distancia medida desde el borde superior a coordenada Y."""
    return A4[1] - v


def _cabecera(c, doc):
    """Banda superior: logo recortado a la izquierda, texto a los lados y regla.

    Geometria medida desde el borde superior de la pagina:
      0-4 mm    banda azul
      7-19 mm   logo (caja de 12 mm de alto, proportionada)
      21,5-23   regla azul
      26 mm     inicio del contenido (topMargin), sin solapes
    """
    c.saveState()
    c.setFillColor(NAVY)
    c.rect(0, _t(4 * mm), A4[0], 4 * mm, stroke=0, fill=1)

    x_logo = 16 * mm
    x_texto = 16 * mm
    try:
        ir = ImageReader(LOGO)
        iw, ih = ir.getSize()
        alto = 12 * mm
        ancho = alto * iw / ih
        ancho_max = 52 * mm          # nunca invade el bloque de texto
        if ancho > ancho_max:
            alto = alto * ancho_max / ancho
            ancho = ancho_max
        c.drawImage(LOGO, x_logo, _t(7 * mm) - alto, width=ancho, height=alto,
                    mask="auto")
        x_texto = x_logo + ancho + 5 * mm
    except Exception:
        pass

    # la marca ya aparece en el logo: aqui solo el descriptor
    c.setFont("Helvetica-Bold", 8.5)
    c.setFillColor(NAVY)
    c.drawString(x_texto, _t(11.8 * mm), "Portal jur\xeddico \xb7 Defensa y asesor\xeda legal")
    c.setFont("Helvetica", 7.5)
    c.setFillColor(GRIS_TEXTO)
    c.drawString(x_texto, _t(15.2 * mm), "Tr\xe1fico, interacciones y cobros del portal")

    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(NAVY)
    c.drawRightString(A4[0] - 16 * mm, _t(11.8 * mm), "Informe de an\xe1lisis")
    c.setFont("Helvetica", 7.5)
    c.setFillColor(GRIS_TEXTO)
    c.drawRightString(A4[0] - 16 * mm, _t(15.2 * mm),
                      "Fecha del informe: %s" % _fecha_es())
    c.setFillColor(AZUL)
    c.rect(16 * mm, _t(23 * mm), ANCHO, 1.5 * mm, stroke=0, fill=1)
    c.restoreState()


def generar_informe(d):
    """Genera el PDF del informe y devuelve los bytes."""
    if not isinstance(d, dict):
        raise ValueError("Datos del panel inválidos")
    S = _estilos()
    buf = __import__("io").BytesIO()

    # -- flujo de contenido
    hoy = _fecha_es()
    etiqueta = d.get("etiqueta_periodo", "7 días")
    periodo = d.get("periodo_texto") or "últimos 7 días"
    periodo_largo = d.get("periodo_largo") or ("Período analizado: últimos 7 días")
    gran_nombre = d.get("gran_nombre", "día")
    partes = []

    # Bloque principal (primera página)
    tittle = Paragraph("Informe de an\xe1lisis", S["t"])
    partes.append(tittle)
    partes.append(Paragraph(
        "Portal web, redes sociales, pagos y cartera de clientes \u00b7 Derechos On.",
        S["sub"]))
    fila_chips = Table([[_chip(S, "Per\xedodo: %s" % etiqueta),
                         _chip(S, "Corte del informe: %s" % hoy),
                         _chip(S, "Agrupado por %s" % gran_nombre),
                         _chip(S, "Reservado a la administraci\xf3n")]],
                       colWidths=[0.25 * ANCHO] * 4)
    fila_chips.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                    ("BOTTOMPADDING", (0, 0), (-1, -1), 10)]))
    partes.append(fila_chips)

    # ---- 1. Tráfico y visitas
    partes.append(_seccion(S, 1, "Tr\xe1fico y visitas"))
    partes.append(_fila_kpi(S, [
        ("Visitas del per\xedodo", _num(d.get("visitas_periodo")), TRAFICO[0]),
        ("Visitas hoy", _num(d.get("visitas_hoy")), TRAFICO[0]),
        ("Visitantes \xfanicos", _num(d.get("unicas_periodo")), TRAFICO[1]),
        ("Retorno (vuelta)", _num(d.get("vuelta_periodo")), TRAFICO[2]),
    ]))
    partes.append(Spacer(1, 4 * mm))
    puntos = d.get("serie_visitas", [])
    etiquetas = [str(r["etq"]) for r in puntos]
    valores = [r["n"] for r in puntos]
    maximo = d.get("max_serie") or 4
    es_hoy = None
    for i, r in enumerate(puntos):
        if r.get("es_hoy"):
            es_hoy = i
    pie_grafico = Paragraph(
        "Visitas al portal \xb7 %s%s." % (periodo,
                                          " (columna turquesa = hoy)" if es_hoy is not None else ""),
        S["cap"])
    partes.append(_grafico_barras(etiquetas, valores, maximo, hoy=es_hoy))
    partes.append(pie_grafico)
    partes.append(Spacer(1, 3 * mm))

    top_paginas = d.get("top_paginas", [])
    cab_pp = ["P\xe1gina", "Visitas"]
    filas = [[Paragraph(escape(cab_pp[0]), S["celda_b"]),
              Paragraph(cab_pp[1], S["celda_b"])]]
    ancho_pp = [0.78 * ANCHO, 0.22 * ANCHO]
    ancho_pp[1] = ancho_pp[0] * 0.30
    for r in top_paginas[:6]:
        filas.append([Paragraph(escape(r["pagina"] or "(directo)"), S["celda"]),
                      Paragraph(_num(r["n"]), S["celda_der"])])
    if not top_paginas:
        filas = [[Paragraph(cab_pp[0], S["celda_b"]), Paragraph(cab_pp[1], S["celda_b"])],
                 [_fila_sin_datos(S, 2, ancho_pp[0] + ancho_pp[1])]]
    t_pag = Table([fila for fila in filas], colWidths=ancho_pp)
    t_pag.setStyle(_tabla_estilo(S))
    partes.append(Paragraph("P\xe1ginas m\xe1s visitadas \xb7 %s" % etiqueta, S["kapo"]))
    partes.append(t_pag)
    partes.append(Spacer(1, 3 * mm))

    # ---- 2. Interacciones
    partes.append(_seccion(S, 2, "Interacciones \xb7 %s" % etiqueta))
    por_tipo = list(d.get("por_tipo", []))
    total_inter = sum(r["n"] for r in por_tipo)
    if not por_tipo or total_inter == 0:
        partes.append(_fila_sin_datos(S, 1, ANCHO))
    else:
        max_n = max(r["n"] for r in por_tipo)
        alto = max(26 * mm, len(por_tipo) * 9 * mm + 2 * mm)
        dib = Drawing(ANCHO, alto)
        y0 = alto - 6 * mm
        disponibles = {  # colores por tipo
            "chat": TEAL, "contacto": AZUL, "cita": MORADO,
            "registro": VERDE, "testimonio": AMBAR, "pago": ROJO,
        }
        for i, r in enumerate(por_tipo[:8]):
            y = y0 - i * 8 * mm
            ancho_barra = (88 * mm) * (r["n"] / max_n)
            color = disponibles.get(r["tipo"], AZUL)
            eti = (r["tipo"] or "otro").replace("_", " ").capitalize()
            dib.add(String(0, y, eti, fontName="Helvetica", fontSize=7.5,
                           fillColor=NAVY))
            dib.add(Rect(62 * mm, y - 0.1, ancho_barra, 3.2 * mm,
                         fillColor=color, strokeColor=None))
            dib.add(String(62 * mm + ancho_barra + 3 * mm, y - 0.2,
                           _num(r["n"]), fontName="Helvetica-Bold", fontSize=7.5,
                           fillColor=NAVY))
        dib.add(String(62 * mm, 1 * mm, "Total: %s" % _num(total_inter),
                       fontName="Helvetica-Oblique", fontSize=7,
                       fillColor=GRIS_TEXTO))
        partes.append(dib)
    partes.append(Spacer(1, 2 * mm))

    # ---- 3. Pagos
    partes.append(_seccion(S, 3, "Pagos y comprobantes"))
    cv = d.get("comp_validados", {})
    cp = d.get("comp_pendientes", {})
    cr = d.get("comp_rechazados", {})
    partes.append(_fila_kpi(S, [
        ("Comprobantes validados", _num(cv.get("n", 0)), VERDE),
        ("Monto validado", _dinero(cv.get("tot", 0)), VERDE),
        ("Pendientes de validar", _num(cp.get("n", 0)), AMBAR),
        ("Rechazados", _num(cr.get("n", 0)), ROJO),
    ]))
    partes.append(Spacer(1, 4 * mm))
    cobros = list(d.get("serie_cobro", []))
    if cobros:
        eti_cobro = [str(r["etq"]) for r in cobros]
        val_cobro = [r["tot"] / 1000 for r in cobros]
        partes.append(_grafico_barras(eti_cobro, val_cobro, max(val_cobro),
                                      color=TEAL, hoy=None))
        partes.append(Paragraph(
            "Cobros validados por %s \xb7 %s \xb7 miles de pesos ($000)." % (
                gran_nombre, periodo), S["cap"]))
        partes.append(Spacer(1, 3 * mm))

    ultimos = list(d.get("ultimos_comprobantes", []))
    cab_uc = ["Cliente", "Servicio / referente", "Importe", "Validado"]
    anchos_uc = [0.30 * ANCHO, 0.34 * ANCHO, 0.18 * ANCHO, 0.18 * ANCHO]
    filas = [[Paragraph(c, S["celda_b"]) for c in cab_uc]]
    for r in ultimos[:6]:
        filas.append([
            Paragraph(escape(r.get("cliente") or "-"), S["celda"]),
            Paragraph(escape(r.get("servicio_cartera") or r.get("referencia") or "-"), S["celda_d"]),
            Paragraph(_dinero(r.get("importe", 0)), S["celda_der"]),
            Paragraph(escape((r.get("validado_el") or "-")[:10]), S["celda_d"])])
    if not ultimos:
        filas.append([_fila_sin_datos(S, 3, sum(anchos_uc))])
    t_uc = Table(filas, colWidths=anchos_uc)
    t_uc.setStyle(_tabla_estilo(S))
    partes.append(KeepTogether(
        [Paragraph("\xdaltimos comprobantes validados", S["kapo"]), t_uc]))
    partes.append(Spacer(1, 4 * mm))

    # ---- 4. Cartera
    partes.append(_seccion(S, 4, "Cartera de clientes"))
    partes.append(_fila_kpi(S, [
        ("Cartera total", _dinero(d.get("total_cartera", 0)), NAVY),
        ("Recibido", _dinero(d.get("total_pagado", 0)), VERDE),
        ("Saldo por cobrar", _dinero(d.get("total_saldo", 0)), ROJO),
        ("Tasa de cobro", _pct(d.get("tasa_cobro", 0)), TEAL),
    ]))
    partes.append(Spacer(1, 4 * mm))
    total_cartera = d.get("total_cartera", 0) or 0
    if total_cartera > 0:
        donut = list(d.get("donut", []))
        dib, colores_d = _grafico_dona(donut, total_cartera)
        leyendas = []
        for i, c in enumerate(donut):
            pct = (c["valor"] / total_cartera * 100) if total_cartera else 0
            punt = "<font color='%s'>\u25cf</font>" % colores_d[i].hexval()
            leyendas.append(Paragraph(
                "%s &nbsp;<b>%s</b> (%s) &nbsp;\u00b7 %s" %
                (punt, escape(c["label"]), _pct(pct), _dinero(c["valor"])),
                S["leg"]))
        bloque_dona = Table([[dib],
                            [leyendas[0]], [leyendas[1]], [leyendas[2]]],
                            colWidths=[ANCHO // 2], rowHeights=[48 * mm, 7 * mm, 7 * mm, 7 * mm])
        bloque_dona.setStyle(TableStyle([
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 1), (-1, -1), 2)]))
        bloque_txt = Table([[Paragraph("Composici\xf3n de la cartera por estado de deuda", S["kapo"])],
                            [Paragraph("Distribuci\xf3n del saldo total seg\xfan el estado de cada servicio: "
                                       "al d\xeda o cubierto, por vencer en 30 d\xedas y vencido.", S["cap"])],
                            [Spacer(1, 2 * mm)],
                            [Paragraph("Al d\xeda / Pagada &nbsp;\u2014 %s" % _dinero(d.get("al_dia_saldo", 0)), S["leg"])],
                            [Paragraph("Por vencer (30 d\xedas) &nbsp;\u2014 %s" % _dinero(d.get("por_vencer_saldo", 0)), S["leg"])],
                            [Paragraph("Vencida &nbsp;\u2014 %s" % _dinero(d.get("en_mora_saldo", 0)), S["leg"])]],
                           colWidths=[ANCHO // 2])
        bloque_txt.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 8),
                                        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                                        ("TOPPADDING", (0, 0), (-1, -1), 2)]))
        partes.append(Table([[bloque_dona, bloque_txt]]))
    else:
        partes.append(_fila_sin_datos(S, 1, ANCHO))
    partes.append(Spacer(1, 4 * mm))

    regs = list(d.get("registros", []))
    cab_c = ["Cliente", "Servicio", "Valor", "Pagado", "Saldo", "Estado"]
    anchos_c = [0.20 * ANCHO, 0.22 * ANCHO, 0.13 * ANCHO, 0.13 * ANCHO,
                0.13 * ANCHO, 0.19 * ANCHO]
    filas = [[Paragraph(c, S["celda_b"]) for c in cab_c]]
    COLOR_ESTADO = {"Pagada": VERDE, "Al d\xeda": VERDE, "Por pagar": AMBAR,
                    "Por vencer": AMBAR, "Vencida": ROJO}
    for r in regs[:12]:
        est = r.get("estado", "")
        color_e = COLOR_ESTADO.get(est, GRIS_TEXTO)
        filas.append([
            Paragraph(escape(r.get("cliente") or "-"), S["celda"]),
            Paragraph(escape(r.get("servicio") or "-"), S["celda_d"]),
            Paragraph(_dinero(r.get("valor_total", 0)), S["celda_der"]),
            Paragraph(_dinero(r.get("pagado", 0)), S["celda_der"]),
            Paragraph(_dinero(r.get("saldo", 0)), S["celda_der"]),
            Paragraph("<font color='%s'><b>%s</b></font>" % (color_e.hexval(), escape(est)), S["celda"])])
    extra = len(regs) - 12
    if regs and extra > 0:
        p = Paragraph("<i>... y %d servicios m\xe1s. Detalle completo en el m\xf3dulo de Cartera.</i>" % extra,
                      S["cap"])
        filas.append([Paragraph("", S["celda_d"])] * 1 + [p] + [Paragraph("", S["celda_d"])] * 4)
    if not regs:
        filas.append([_fila_sin_datos(S, 6, sum(anchos_c))])
    t_c = Table(filas, colWidths=anchos_c, repeatRows=1)
    t_c.setStyle(_tabla_estilo(S))
    partes.append(KeepTogether([Paragraph("Detalle de la cartera", S["kapo"]), t_c]))
    partes.append(Spacer(1, 4 * mm))

    # ---- 5. Redes sociales
    partes.append(_seccion(S, 5, "Redes sociales"))
    plataf = list(d.get("plataformas", []))
    cab_r = ["Plataforma", "Estado", "Publicaciones", "Seguidores", "Alcance",
             "Impresiones", "Interacciones"]
    anchos_r = [0.17 * ANCHO, 0.13 * ANCHO, 0.15 * ANCHO, 0.13 * ANCHO,
                0.13 * ANCHO, 0.15 * ANCHO, 0.14 * ANCHO]
    filas = [[Paragraph(c, S["celda_b"]) for c in cab_r]]
    for p in plataf:
        m = p.get("metrica") or {}
        estado = "Activa" if p.get("activa") else "Inactiva"
        color_e = VERDE if p.get("activa") else GRIS_TEXTO
        filas.append([
            Paragraph(escape(p.get("nombre") or p.get("clave")), S["celda"]),
            Paragraph("<font color='%s'><b>%s</b></font>" % (color_e.hexval(), estado), S["celda"]),
            Paragraph(_num(p.get("publicaciones", 0)), S["celda_der"]),
            Paragraph(_num(m.get("seguidores", 0)), S["celda_der"]),
            Paragraph(_num(m.get("alcance", 0)), S["celda_der"]),
            Paragraph(_num(m.get("impresiones", 0)), S["celda_der"]),
            Paragraph(_num(m.get("interacciones", 0)), S["celda_der"])])
    if not plataf:
        filas.append([_fila_sin_datos(S, 7, sum(anchos_r))])
    t_r = Table(filas, colWidths=anchos_r, repeatRows=1)
    t_r.setStyle(_tabla_estilo(S))
    partes.append(KeepTogether([Paragraph("Resumen por plataforma", S["kapo"]), t_r]))
    partes.append(Spacer(1, 3 * mm))

    pubs = list(d.get("publicaciones", []))
    hist = list(d.get("historial_metricas", []))
    if pubs:
        cab_p = ["Plataforma", "Publicaci\xf3n", "Fecha"]
        anchos_p = [0.16 * ANCHO, 0.60 * ANCHO, 0.24 * ANCHO]
        filas = [[Paragraph(c, S["celda_b"]) for c in cab_p]]
        NOM = {"linkedin": "LinkedIn", "x": "X / Twitter", "instagram": "Instagram"}
        for p in pubs[:6]:
            filas.append([
                Paragraph(escape(NOM.get(p.get("plataforma"), p.get("plataforma"))), S["celda"]),
                Paragraph(escape(p.get("titulo") or "-"), S["celda_d"]),
                Paragraph(escape((p.get("creado_el") or "-")[:10]), S["celda_d"])])
        t_p = Table(filas, colWidths=anchos_p, repeatRows=1)
        t_p.setStyle(_tabla_estilo(S))
        partes.append(KeepTogether([Paragraph("Publicaciones recientes", S["kapo"]), t_p]))
        partes.append(Spacer(1, 3 * mm))
    if hist:
        cab_h = ["Fecha", "Plataforma", "Seguidores", "Alcance", "Impresiones", "Interacciones"]
        anchos_h = [0.18 * ANCHO, 0.18 * ANCHO, 0.16 * ANCHO, 0.16 * ANCHO,
                    0.16 * ANCHO, 0.16 * ANCHO]
        filas = [[Paragraph(c, S["celda_b"]) for c in cab_h]]
        for h in hist[:7]:
            filas.append([
                Paragraph(escape((h.get("fecha") or "-")[:10]), S["celda_d"]),
                Paragraph(escape(h.get("plataforma") or "-"), S["celda"]),
                Paragraph(_num(h.get("seguidores", 0)), S["celda_der"]),
                Paragraph(_num(h.get("alcance", 0)), S["celda_der"]),
                Paragraph(_num(h.get("impresiones", 0)), S["celda_der"]),
                Paragraph(_num(h.get("interacciones", 0)), S["celda_der"])])
        t_h = Table(filas, colWidths=anchos_h, repeatRows=1)
        t_h.setStyle(_tabla_estilo(S))
        partes.append(KeepTogether([Paragraph("Hist\xf3rico de m\xe9tricas registrado", S["kapo"]), t_h]))
        partes.append(Spacer(1, 4 * mm))

    # ---- Notas
    partes.append(_seccion(S, 6, "Notas del informe"))
    sync = d.get("sync_ultimo") or {}
    if sync.get("ejecutado_el"):
        notas_redes = ("Métricas de redes actualizadas automáticamente el %s (%s)."
                       % (str(sync["ejecutado_el"])[:16],
                          ", ".join(p for p in (sync.get("plataformas") or "").split(",") if p)
                          or "sin detalle"))
    else:
        notas_redes = ("Aún no hay lecturas automáticas de redes: se registran solas al "
                       "conectar las cuentas.")
    notas = [
        "Período analizado: %s." % periodo_largo,
        "Datos recopilados de visitas, interacciones, comprobantes, cartera y redes "
        "sociales del portal Derechos On. La cartera y las redes sociales reflejan "
        "valores actuales, no del período seleccionado.",
        "Las cifras de redes sociales provienen de la última medición registrada "
        "o importada (LinkedIn, X / Twitter e Instagram).",
        notas_redes,
        "Informe generado automáticamente el %s. Uso reservado a la administración; "
        "no debe difundirse sin autorización." % hoy,
    ]
    for n in notas:
        partes.append(Paragraph("\u2013&nbsp;" + escape(n), S["nota"]))
        partes.append(Spacer(1, 1.5 * mm))
    partes.append(Spacer(1, 2 * mm))
    partes.append(Paragraph(
        "Derechos On &nbsp;\u00b7&nbsp; %s" % hoy, S["nota"]))

    # -- construir
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
        topMargin=26 * mm, bottomMargin=20 * mm,
        title="Informe de análisis – Derechos On",
        author="Derechos On",
        subject="Informe de análisis del portal web",
        creator="Panel de análisis – Derechos On")
    doc.build(partes, canvasmaker=_CanvasPaginas,
              onFirstPage=_cabecera, onLaterPages=_cabecera)
    return buf.getvalue()