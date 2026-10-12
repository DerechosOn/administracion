# -*- coding: utf-8 -*-
"""Consulta pública de la Rama Judicial (consulta de procesos): demandantes y
demandados en procesos que cursan ante los despachos judiciales de Colombia.

Usa el API JSON pública que alimenta el portal "Consulta de Procesos" de la
Rama Judicial (https://consultaprocesos.ramajudicial.gov.co). Solo expone
procesos de acceso público (esPrivado = False)."""
import re
import time

import requests as _requests

API_V2 = "https://consultaprocesos.ramajudicial.gov.co:448/api/v2"
TIEMPO = 20
INTENTOS = 3
_SESION = _requests.Session()
_SESION.headers.update({
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0 Safari/537.36"),
    "Accept": "application/json",
})


def _postulacion_consulta(params):
    """Consulta el API de procesos con reintentos, ya que el gateway puede
    responder 403/5xx de forma intermitente ante ráfagas de consultas."""
    respuesta = None
    for i in range(INTENTOS):
        try:
            respuesta = _SESION.get(API_V2 + "/Procesos/Consulta/NombreRazonSocial",
                                    params=params, timeout=TIEMPO)
            if respuesta.status_code == 200:
                return respuesta.json()
        except Exception:
            pass
        if i < INTENTOS - 1:
            time.sleep(1.0 + i)
    if respuesta is not None:
        try:
            return respuesta.json()
        except Exception:
            return None
    return None


def _norm(texto):
    """Normaliza el texto para comparar nombres: mayúsculas y sin tildes."""
    t = (texto or "").strip().upper()
    for a, b in (("Á", "A"), ("É", "E"), ("Í", "I"), ("Ó", "O"), ("Ú", "U"),
                 ("Ñ", "N")):
        t = t.replace(a, b)
    return re.sub(r"\s+", " ", t)


def buscar(termino, limite=12):
    """Busca procesos por nombre y extrae las personas (demandantes y
    demandados) cuyo nombre coincide con el término. Devuelve fichas preparadas
    para el motor de personas. Ante cualquier error devuelve []."""
    t = _norm(termino)
    if not t:
        return []
    tokens = set(t.split())
    data = _postulacion_consulta(params={
        "nombre": termino, "tipoPersona": "1",
        "SoloActivos": "true", "codificacionDespacho": "", "pagina": "1"})
    procesos = []
    if isinstance(data, dict):
        procesos = data.get("procesos") or []
    leads = []
    vistos = set()
    for p in procesos:
        sujetos = p.get("sujetosProcesales") or ""
        for rol, nombre in re.findall(r"(Demandante|Demandado)\s*:\s*([^|]+)",
                                      sujetos, re.I):
            nombre = " ".join(nombre.split())
            if not nombre:
                continue
            parte = _norm(nombre)
            if not tokens.issubset(set(parte.split())):
                continue
            id_proceso = str(p.get("idProceso") or "")
            radicado = str(p.get("llaveProceso") or "")
            clave = (rol.lower(), parte, id_proceso, radicado)
            if clave in vistos:
                continue
            vistos.add(clave)
            departamento = p.get("departamento") or ""
            leads.append({
                "rama": True,
                "rol": rol.capitalize(),
                "nombre": nombre,
                "clave_import": ("RJ:%s:%s" % (id_proceso, radicado)),
                "nit": "",
                "tipo_local": "Parte procesal",
                "radicado": radicado,
                "id_proceso": id_proceso,
                "despacho": p.get("despacho") or "",
                "departamento": departamento,
                "municipio": departamento,
                "estado_matricula": "Proceso activo en la Rama Judicial",
                "fecha_proceso": (p.get("fechaProceso") or "")[:10],
                "fecha_ultima_actuacion": (p.get("fechaUltimaActuacion") or "")[:10],
                "sujetos": sujetos,
                "correo": "",
                "ciiu": "",
                "fuente": "Rama Judicial · consulta de procesos (demandantes y demandados)",
            })
            if len(leads) >= limite:
                return leads
    return leads