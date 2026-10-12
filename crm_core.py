# -*- coding: utf-8 -*-
"""CRM básico: tareas, recordatorios y tableros para abogados, clientes y administración."""
import os
import re
import sqlite3
from datetime import datetime, date, timedelta

RAIZ = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(RAIZ, "crm.db")


def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def inicializar():
    conn = _db()
    try:
        cur = conn.cursor()
        cur.executescript("""
        CREATE TABLE IF NOT EXISTS crm_tareas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo TEXT NOT NULL,
            descripcion TEXT DEFAULT '',
            propietario_tipo TEXT NOT NULL CHECK (propietario_tipo IN ('admin','abogado','cliente')),
            propietario_id INTEGER DEFAULT NULL,
            asignado_a_tipo TEXT DEFAULT NULL CHECK (asignado_a_tipo IN ('admin','abogado','cliente')),
            asignado_a_id INTEGER DEFAULT NULL,
            proceso_id INTEGER DEFAULT NULL,
            cita_id INTEGER DEFAULT NULL,
            prioridad TEXT NOT NULL DEFAULT 'media' CHECK (prioridad IN ('baja','media','alta','urgente')),
            estado TEXT NOT NULL DEFAULT 'pendiente' CHECK (estado IN ('pendiente','en_proceso','completada','cancelada')),
            fecha_vencimiento TEXT DEFAULT NULL,
            fecha_completada TEXT DEFAULT NULL,
            recordatorio_fecha TEXT DEFAULT NULL,
            recordatorio_enviado INTEGER NOT NULL DEFAULT 0,
            creado_el TEXT NOT NULL,
            actualizado_el TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS crm_recordatorios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo TEXT NOT NULL,
            mensaje TEXT DEFAULT '',
            destinatario_tipo TEXT NOT NULL CHECK (destinatario_tipo IN ('admin','abogado','cliente')),
            destinatario_id INTEGER DEFAULT NULL,
            tarea_id INTEGER DEFAULT NULL,
            fecha_programada TEXT NOT NULL,
            enviado INTEGER NOT NULL DEFAULT 0,
            fecha_envio TEXT DEFAULT NULL,
            creado_el TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS crm_comentarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tarea_id INTEGER NOT NULL,
            autor_tipo TEXT NOT NULL CHECK (autor_tipo IN ('admin','abogado','cliente')),
            autor_id INTEGER DEFAULT NULL,
            comentario TEXT NOT NULL,
            creado_el TEXT NOT NULL,
            FOREIGN KEY (tarea_id) REFERENCES crm_tareas (id) ON DELETE CASCADE
        );
        """)
        conn.commit()
    finally:
        conn.close()


def _ahora():
    return datetime.now().isoformat(timespec='seconds')


def crear_tarea(**kwargs):
    conn = _db()
    try:
        cur = conn.cursor()
        ahora = _ahora()
        cur.execute("""
        INSERT INTO crm_tareas (
            titulo, descripcion, propietario_tipo, propietario_id,
            asignado_a_tipo, asignado_a_id, proceso_id, cita_id,
            prioridad, estado, fecha_vencimiento, recordatorio_fecha,
            creado_el, actualizado_el
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            kwargs.get('titulo', '').strip(),
            kwargs.get('descripcion', '') or '',
            kwargs.get('propietario_tipo', 'admin'),
            kwargs.get('propietario_id'),
            kwargs.get('asignado_a_tipo'),
            kwargs.get('asignado_a_id'),
            kwargs.get('proceso_id'),
            kwargs.get('cita_id'),
            kwargs.get('prioridad', 'media'),
            kwargs.get('estado', 'pendiente'),
            kwargs.get('fecha_vencimiento'),
            kwargs.get('recordatorio_fecha'),
            ahora,
            ahora,
        ))
        tid = cur.lastrowid
        conn.commit()
        return tid
    finally:
        conn.close()


def listar_tareas(filtros=None):
    filtros = filtros or {}
    sql = "SELECT * FROM crm_tareas WHERE 1=1"
    params = []
    if filtros.get('propietario_tipo'):
        sql += " AND propietario_tipo = ?"; params.append(filtros['propietario_tipo'])
    if filtros.get('propietario_id') is not None:
        sql += " AND propietario_id = ?"; params.append(filtros['propietario_id'])
    if filtros.get('asignado_a_tipo'):
        sql += " AND asignado_a_tipo = ?"; params.append(filtros['asignado_a_tipo'])
    if filtros.get('asignado_a_id') is not None:
        sql += " AND asignado_a_id = ?"; params.append(filtros['asignado_a_id'])
    if filtros.get('estado'):
        sql += " AND estado = ?"; params.append(filtros['estado'])
    if filtros.get('proceso_id'):
        sql += " AND proceso_id = ?"; params.append(filtros['proceso_id'])
    sql += " ORDER BY (CASE prioridad WHEN 'urgente' THEN 0 WHEN 'alta' THEN 1 WHEN 'media' THEN 2 WHEN 'baja' THEN 3 END), COALESCE(fecha_vencimiento,'9999-99-99') ASC, id DESC"
    conn = _db()
    try:
        cur = conn.cursor()
        return [dict(r) for r in cur.execute(sql, params).fetchall()]
    finally:
        conn.close()


def obtener_tarea(tid):
    conn = _db()
    try:
        cur = conn.cursor()
        r = cur.execute("SELECT * FROM crm_tareas WHERE id=?", (tid,)).fetchone()
        return dict(r) if r else None
    finally:
        conn.close()


def actualizar_tarea(tid, **kwargs):
    if not kwargs: return False
    campos = []
    params = []
    for k, v in kwargs.items():
        if k in ('titulo','descripcion','propietario_tipo','propietario_id','asignado_a_tipo','asignado_a_id','proceso_id','cita_id','prioridad','estado','fecha_vencimiento','recordatorio_fecha','recordatorio_enviado','fecha_completada'):
            campos.append(f"{k}=?")
            params.append(v)
    campos.append("actualizado_el=?")
    params.append(_ahora())
    params.append(tid)
    conn = _db()
    try:
        cur = conn.cursor()
        cur.execute(f"UPDATE crm_tareas SET {', '.join(campos)} WHERE id=?", params)
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def completar_tarea(tid):
    return actualizar_tarea(tid, estado='completada', fecha_completada=_ahora())


def agregar_comentario(tarea_id, autor_tipo, autor_id, comentario):
    conn = _db()
    try:
        cur = conn.cursor()
        cur.execute("""INSERT INTO crm_comentarios (tarea_id, autor_tipo, autor_id, comentario, creado_el)
        VALUES (?,?,?,?,?)""", (tarea_id, autor_tipo, autor_id, comentario.strip(), _ahora()))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def comentarios_tarea(tarea_id):
    conn = _db()
    try:
        cur = conn.cursor()
        return [dict(r) for r in cur.execute("SELECT * FROM crm_comentarios WHERE tarea_id=? ORDER BY id ASC", (tarea_id,)).fetchall()]
    finally:
        conn.close()


def crear_recordatorio(**kwargs):
    conn = _db()
    try:
        cur = conn.cursor()
        cur.execute("""INSERT INTO crm_recordatorios (titulo, mensaje, destinatario_tipo, destinatario_id, tarea_id, fecha_programada, creado_el)
        VALUES (?,?,?,?,?,?,?)""", (
            kwargs.get('titulo','').strip(),
            kwargs.get('mensaje','') or '',
            kwargs.get('destinatario_tipo','admin'),
            kwargs.get('destinatario_id'),
            kwargs.get('tarea_id'),
            kwargs.get('fecha_programada'),
            _ahora(),
        ))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def recordatorios_pendientes():
    ahora = datetime.now().isoformat(timespec='seconds')
    conn = _db()
    try:
        cur = conn.cursor()
        return [dict(r) for r in cur.execute("SELECT * FROM crm_recordatorios WHERE enviado=0 AND fecha_programada <= ? ORDER BY fecha_programada ASC", (ahora,)).fetchall()]
    finally:
        conn.close()


def marcar_recordatorio_enviado(rid):
    conn = _db()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE crm_recordatorios SET enviado=1, fecha_envio=? WHERE id=?", (_ahora(), rid))
        conn.commit()
    finally:
        conn.close()


# ------------------------------------------------------- consultas por rol
def tareas_de(tipo, oid, estados=None):
    """Tareas donde la persona es propietaria o responsable, sin duplicar."""
    sql = ("SELECT * FROM crm_tareas WHERE (propietario_tipo=? AND propietario_id=?) "
           "OR (asignado_a_tipo=? AND asignado_a_id=?)")
    params = [tipo, oid, tipo, oid]
    if estados:
        marcas = ",".join("?" for _ in estados)
        sql += " AND estado IN (%s)" % marcas
        params.extend(estados)
    sql += (" ORDER BY CASE prioridad WHEN 'urgente' THEN 0 WHEN 'alta' THEN 1 "
            "WHEN 'media' THEN 2 ELSE 3 END, "
            "COALESCE(fecha_vencimiento,'9999-99-99') ASC, id DESC")
    conn = _db()
    try:
        cur = conn.cursor()
        return [dict(r) for r in cur.execute(sql, params).fetchall()]
    finally:
        conn.close()


def tarea_visible_para(tid, tipo, oid):
    t = obtener_tarea(tid)
    if not t:
        return None
    propietario = (t["propietario_tipo"] == tipo and t["propietario_id"] == oid)
    asignado = (t["asignado_a_tipo"] == tipo and t["asignado_a_id"] == oid)
    return t if (propietario or asignado) else None


def contar_estado(tipo, oid):
    resumen = {"pendiente": 0, "en_proceso": 0, "completada": 0, "cancelada": 0, "vencidas": 0}
    hoy = date.today().isoformat()
    for t in tareas_de(tipo, oid):
        resumen[t["estado"]] = resumen.get(t["estado"], 0) + 1
        venc = (t.get("fecha_vencimiento") or "")[:10]
        if venc and venc < hoy and t["estado"] in ("pendiente", "en_proceso"):
            resumen["vencidas"] += 1
    resumen["total"] = sum(v for k, v in resumen.items() if k != "vencidas")
    return resumen


def recordatorios_de(tipo, oid):
    conn = _db()
    try:
        cur = conn.cursor()
        return [dict(r) for r in cur.execute(
            "SELECT * FROM crm_recordatorios WHERE destinatario_tipo=? AND destinatario_id=? "
            "ORDER BY enviado ASC, fecha_programada ASC, id DESC",
            (tipo, oid)).fetchall()]
    finally:
        conn.close()


def personas_disponibles(tipo):
    """Lista de posibles responsables: abogados activos o usuarios clientes."""
    try:
        import db as _db_mod
        if tipo == "abogado":
            return _db_mod.abogados_lista(activos=True)
        if tipo == "cliente":
            return _db_mod.consultar(
                "SELECT id, nombre, email AS correo FROM usuarios "
                "WHERE rol='cliente' AND activo=1 ORDER BY nombre")
    except Exception:
        return []


inicializar()
