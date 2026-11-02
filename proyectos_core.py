# -*- coding: utf-8 -*-
"""Gestión de proyectos estilo ClickUp.

Proyectos con tablero Kanban, tareas con prioridad, responsable y fecha de
vencimiento, comentarios y miembros del equipo. Se apoya en la misma base de
datos SQLite que el resto de la aplicación (db.py).
"""

from datetime import date, datetime

import db

ESTADOS = ("pendiente", "en_curso", "en_revision", "completada")
ESTADO_TXT = {
    "pendiente": "Pendiente",
    "en_curso": "En curso",
    "en_revision": "En revisión",
    "completada": "Completada",
}

PRIORIDADES = ("baja", "media", "alta", "urgente")
PRIORIDAD_TXT = {
    "baja": "Baja",
    "media": "Media",
    "alta": "Alta",
    "urgente": "Urgente",
}

COLORES = ("azul", "verde", "naranja", "morado", "rojo", "turquesa")
ESTADOS_PROYECTO = ("activo", "pausado", "archivado")
ESTADO_PROYECTO_TXT = {
    "activo": "Activo",
    "pausado": "Pausado",
    "archivado": "Archivado",
}


def _ahora():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def inicializar():
    conn = db.conectar()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS proyectos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                descripcion TEXT DEFAULT '',
                color TEXT NOT NULL DEFAULT 'azul',
                estado TEXT NOT NULL DEFAULT 'activo',
                fecha_inicio TEXT DEFAULT '',
                fecha_fin TEXT DEFAULT '',
                propietario_tipo TEXT NOT NULL DEFAULT 'admin',
                propietario_id INTEGER DEFAULT NULL,
                creado_el TEXT NOT NULL,
                actualizado_el TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS proyecto_miembros (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                proyecto_id INTEGER NOT NULL,
                tipo TEXT NOT NULL,
                oid INTEGER NOT NULL,
                UNIQUE (proyecto_id, tipo, oid),
                FOREIGN KEY (proyecto_id) REFERENCES proyectos (id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS proyecto_tareas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                proyecto_id INTEGER NOT NULL,
                titulo TEXT NOT NULL,
                descripcion TEXT DEFAULT '',
                estado TEXT NOT NULL DEFAULT 'pendiente',
                prioridad TEXT NOT NULL DEFAULT 'media',
                asignado_tipo TEXT DEFAULT NULL,
                asignado_id INTEGER DEFAULT NULL,
                fecha_vencimiento TEXT DEFAULT '',
                orden INTEGER NOT NULL DEFAULT 0,
                creado_el TEXT NOT NULL,
                actualizado_el TEXT NOT NULL,
                completado_el TEXT DEFAULT NULL,
                FOREIGN KEY (proyecto_id) REFERENCES proyectos (id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS proyecto_comentarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tarea_id INTEGER NOT NULL,
                autor_tipo TEXT NOT NULL,
                autor_id INTEGER DEFAULT NULL,
                autor_nombre TEXT DEFAULT '',
                texto TEXT NOT NULL,
                creado_el TEXT NOT NULL,
                FOREIGN KEY (tarea_id) REFERENCES proyecto_tareas (id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS ix_proyecto_tareas_proyecto
                ON proyecto_tareas (proyecto_id, estado);
            CREATE INDEX IF NOT EXISTS ix_proyecto_miembros_proyecto
                ON proyecto_miembros (proyecto_id);
            """
        )
        conn.commit()
    finally:
        conn.close()


# ------------------------------------------------------------------ personas
def personas():
    """Abogados activos y administradores que pueden ser responsables."""
    salida = []
    try:
        for a in db.consultar(
                "SELECT id, nombre, especialidad FROM abogados "
                "WHERE activo = 1 ORDER BY nombre"):
            salida.append({"tipo": "abogado", "id": a["id"],
                           "nombre": a["nombre"],
                           "detalle": a.get("especialidad") or "Abogado"})
    except Exception:
        pass
    try:
        for u in db.consultar(
                "SELECT id, nombre FROM usuarios "
                "WHERE rol = 'admin' AND activo = 1 ORDER BY nombre"):
            salida.append({"tipo": "admin", "id": u["id"],
                           "nombre": u["nombre"], "detalle": "Administración"})
    except Exception:
        pass
    return salida


def nombre_persona(tipo, oid):
    if not tipo or not oid:
        return ""
    try:
        if tipo == "abogado":
            filas = db.consultar(
                "SELECT nombre FROM abogados WHERE id = ?", (oid,))
        else:
            filas = db.consultar(
                "SELECT nombre FROM usuarios WHERE id = ?", (oid,))
        return filas[0]["nombre"] if filas else "Usuario %s" % oid
    except Exception:
        return "Usuario %s" % oid


# ---------------------------------------------------------------- proyectos
def _visibilidad(tipo, oid):
    """Devuelve (fragmento SQL, parámetros) con los proyectos visibles."""
    if tipo == "admin":
        return "1 = 1", ()
    return (
        "(p.propietario_tipo = ? AND p.propietario_id = ? "
        " OR EXISTS (SELECT 1 FROM proyecto_miembros m "
        "            WHERE m.proyecto_id = p.id AND m.tipo = ? AND m.oid = ?) "
        " OR EXISTS (SELECT 1 FROM proyecto_tareas t "
        "            WHERE t.proyecto_id = p.id "
        "              AND t.asignado_tipo = ? AND t.asignado_id = ?))",
        (tipo, oid, tipo, oid, tipo, oid),
    )


def listar_proyectos(tipo, oid):
    where, params = _visibilidad(tipo, oid)
    sql = (
        "SELECT p.*, "
        " (SELECT COUNT(*) FROM proyecto_tareas t WHERE t.proyecto_id = p.id) AS total, "
        " (SELECT COUNT(*) FROM proyecto_tareas t WHERE t.proyecto_id = p.id "
        "   AND t.estado = 'completada') AS hechas "
        "FROM proyectos p WHERE " + where +
        " ORDER BY CASE p.estado WHEN 'activo' THEN 0 "
        "          WHEN 'pausado' THEN 1 ELSE 2 END, p.id DESC"
    )
    filas = db.consultar(sql, params)
    for p in filas:
        p["avance"] = _pct(p.get("hechas") or 0, p.get("total") or 0)
        p["propietario_nombre"] = nombre_persona(
            p.get("propietario_tipo"), p.get("propietario_id"))
        p["miembros_n"] = len(miembros(p["id"]))
    return filas


def _pct(hechas, total):
    if not total:
        return 0
    return int(round(100.0 * hechas / total))


def obtener_proyecto(pid):
    filas = db.consultar("SELECT * FROM proyectos WHERE id = ?", (pid,))
    return filas[0] if filas else None


def proyecto_visible(pid, tipo, oid):
    p = obtener_proyecto(pid)
    if not p:
        return None
    if tipo == "admin":
        return p
    if p["propietario_tipo"] == tipo and p["propietario_id"] == oid:
        return p
    if db.consultar(
            "SELECT 1 FROM proyecto_miembros WHERE proyecto_id = ? "
            "AND tipo = ? AND oid = ?", (pid, tipo, oid)):
        return p
    if db.consultar(
            "SELECT 1 FROM proyecto_tareas WHERE proyecto_id = ? "
            "AND asignado_tipo = ? AND asignado_id = ?", (pid, tipo, oid)):
        return p
    return None


def crear_proyecto(nombre, descripcion="", color="azul", estado="activo",
                   fecha_inicio="", fecha_fin="",
                   propietario_tipo="admin", propietario_id=None):
    ahora = _ahora()
    pid = db.ejecutar(
        "INSERT INTO proyectos (nombre, descripcion, color, estado, fecha_inicio, "
        "fecha_fin, propietario_tipo, propietario_id, creado_el, actualizado_el) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ((nombre or "").strip(), (descripcion or "").strip(), color, estado,
         fecha_inicio or "", fecha_fin or "", propietario_tipo,
         propietario_id, ahora, ahora))
    if pid and propietario_tipo and propietario_id:
        agregar_miembro(pid, propietario_tipo, propietario_id)
    return pid


def actualizar_proyecto(pid, **campos):
    permitidos = ("nombre", "descripcion", "color", "estado",
                  "fecha_inicio", "fecha_fin")
    datos = {k: v for k, v in campos.items() if k in permitidos}
    if not datos:
        return
    datos["actualizado_el"] = _ahora()
    sets = ", ".join("%s = ?" % k for k in datos)
    db.ejecutar("UPDATE proyectos SET %s WHERE id = ?" % sets,
                tuple(datos.values()) + (pid,))


def eliminar_proyecto(pid):
    db.ejecutar("DELETE FROM proyecto_comentarios WHERE tarea_id IN "
                "(SELECT id FROM proyecto_tareas WHERE proyecto_id = ?)", (pid,))
    db.ejecutar("DELETE FROM proyecto_tareas WHERE proyecto_id = ?", (pid,))
    db.ejecutar("DELETE FROM proyecto_miembros WHERE proyecto_id = ?", (pid,))
    db.ejecutar("DELETE FROM proyectos WHERE id = ?", (pid,))


# ------------------------------------------------------------------ miembros
def miembros(pid):
    filas = db.consultar(
        "SELECT * FROM proyecto_miembros WHERE proyecto_id = ? ORDER BY tipo, oid",
        (pid,))
    for m in filas:
        m["nombre"] = nombre_persona(m["tipo"], m["oid"])
    return filas


def agregar_miembro(pid, tipo, oid):
    if not tipo or not oid:
        return
    try:
        db.ejecutar(
            "INSERT OR IGNORE INTO proyecto_miembros (proyecto_id, tipo, oid) "
            "VALUES (?, ?, ?)", (pid, tipo, oid))
    except Exception:
        pass


def quitar_miembro(pid, tipo, oid):
    db.ejecutar(
        "DELETE FROM proyecto_miembros WHERE proyecto_id = ? "
        "AND tipo = ? AND oid = ?", (pid, tipo, oid))


# -------------------------------------------------------------------- tareas
def tareas_de(pid, prioridad=None, asignado_tipo=None, asignado_id=None):
    sql = "SELECT * FROM proyecto_tareas WHERE proyecto_id = ?"
    params = [pid]
    if prioridad in PRIORIDADES:
        sql += " AND prioridad = ?"
        params.append(prioridad)
    if asignado_tipo and asignado_id:
        sql += " AND asignado_tipo = ? AND asignado_id = ?"
        params.extend([asignado_tipo, asignado_id])
    sql += " ORDER BY orden, id"
    filas = db.consultar(sql, tuple(params))
    hoy = date.today().isoformat()
    for t in filas:
        t["asignado_nombre"] = nombre_persona(
            t.get("asignado_tipo"), t.get("asignado_id"))
        t["comentarios_n"] = _contar_comentarios(t["id"])
        venc = (t.get("fecha_vencimiento") or "")[:10]
        t["vencida"] = bool(venc and venc < hoy
                            and t["estado"] != "completada")
    return filas


def _contar_comentarios(tid):
    try:
        filas = db.consultar(
            "SELECT COUNT(*) AS n FROM proyecto_comentarios WHERE tarea_id = ?",
            (tid,))
        return filas[0]["n"] if filas else 0
    except Exception:
        return 0


def crear_tarea(pid, titulo, descripcion="", estado="pendiente",
                prioridad="media", asignado_tipo=None, asignado_id=None,
                fecha_vencimiento=""):
    if estado not in ESTADOS:
        estado = "pendiente"
    if prioridad not in PRIORIDADES:
        prioridad = "media"
    orden = 0
    try:
        filas = db.consultar(
            "SELECT COALESCE(MAX(orden), 0) + 1 AS n FROM proyecto_tareas "
            "WHERE proyecto_id = ?", (pid,))
        orden = filas[0]["n"] if filas else 0
    except Exception:
        pass
    ahora = _ahora()
    return db.ejecutar(
        "INSERT INTO proyecto_tareas (proyecto_id, titulo, descripcion, estado, "
        "prioridad, asignado_tipo, asignado_id, fecha_vencimiento, orden, "
        "creado_el, actualizado_el) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (pid, (titulo or "").strip(), (descripcion or "").strip(), estado,
         prioridad, asignado_tipo or None, asignado_id, fecha_vencimiento or "",
         orden, ahora, ahora))


def obtener_tarea(tid):
    filas = db.consultar("SELECT * FROM proyecto_tareas WHERE id = ?", (tid,))
    if not filas:
        return None
    t = filas[0]
    t["asignado_nombre"] = nombre_persona(
        t.get("asignado_tipo"), t.get("asignado_id"))
    return t


def tarea_visible(tid, tipo, oid):
    t = obtener_tarea(tid)
    if not t:
        return None
    if not proyecto_visible(t["proyecto_id"], tipo, oid):
        return None
    return t


def actualizar_tarea(tid, **campos):
    permitidos = ("titulo", "descripcion", "estado", "prioridad",
                  "asignado_tipo", "asignado_id", "fecha_vencimiento")
    datos = {k: v for k, v in campos.items() if k in permitidos}
    if not datos:
        return
    if datos.get("estado") in ESTADOS:
        datos["completado_el"] = _ahora() if datos["estado"] == "completada" else None
    datos["actualizado_el"] = _ahora()
    sets = ", ".join("%s = ?" % k for k in datos)
    db.ejecutar("UPDATE proyecto_tareas SET %s WHERE id = ?" % sets,
                tuple(datos.values()) + (tid,))


def cambiar_estado(tid, estado):
    if estado not in ESTADOS:
        return False
    actualizar_tarea(tid, estado=estado)
    return True


def eliminar_tarea(tid):
    db.ejecutar("DELETE FROM proyecto_comentarios WHERE tarea_id = ?", (tid,))
    db.ejecutar("DELETE FROM proyecto_tareas WHERE id = ?", (tid,))


# --------------------------------------------------------------- comentarios
def comentarios(tid):
    return db.consultar(
        "SELECT * FROM proyecto_comentarios WHERE tarea_id = ? ORDER BY id",
        (tid,))


def agregar_comentario(tid, autor_tipo, autor_id, texto):
    texto = (texto or "").strip()
    if not texto:
        return None
    return db.ejecutar(
        "INSERT INTO proyecto_comentarios (tarea_id, autor_tipo, autor_id, "
        "autor_nombre, texto, creado_el) VALUES (?, ?, ?, ?, ?, ?)",
        (tid, autor_tipo, autor_id, nombre_persona(autor_tipo, autor_id),
         texto, _ahora()))


# ------------------------------------------------------------------ resumen
def resumen(pid):
    filas = db.consultar(
        "SELECT estado, COUNT(*) AS n FROM proyecto_tareas "
        "WHERE proyecto_id = ? GROUP BY estado", (pid,))
    datos = {e: 0 for e in ESTADOS}
    for f in filas:
        if f["estado"] in datos:
            datos[f["estado"]] = f["n"]
    datos["total"] = sum(datos[e] for e in ESTADOS)
    datos["avance"] = _pct(datos["completada"], datos["total"])
    return datos


def tareas_abiertas_de(tipo, oid, limite=8):
    """Tareas abiertas asignadas a una persona (para el resumen del portal)."""
    filas = db.consultar(
        "SELECT t.*, p.nombre AS proyecto_nombre FROM proyecto_tareas t "
        "JOIN proyectos p ON p.id = t.proyecto_id "
        "WHERE t.asignado_tipo = ? AND t.asignado_id = ? "
        "AND t.estado != 'completada' "
        "ORDER BY CASE t.prioridad WHEN 'urgente' THEN 0 WHEN 'alta' THEN 1 "
        "WHEN 'media' THEN 2 ELSE 3 END, t.fecha_vencimiento, t.id "
        "LIMIT ?", (tipo, oid, limite))
    hoy = date.today().isoformat()
    for t in filas:
        venc = (t.get("fecha_vencimiento") or "")[:10]
        t["vencida"] = bool(venc and venc < hoy)
    return filas


inicializar()
