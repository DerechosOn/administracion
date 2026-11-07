# -*- coding: utf-8 -*-
"""Punto de entrada WSGI para producción (Gunicorn).

Uso en el VPS:
    gunicorn --bind 127.0.0.1:8000 wsgi:application
"""

import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import db

_db_listo = threading.Event()


def _inicializar():
    try:
        import logging
        logging.info("INICIO: comenzando db.iniciar()")
        db.iniciar()
        logging.info("INICIO: db.iniciar() completado")
    except Exception as exc:
        import logging
        logging.exception("Error inicializando la base de datos: %s", exc)
    finally:
        _db_listo.set()


threading.Thread(target=_inicializar, daemon=True).start()

from app import app  # noqa: E402

@app.before_request
def _esperar_db():
    from flask import request, Response
    if _db_listo.is_set():
        return None
    if request.path == "/":
        return Response("OK", status=200)
    _db_listo.wait(timeout=120)

application = app