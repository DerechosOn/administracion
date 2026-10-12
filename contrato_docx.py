# -*- coding: utf-8 -*-
"""Procesamiento de plantillas de contrato desde Word (.docx)."""
import re
import html
from docx import Document
from docx.shared import Pt, Cm
from docx.oxml.ns import qn


# Variables disponibles en el contrato (deben coincidir con CONTRATO_CAMPOS en app.py)
VARIABLES_CONTRATO = {
    "nombre": "%(nombre)s",
    "documento": "%(documento)s",
    "email": "%(email)s",
    "telefono": "%(telefono)s",
    "servicio": "%(servicio)s",
    "numero": "%(numero)s",
    "ciudad": "%(ciudad)s",
    "dia": "%(dia)s",
    "mes_nombre": "%(mes_nombre)s",
    "año": "%(año)s",
    "despacho": "%(despacho)s",
    "firmante_nombre": "%(firmante_nombre)s",
    "firmante_cargo": "%(firmante_cargo)s",
}


# Membrete de DERECHOS ON (HTML que se antepone al documento)
MEMBRETE_DERECHOS_ON = """<div class="ct-membrete">
  <div class="ct-membrete-logo">
    <img src="/static/img/logo.png" alt="Derechos On" style="max-height:60px">
  </div>
  <div class="ct-membrete-datos">
    <strong>DERECHOS ON</strong> — Firma de Abogados<br>
    <span>Calle 72 # 10-35, Oficina 402, Bogotá D.C., Colombia</span><br>
    <span>Tel: +57 1 744 1234 · Email: contacto@derechos.on</span><br>
    <span>www.derechos.on</span>
  </div>
  <hr class="ct-membrete-sep">
</div>"""


def extraer_texto_docx(ruta_archivo):
    """Extrae el texto completo de un .docx preservando estructura básica."""
    doc = Document(ruta_archivo)
    partes = []
    for p in doc.paragraphs:
        if p.text.strip():
            partes.append((p.style.name if p.style else "Normal", p.text, p.runs))
    for tabla in doc.tables:
        filas = []
        for fila in tabla.rows:
            celdas = [celda.text.strip() for celda in fila.cells]
            filas.append(" | ".join(celdas))
        if filas:
            partes.append(("Table", "\n".join(filas), []))
    return partes


def runs_a_html(runs):
    """Convierte los runs de un párrafo a HTML con formato básico."""
    html_partes = []
    for run in runs:
        texto = html.escape(run.text)
        if not texto:
            continue
        estilos = []
        if run.bold:
            estilos.append("font-weight:bold")
        if run.italic:
            estilos.append("font-style:italic")
        if run.underline:
            estilos.append("text-decoration:underline")
        if run.font.size:
            pt = run.font.size.pt
            if pt:
                estilos.append(f"font-size:{pt}pt")
        if run.font.name:
            estilos.append(f"font-family:'{run.font.name}'")
        if run.font.color and run.font.color.rgb:
            estilos.append(f"color:#{run.font.color.rgb}")
        if estilos:
            html_partes.append(f'<span style="{"; ".join(estilos)}">{texto}</span>')
        else:
            html_partes.append(texto)
    return "".join(html_partes)


def estilo_a_etiqueta(style_name):
    """Mapea estilos de Word a etiquetas HTML."""
    style_lower = (style_name or "").lower()
    if style_lower.startswith("heading 1") or "titulo 1" in style_lower:
        return "h1"
    if style_lower.startswith("heading 2") or "titulo 2" in style_lower:
        return "h2"
    if style_lower.startswith("heading 3") or "titulo 3" in style_lower:
        return "h3"
    if "quote" in style_lower or "cita" in style_lower:
        return "blockquote"
    if "list" in style_lower or "lista" in style_lower:
        return "li"
    return "p"


def detectar_variables(texto):
    """Detecta placeholders tipo {{variable}} o [variable] y los convierte a %(variable)s."""
    # Primero busca {{variable}} o {variable}
    texto = re.sub(r"\{\{\s*(\w+)\s*\}\}", r"%(\1)s", texto)
    texto = re.sub(r"\{\s*(\w+)\s*\}", r"%(\1)s", texto)
    # Luego [variable]
    texto = re.sub(r"\[\s*(\w+)\s*\]", r"%(\1)s", texto)
    return texto


def normalizar_variable(texto):
    """Normaliza nombres de variables conocidos a su forma canónica %(var)s."""
    for clave, canonica in VARIABLES_CONTRATO.items():
        # Busca variaciones: {{clave}}, {clave}, [clave], {{ clave }}, etc.
        patrones = [
            r"\{\{\s*" + clave + r"\s*\}\}",
            r"\{\s*" + clave + r"\s*\}",
            r"\[\s*" + clave + r"\s*\]",
            r"%\(\s*" + clave + r"\s*\)s",
        ]
        for pat in patrones:
            texto = re.sub(pat, canonica, texto, flags=re.IGNORECASE)
    return texto


def limpiar_html(html_texto):
    """Limpia HTML básico: elimina estilos inline excesivos, normaliza etiquetas."""
    # Elimina spans vacíos
    html_texto = re.sub(r"<span[^>]*>\s*</span>", "", html_texto)
    # Normaliza múltiples espacios
    html_texto = re.sub(r"\s+", " ", html_texto)
    # Elimina atributos style vacíos
    html_texto = re.sub(r'style=""', "", html_texto)
    return html_texto.strip()


def docx_a_plantilla(ruta_archivo, incluir_membrete=True):
    """
    Convierte un .docx a plantilla HTML para el sistema de contratos.
    Retorna (html_plantilla, variables_detectadas, advertencias).
    """
    partes = extraer_texto_docx(ruta_archivo)
    html_partes = []
    variables_detectadas = set()
    advertencias = []

    for estilo, texto, runs in partes:
        etiqueta = estilo_a_etiqueta(estilo)
        if runs:
            contenido = runs_a_html(runs)
        else:
            contenido = html.escape(texto)

        # Detecta variables en el texto
        texto_con_vars = detectar_variables(contenido)
        texto_con_vars = normalizar_variable(texto_con_vars)

        # Recolecta variables usadas
        for m in re.finditer(r"%\((\w+)\)s", texto_con_vars):
            variables_detectadas.add(m.group(1))

        html_partes.append(f"<{etiqueta}>{texto_con_vars}</{etiqueta}>")

    html_final = "\n".join(html_partes)
    html_final = limpiar_html(html_final)

    if incluir_membrete:
        html_final = MEMBRETE_DERECHOS_ON + "\n" + html_final

    # Verifica variables desconocidas
    vars_conocidas = set(VARIABLES_CONTRATO.keys())
    vars_desconocidas = variables_detectadas - vars_conocidas
    if vars_desconocidas:
        advertencias.append(f"Variables no reconocidas (se mostrarán tal cual): {', '.join(sorted(vars_desconocidas))}")

    return html_final, sorted(variables_detectadas), advertencias


def validar_docx(ruta_archivo):
    """Valida que el archivo sea un .docx legible."""
    try:
        Document(ruta_archivo)
        return True, ""
    except Exception as e:
        return False, f"Archivo .docx inválido o corrupto: {e}"


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        html, vars_det, warns = docx_a_plantilla(sys.argv[1])
        print("=== HTML GENERADO ===")
        print(html)
        print("\n=== VARIABLES ===")
        print(vars_det)
        print("\n=== ADVERTENCIAS ===")
        print(warns)