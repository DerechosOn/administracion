# -*- coding: utf-8 -*-
"""Respaldos completos de Derechos On.

Un respaldo es un ZIP con dos cosas:

    derechos.db      la base de datos (usuarios, procesos, proyectos,
                     adjuntos de proyectos, etc.)
    uploads/...      los archivos subidos que aún viven en disco
                     (comprobantes de pago, documentos, IAT)

Restaurar reemplaza la base y mezcla los archivos, dejando antes una copia de
seguridad de la base actual por si algo sale mal.
"""

import os
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime

import db

TABLAS = (
    ("usuarios", "usuarios"),
    ("abogados", "abogados"),
    ("procesos", "procesos"),
    ("proyectos", "proyectos"),
    ("proyecto_tareas", "tareas"),
    ("proyecto_adjuntos", "adjuntos"),
    ("documentos", "documentos"),
    ("comprobantes", "comprobantes"),
)


def _tamano_arbol(carpeta):
    """(número de archivos, bytes) de una carpeta, sin romperse si no existe."""
    total = 0
    cuenta = 0
    if not carpeta or not os.path.isdir(carpeta):
        return 0, 0
    for raiz, _dirs, archivos in os.walk(carpeta):
        for nombre in archivos:
            try:
                total += os.path.getsize(os.path.join(raiz, nombre))
                cuenta += 1
            except OSError:
                pass
    return cuenta, total


def estadisticas(upload_dir):
    datos = {"db_bytes": 0, "db_fecha": None, "adjuntos_bytes": 0}
    try:
        datos["db_bytes"] = os.path.getsize(db.DB_PATH)
        datos["db_fecha"] = datetime.fromtimestamp(
            os.path.getmtime(db.DB_PATH)).strftime("%d/%m/%Y %H:%M")
    except OSError:
        pass
    for tabla, clave in TABLAS:
        try:
            datos[clave] = db.consultar(
                "SELECT COUNT(*) AS n FROM %s" % tabla)[0]["n"]
        except Exception:
            datos[clave] = 0
    try:
        datos["adjuntos_bytes"] = db.consultar(
            "SELECT COALESCE(SUM(tamano), 0) AS n FROM proyecto_adjuntos")[0]["n"]
    except Exception:
        pass
    datos["uploads_archivos"], datos["uploads_bytes"] = _tamano_arbol(upload_dir)
    datos["total_bytes"] = (datos["db_bytes"] + datos["uploads_bytes"]
                            + (datos["adjuntos_bytes"] or 0))
    return datos


def _copiar_base(destino):
    """Copia consistente de la base aunque haya escrituras en curso."""
    origen = db.conectar()
    try:
        salida = sqlite3.connect(destino)
        try:
            origen.backup(salida)
        finally:
            salida.close()
    finally:
        origen.close()


def crear_respaldo(destino_zip, upload_dir):
    """Escribe el ZIP de respaldo en destino_zip y lo devuelve."""
    carpeta = tempfile.mkdtemp(prefix="respaldo-")
    try:
        ruta_db = os.path.join(carpeta, "derechos.db")
        _copiar_base(ruta_db)
        with zipfile.ZipFile(destino_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(ruta_db, "derechos.db")
            if upload_dir and os.path.isdir(upload_dir):
                for raiz, _dirs, archivos in os.walk(upload_dir):
                    for nombre in archivos:
                        ruta = os.path.join(raiz, nombre)
                        rel = os.path.relpath(ruta, upload_dir)
                        zf.write(ruta, "uploads/" + rel.replace("\\", "/"))
        return destino_zip
    finally:
        shutil.rmtree(carpeta, ignore_errors=True)


def _extraer_seguro(zf, destino):
    """Extrae el ZIP evitando rutas que se salgan de la carpeta destino."""
    base = os.path.abspath(destino)
    for info in zf.infolist():
        nombre = info.filename.replace("\\", "/")
        if nombre.startswith("/") or ".." in nombre.split("/"):
            continue
        ruta = os.path.abspath(os.path.join(base, nombre))
        if not ruta.startswith(base + os.sep) and ruta != base:
            continue
        if info.is_dir():
            os.makedirs(ruta, exist_ok=True)
            continue
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        with zf.open(info) as origen, open(ruta, "wb") as salida:
            shutil.copyfileobj(origen, salida)


def _validar_base(ruta):
    if not os.path.exists(ruta) or os.path.getsize(ruta) < 1024:
        raise ValueError("El respaldo no trae una base de datos válida.")
    conn = sqlite3.connect(ruta)
    try:
        filas = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name = 'usuarios'").fetchall()
    finally:
        conn.close()
    if not filas:
        raise ValueError("La base del respaldo no parece de Derechos On "
                         "(no tiene la tabla de usuarios).")


def restaurar(ruta_zip, db_path, upload_dir):
    """Reemplaza la base con la del ZIP y mezcla los archivos subidos."""
    if not zipfile.is_zipfile(ruta_zip):
        raise ValueError("El archivo no es un ZIP de respaldo.")
    carpeta = tempfile.mkdtemp(prefix="restaurar-")
    try:
        with zipfile.ZipFile(ruta_zip) as zf:
            _extraer_seguro(zf, carpeta)
        origen_db = os.path.join(carpeta, "derechos.db")
        _validar_base(origen_db)

        marca = datetime.now().strftime("%Y%m%d-%H%M%S")
        copia_previa = "%s.antes-restaurar-%s" % (db_path, marca)
        if os.path.exists(db_path):
            shutil.copy2(db_path, copia_previa)

        # Se copia sobre el archivo existente para conservar permisos y no
        # dejar la base a medio escribir si algo falla.
        shutil.copy2(origen_db, db_path)

        carpeta_uploads = os.path.join(carpeta, "uploads")
        if os.path.isdir(carpeta_uploads) and upload_dir:
            os.makedirs(upload_dir, exist_ok=True)
            for raiz, _dirs, archivos in os.walk(carpeta_uploads):
                for nombre in archivos:
                    origen = os.path.join(raiz, nombre)
                    rel = os.path.relpath(origen, carpeta_uploads)
                    destino = os.path.join(upload_dir, rel)
                    os.makedirs(os.path.dirname(destino), exist_ok=True)
                    shutil.copy2(origen, destino)
        return {"copia_previa": copia_previa}
    finally:
        shutil.rmtree(carpeta, ignore_errors=True)
