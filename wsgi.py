# -*- coding: utf-8 -*-
"""Punto de entrada WSGI para producción (Gunicorn).

Uso en el VPS:
    gunicorn --bind 127.0.0.1:8000 wsgi:application
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import db

db.iniciar()

from app import _retext_contratos, app, arrancar_redes_auto  # noqa: E402

_retext_contratos()
arrancar_redes_auto()

application = app