# -*- coding: utf-8 -*-
"""Punto de entrada WSGI para producción (Gunicorn).

Uso en el VPS:
    gunicorn --bind 127.0.0.1:8000 wsgi:application
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import threading

import db

# La inicializacion (incluida la sincronizacion con Turso) puede tardar mas
# de lo que Render espera para detectar el puerto. Se ejecuta en segundo plano
# para que gunicorn pueda arrancar de inmediato.
_db_listo = threading.Event()


def _inicializar():
    try:
        db.iniciar()
        from app import _retext_contratos, arrancar_redes_auto
        _retext_contratos()
        arrancar_redes_auto()
    except Exception as exc:
        import logging
        logging.exception("Error inicializando la base de datos: %s", exc)
    finally:
        _db_listo.set()


threading.Thread(target=_inicializar, daemon=True).start()

from app import app  # noqa: E402

# Espera breve a la inicializacion antes de atender peticiones.
@app.before_request
def _esperar_db():
    if not _db_listo.is_set():
        _db_listo.wait(timeout=120)

application = app