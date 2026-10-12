# -*- coding: utf-8 -*-
"""Agente automatizado para el chat de Jarvis."""
import os
import json
import re
from typing import Dict, Any, List, Tuple

try:
    from flask import session
except Exception:
    session = {}

import db
import conocimiento_juridico as cj

NOMBRE_AGENTE = "Jarvis_Agente"
DESCRIPCION = "Agente automatizado que recibe el caso, identifica área jurídica, aplica conocimiento normativo colombiano verificado y agenda cita con abogado disponible."


class AgenteJarvis:
    def __init__(self):
        self.areas = {
            'laboral': ['trabajo', 'despido', 'liquidacion', 'salario', 'cesantia', 'preaviso', 'arl', 'sindicato'],
            'civil': ['contrato', 'arrendamiento', 'compraventa', 'obligacion', 'prescripcion', 'reivindicacion'],
            'familia': ['divorcio', 'custodia', 'alimentos', 'adopcion', 'tuicion', 'sucesion'],
            'penal': ['denuncia', 'hurto', 'estafa', 'lesiones', 'riesgo', 'proceso penal'],
            'administrativo': ['entidad', 'acto administrativo', 'derecho de peticion', 'tutela', 'cpaca'],
            'comercial': ['sociedad', 'sas', 'factura', 'proveedor', 'insolvencia', 'reorganizacion', 'liquidacion judicial'],
        }

    def normalizar(self, texto: str) -> str:
        s = (texto or '').lower()
        s = re.sub(r'[^\w\sáéíóúüñ]', ' ', s)
        s = re.sub(r'\s+', ' ', s)
        return s.strip()

    def identificar_area(self, texto: str) -> str:
        s = self.normalizar(texto)
        scores = {}
        for area, kws in self.areas.items():
            c = sum(1 for k in kws if k in s)
            if c:
                scores[area] = c
        if scores:
            return sorted(scores.items(), key=lambda x: -x[1])[0][0]
        return 'general'

    def obtener_abogado_disponible(self):
        try:
            rs = db.consultar("SELECT id, nombre, especialidad FROM abogados WHERE activo=1 ORDER BY id LIMIT 1")
            if rs:
                return rs[0]
        except Exception:
            pass
        return None

    def procesar(self, mensaje: str, contexto: Dict[str, Any] = None) -> Dict[str, Any]:
        ctx = contexto or {}
        mensaje_n = self.normalizar(mensaje)
        area = self.identificar_area(mensaje)
        abogado = self.obtener_abogado_disponible()

        normas = []
        try:
            normas = cj.fragmentos(mensaje, limite=4)
        except Exception:
            normas = []

        respuesta = []
        respuesta.append("## Caso recibido")
        respuesta.append(f"- Área identificada: **{area.upper()}**")
        if abogado:
            respuesta.append(f"- Abogado disponible: **{abogado.get('nombre')}** ({abogado.get('especialidad') or 'General'})")
        else:
            respuesta.append("- Abogado disponible: **Agenda general** (no hay abogados activos registrados)")

        if normas:
            respuesta.append("\n## Fundamento normativo (verificado)")
            for n in normas[:3]:
                respuesta.append(f"- [{n['clave']} {n['ref']}]({n['url']}) - {n['fecha']}: {n['norma']}")

        respuesta.append("\n## Siguiente paso")
        respuesta.append("Solo necesitamos formalizar la cita. ¿Qué fecha y hora prefieres (ej. 2026-10-05 14:30)?")

        estado = {
            'paso': 'agendar_cita',
            'consulta': mensaje[:500],
            'area': area,
            'abogado_id': abogado.get('id') if abogado else None,
            'fuentes': cj.urls_de(mensaje, frags=normas) if normas else [],
        }

        return {
            'texto': '\n'.join(respuesta),
            'estado': estado,
            'fuentes': estado['fuentes'],
            'acciones': [{'tipo': 'agendar', 'texto': 'Agendar cita con abogado disponible'}],
            'usar_ia': True,
        }


agente = AgenteJarvis()
