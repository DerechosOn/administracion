# -*- coding: utf-8 -*-
"""Conexión y esquema de base de datos SQLite para Derechos On."""

import os
import json
import sqlite3
from datetime import datetime

from werkzeug.security import generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "derechos.db")

ESTADOS_PROCESO = [
    "Trámite inicial",
    "En estudio",
    "Audiencia programada",
    "En apelación",
    "Resuelto a favor",
    "Resuelto en contra",
    "Archivado",
]

ERRORES_ACCION = 0  # usuario inactivo
ERRORES_DUPLICADO = 1
ERRORES_NO_EXISTE = 2


def conectar():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def iniciar():
    conn = conectar()
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            rol TEXT NOT NULL DEFAULT 'cliente',
            telefono TEXT DEFAULT '',
            documento TEXT DEFAULT '',
            tipo_servicio TEXT DEFAULT '',
            datos_extra TEXT DEFAULT NULL,
            tipo_persona TEXT DEFAULT 'natural',
            activo INTEGER NOT NULL DEFAULT 1,
            fecha_registro TEXT NOT NULL,
            ultima_sesion TEXT DEFAULT NULL
        );

        CREATE TABLE IF NOT EXISTS procesos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER NOT NULL,
            abogado_id INTEGER DEFAULT NULL,
            titulo TEXT NOT NULL,
            despacho TEXT DEFAULT '',
            descripcion TEXT DEFAULT '',
            tipo TEXT DEFAULT 'Civil',
            estado TEXT NOT NULL DEFAULT 'Trámite inicial',
            fecha_apertura TEXT NOT NULL,
            fecha_actualizacion TEXT NOT NULL,
            notas TEXT DEFAULT '',
            FOREIGN KEY (cliente_id) REFERENCES usuarios (id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS abogados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            especialidad TEXT DEFAULT '',
            correo TEXT DEFAULT '',
            telefono TEXT DEFAULT '',
            tarjeta_profesional TEXT DEFAULT '',
            activo INTEGER NOT NULL DEFAULT 1,
            fecha_registro TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS expedientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proceso_id INTEGER NOT NULL,
            tipo TEXT NOT NULL DEFAULT 'Documento',
            titulo TEXT NOT NULL,
            descripcion TEXT DEFAULT '',
            fecha TEXT NOT NULL,
            FOREIGN KEY (proceso_id) REFERENCES procesos (id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS actuaciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proceso_id INTEGER NOT NULL,
            fecha TEXT NOT NULL,
            fecha_maxima TEXT DEFAULT '',
            descripcion TEXT DEFAULT '',
            creado_el TEXT NOT NULL,
            FOREIGN KEY (proceso_id) REFERENCES procesos (id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS anotaciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proceso_id INTEGER NOT NULL,
            abogado_id INTEGER DEFAULT NULL,
            texto TEXT NOT NULL,
            creado_el TEXT NOT NULL,
            FOREIGN KEY (proceso_id) REFERENCES procesos (id) ON DELETE CASCADE,
            FOREIGN KEY (abogado_id) REFERENCES abogados (id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS correo_config (
            abogado_id INTEGER PRIMARY KEY,
            servidor_imap TEXT NOT NULL DEFAULT 'imap.hostinger.com',
            puerto_imap INTEGER NOT NULL DEFAULT 993,
            servidor_smtp TEXT NOT NULL DEFAULT 'smtp.hostinger.com',
            puerto_smtp INTEGER NOT NULL DEFAULT 465,
            correo TEXT DEFAULT '',
            clave TEXT DEFAULT '',
            activo INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (abogado_id) REFERENCES abogados (id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS documentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actuacion_id INTEGER NOT NULL,
            nombre_original TEXT NOT NULL,
            archivo TEXT NOT NULL,
            tamano INTEGER NOT NULL DEFAULT 0,
            cargado_el TEXT NOT NULL,
            FOREIGN KEY (actuacion_id) REFERENCES actuaciones (id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS noticias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo TEXT NOT NULL,
            resumen TEXT DEFAULT '',
            contenido TEXT DEFAULT '',
            etiqueta TEXT DEFAULT 'Artículo',
            imagen TEXT DEFAULT '',
            creado_el TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS areas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL UNIQUE,
            descripcion TEXT DEFAULT '',
            icono TEXT DEFAULT 'scale'
        );

        CREATE TABLE IF NOT EXISTS contenido (
            clave TEXT PRIMARY KEY,
            valor TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS secciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo TEXT NOT NULL,
            subtitulo TEXT DEFAULT '',
            contenido TEXT DEFAULT '',
            icono TEXT DEFAULT 'scale',
            activa INTEGER NOT NULL DEFAULT 1,
            posicion INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS contactos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            correo TEXT NOT NULL,
            telefono TEXT DEFAULT '',
            asunto TEXT DEFAULT '',
            mensaje TEXT NOT NULL,
            leido INTEGER NOT NULL DEFAULT 0,
            creado_el TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS citas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            correo TEXT NOT NULL,
            telefono TEXT DEFAULT '',
            abogado_id INTEGER DEFAULT NULL,
            fecha TEXT NOT NULL,
            hora TEXT NOT NULL,
            motivo TEXT DEFAULT '',
            estado TEXT NOT NULL DEFAULT 'Pendiente',
            creado_el TEXT NOT NULL,
            FOREIGN KEY (abogado_id) REFERENCES abogados (id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS testimonios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_nombre TEXT NOT NULL,
            texto TEXT NOT NULL,
            calificacion INTEGER NOT NULL DEFAULT 5,
            activo INTEGER NOT NULL DEFAULT 1,
            cliente_id INTEGER DEFAULT NULL,
            creado_el TEXT NOT NULL,
            FOREIGN KEY (cliente_id) REFERENCES usuarios (id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS notificacion_config (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            servidor_smtp TEXT NOT NULL DEFAULT 'smtp.hostinger.com',
            puerto_smtp INTEGER NOT NULL DEFAULT 465,
            correo TEXT DEFAULT '',
            clave TEXT DEFAULT '',
            destino TEXT DEFAULT '',
            activo INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS actividades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            abogado_id INTEGER NOT NULL,
            titulo TEXT NOT NULL,
            tipo TEXT NOT NULL DEFAULT 'Actividad',
            fecha TEXT NOT NULL,
            hora TEXT NOT NULL,
            hora_fin TEXT NOT NULL,
            descripcion TEXT DEFAULT '',
            creado_el TEXT NOT NULL,
            FOREIGN KEY (abogado_id) REFERENCES abogados (id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS cartera (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER NOT NULL,
            servicio TEXT NOT NULL,
            descripcion TEXT DEFAULT '',
            valor_total REAL NOT NULL DEFAULT 0,
            pagado REAL NOT NULL DEFAULT 0,
            vencimiento TEXT DEFAULT '',
            creado_el TEXT NOT NULL,
            actualizado_el TEXT NOT NULL,
            FOREIGN KEY (cliente_id) REFERENCES usuarios (id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS comprobantes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER NOT NULL,
            cartera_id INTEGER DEFAULT NULL,
            nombre_archivo TEXT NOT NULL,
            archivo TEXT NOT NULL DEFAULT '',
            tamano INTEGER NOT NULL DEFAULT 0,
            importe REAL NOT NULL DEFAULT 0,
            nota TEXT DEFAULT '',
            estado TEXT NOT NULL DEFAULT 'Pendiente',
            cargado_el TEXT NOT NULL,
            validado_el TEXT DEFAULT '',
            validado_por TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (cliente_id) REFERENCES usuarios (id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS formas_pago (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            tipo TEXT NOT NULL DEFAULT 'bancaria',
            beneficiario TEXT DEFAULT '',
            datos TEXT DEFAULT '',
            instrucciones TEXT DEFAULT '',
            activa INTEGER NOT NULL DEFAULT 1,
            orden INTEGER NOT NULL DEFAULT 0,
            creado_el TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS contratos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER NOT NULL,
            numero TEXT NOT NULL DEFAULT '',
            servicio TEXT NOT NULL DEFAULT '',
            ciudad TEXT NOT NULL DEFAULT 'Bogotá D.C.',
            texto TEXT NOT NULL DEFAULT '',
            estado TEXT NOT NULL DEFAULT 'Activo',
            firma_imagen TEXT NOT NULL DEFAULT '',
            firma_nombre TEXT NOT NULL DEFAULT '',
            firmado_el TEXT NOT NULL DEFAULT '',
            creado_el TEXT NOT NULL,
            FOREIGN KEY (cliente_id) REFERENCES usuarios (id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS visitas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sesion TEXT DEFAULT '',
            pagina TEXT DEFAULT '',
            dispositivo TEXT DEFAULT '',
            navegador TEXT DEFAULT '',
            es_vuelta INTEGER NOT NULL DEFAULT 0,
            creado_el TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS interacciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT NOT NULL,
            pagina TEXT DEFAULT '',
            detalle TEXT DEFAULT '',
            sesion TEXT DEFAULT '',
            creado_el TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS publicaciones_redes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plataforma TEXT NOT NULL,
            articulo_id INTEGER DEFAULT NULL,
            url_externa TEXT DEFAULT '',
            estado TEXT NOT NULL DEFAULT 'ok',
            detalle TEXT DEFAULT '',
            creado_el TEXT NOT NULL,
            FOREIGN KEY (articulo_id) REFERENCES noticias (id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS redes_metricas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plataforma TEXT NOT NULL,
            fecha TEXT NOT NULL,
            seguidores INTEGER DEFAULT 0,
            alcance INTEGER DEFAULT 0,
            impresiones INTEGER DEFAULT 0,
            interacciones INTEGER DEFAULT 0,
            notas TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS redes_sync (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ejecutado_el TEXT NOT NULL,
            disparador TEXT NOT NULL DEFAULT 'auto',
            plataformas TEXT DEFAULT '',
            guardadas INTEGER DEFAULT 0,
            errores INTEGER DEFAULT 0,
            detalle TEXT DEFAULT ''
        );

        CREATE INDEX IF NOT EXISTS ix_redes_metricas_plataforma_fecha
            ON redes_metricas (plataforma, fecha);
        """
    )
    conn.commit()
    migrar(conn)
    semilla(conn)
    conn.close()


def migrar(conn):
    cur = conn.cursor()
    columnas = [r[1] for r in cur.execute("PRAGMA table_info(procesos)").fetchall()]
    if "abogado_id" not in columnas:
        cur.execute("ALTER TABLE procesos ADD COLUMN abogado_id INTEGER DEFAULT NULL")
        conn.commit()
        columnas = [r[1] for r in cur.execute("PRAGMA table_info(procesos)").fetchall()]
    if "despacho" not in columnas:
        cur.execute("ALTER TABLE procesos ADD COLUMN despacho TEXT DEFAULT ''")
        conn.commit()

    col_noticias = [r[1] for r in cur.execute("PRAGMA table_info(noticias)").fetchall()]
    if "imagen" not in col_noticias:
        cur.execute("ALTER TABLE noticias ADD COLUMN imagen TEXT DEFAULT ''")
        conn.commit()

    col_actu = [r[1] for r in cur.execute("PRAGMA table_info(actuaciones)").fetchall()]
    if "fecha_maxima" not in col_actu:
        cur.execute("ALTER TABLE actuaciones ADD COLUMN fecha_maxima TEXT DEFAULT ''")
        conn.commit()

    tablas = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()]
    if "comprobantes" in tablas:
        col_comp = [r[1] for r in cur.execute("PRAGMA table_info(comprobantes)").fetchall()]
        if "archivo" not in col_comp:
            cur.execute("ALTER TABLE comprobantes ADD COLUMN archivo TEXT NOT NULL DEFAULT ''")
            conn.commit()
        if "validado_por" not in col_comp:
            cur.execute("ALTER TABLE comprobantes ADD COLUMN validado_por TEXT NOT NULL DEFAULT ''")
            conn.commit()

    if "contratos" in tablas:
        col_con = [r[1] for r in cur.execute("PRAGMA table_info(contratos)").fetchall()]
        for col, tipo in (("firma_imagen", "TEXT NOT NULL DEFAULT ''"),
                          ("firma_nombre", "TEXT NOT NULL DEFAULT ''"),
                          ("firmado_el", "TEXT NOT NULL DEFAULT ''")):
            if col not in col_con:
                cur.execute("ALTER TABLE contratos ADD COLUMN %s %s" % (col, tipo))
                conn.commit()

    col_usu = [r[1] for r in cur.execute("PRAGMA table_info(usuarios)").fetchall()]
    if "tipo_servicio" not in col_usu:
        cur.execute("ALTER TABLE usuarios ADD COLUMN tipo_servicio TEXT NOT NULL DEFAULT ''")
        conn.commit()
    if "datos_extra" not in col_usu:
        cur.execute("ALTER TABLE usuarios ADD COLUMN datos_extra TEXT DEFAULT NULL")
        conn.commit()
    if "tipo_persona" not in col_usu:
        cur.execute("ALTER TABLE usuarios ADD COLUMN tipo_persona TEXT DEFAULT 'natural'")
        conn.commit()

    col_abog = [r[1] for r in cur.execute("PRAGMA table_info(abogados)").fetchall()]
    for col, tipo in (("foto", "TEXT NOT NULL DEFAULT ''"),
                      ("perfil", "TEXT NOT NULL DEFAULT ''")):
        if col not in col_abog:
            cur.execute("ALTER TABLE abogados ADD COLUMN %s %s" % (col, tipo))
            conn.commit()

    col_test = [r[1] for r in cur.execute("PRAGMA table_info(testimonios)").fetchall()]
    if "cliente_id" not in col_test:
        cur.execute("ALTER TABLE testimonios ADD COLUMN cliente_id INTEGER DEFAULT NULL")
        conn.commit()

    cur.execute(
        "CREATE TABLE IF NOT EXISTS anotaciones ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "proceso_id INTEGER NOT NULL,"
        "abogado_id INTEGER DEFAULT NULL,"
        "texto TEXT NOT NULL,"
        "creado_el TEXT NOT NULL,"
        "FOREIGN KEY (proceso_id) REFERENCES procesos (id) ON DELETE CASCADE,"
        "FOREIGN KEY (abogado_id) REFERENCES abogados (id) ON DELETE SET NULL)")

    cur.execute(
        "CREATE TABLE IF NOT EXISTS correo_config ("
        "abogado_id INTEGER PRIMARY KEY,"
        "servidor_imap TEXT NOT NULL DEFAULT 'imap.hostinger.com',"
        "puerto_imap INTEGER NOT NULL DEFAULT 993,"
        "servidor_smtp TEXT NOT NULL DEFAULT 'smtp.hostinger.com',"
        "puerto_smtp INTEGER NOT NULL DEFAULT 465,"
        "correo TEXT DEFAULT '',"
        "clave TEXT DEFAULT '',"
        "activo INTEGER NOT NULL DEFAULT 0,"
        "FOREIGN KEY (abogado_id) REFERENCES abogados (id) ON DELETE CASCADE)")

    # ---- Incentivo al Aprovechamiento de Residuos (IAT) para asociaciones de
    # recicladores: proyectos de aprovechamiento radicados ante la alcaldía.
    cur.execute(
        "CREATE TABLE IF NOT EXISTS iat_solicitudes ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "usuario_id INTEGER NOT NULL,"
        "radicado TEXT NOT NULL UNIQUE,"
        "titulo TEXT NOT NULL,"
        "tipo TEXT NOT NULL DEFAULT 'Aprovechamiento',"
        "descripcion TEXT NOT NULL,"
        "toneladas REAL DEFAULT 0,"
        "municipio TEXT DEFAULT '',"
        "estado TEXT NOT NULL DEFAULT 'Radicado',"
        "observaciones TEXT DEFAULT '',"
        "datos TEXT DEFAULT '',"
        "fecha_radicado TEXT NOT NULL,"
        "modificado_el TEXT DEFAULT NULL,"
        "creado_el TEXT NOT NULL,"
        "FOREIGN KEY (usuario_id) REFERENCES usuarios (id) ON DELETE CASCADE)")

    # Compatibilidad con bases creadas antes de la columna `datos`.
    try:
        cols = [f["name"] for f in cur.execute("PRAGMA table_info(iat_solicitudes)").fetchall()]
    except Exception:
        cols = []
    if cols and "datos" not in cols:
        cur.execute("ALTER TABLE iat_solicitudes ADD COLUMN datos TEXT DEFAULT ''")

    cur.execute(
        "UPDATE contenido SET valor = ? WHERE clave = 'noticias_titulo' AND (valor = ? OR valor = '')",
        ("Artículos jurídicos", "Noticias y novedades"))
    conn.commit()

    # La información de contacto de la barra superior y el pie solo aparece
    # cuando se configura desde el portal administrativo, no con valores por defecto.
    viejos_contacto = (
        ("contacto_correo", "contacto@derechoson.co"),
        ("contacto_telefono", "+57 300 123 4567"),
        ("contacto_direccion", "Carrera 15 # 80-40, Bogotá"),
        ("contacto_horario", "Lun a Vie · 8:00 am – 6:00 pm"),
    )
    for clave, default_viejo in viejos_contacto:
        cur.execute("DELETE FROM contenido WHERE clave = ? AND valor = ?", (clave, default_viejo))
    conn.commit()

    cur.execute(
        "CREATE TABLE IF NOT EXISTS prospectos ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "nombre TEXT NOT NULL,"
        "tipo TEXT NOT NULL DEFAULT 'natural',"
        "documento TEXT DEFAULT '',"
        "sector TEXT DEFAULT '',"
        "naturaleza TEXT DEFAULT '',"
        "fuente TEXT NOT NULL DEFAULT 'Manual',"
        "consulta_origen TEXT DEFAULT '',"
        "correo TEXT DEFAULT '',"
        "telefono TEXT DEFAULT '',"
        "sitio_web TEXT DEFAULT '',"
        "score INTEGER NOT NULL DEFAULT 0,"
        "estado TEXT NOT NULL DEFAULT 'Nuevo',"
        "propuesta TEXT DEFAULT '',"
        "creado_el TEXT NOT NULL)")
    cur.execute(
        "CREATE TABLE IF NOT EXISTS busquedas_agente ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "texto TEXT NOT NULL,"
        "fuentes TEXT DEFAULT '',"
        "resultado TEXT DEFAULT 'Pendiente por importar',"
        "nro_resultados INTEGER NOT NULL DEFAULT 0,"
        "creado_el TEXT NOT NULL)")
    conn.commit()

    col_pros = [r[1] for r in cur.execute("PRAGMA table_info(prospectos)").fetchall()]
    for col in ("representante_legal", "domicilio", "direccion"):
        if col not in col_pros:
            cur.execute("ALTER TABLE prospectos ADD COLUMN %s TEXT DEFAULT ''" % col)
            conn.commit()
    col_busq = [r[1] for r in cur.execute("PRAGMA table_info(busquedas_agente)").fetchall()]
    if "detalle" not in col_busq:
        cur.execute("ALTER TABLE busquedas_agente ADD COLUMN detalle TEXT DEFAULT ''")
        conn.commit()

    # Servicios que el usuario crea cuando NO estan en el tarifario de CONALBOS.
    # Viven en la base (no en el .py) para no perderse al actualizar el sistema.
    cur.execute(
        "CREATE TABLE IF NOT EXISTS tarifario_extra ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "numero TEXT NOT NULL,"
        "servicio TEXT NOT NULL,"
        "area TEXT DEFAULT '',"
        "area_numero TEXT DEFAULT '',"
        "smmlv REAL DEFAULT NULL,"
        "valor REAL NOT NULL DEFAULT 0,"
        "nota TEXT DEFAULT '',"
        "fuente TEXT DEFAULT '',"
        "estudio TEXT DEFAULT '',"
        "creado_el TEXT NOT NULL)")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_tarifario_extra_numero ON tarifario_extra (numero)")
    conn.commit()

    col_extra = [r[1] for r in cur.execute("PRAGMA table_info(tarifario_extra)").fetchall()]
    for col, tipo in (("estudio", "TEXT DEFAULT ''"),
                      ("area_numero", "TEXT DEFAULT ''"),
                      ("fuente", "TEXT DEFAULT ''")):
        if col not in col_extra:
            cur.execute("ALTER TABLE tarifario_extra ADD COLUMN %s %s" % (col, tipo))
            conn.commit()

    # Areas del derecho que crea el despacho y que NO existen en CONALBOS
    # (Derecho de Datos, Compliance, Derecho Deportivo...). Se les asigna una
    # raiz numerica propia, continuando despues de la 23, para que sus items
    # queden como 24.1, 24.2 y no se confundan con los oficiales.
    cur.execute(
        "CREATE TABLE IF NOT EXISTS tarifario_area ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "numero TEXT NOT NULL UNIQUE,"
        "nombre TEXT NOT NULL,"
        "color TEXT DEFAULT '',"
        "creado_el TEXT NOT NULL)")
    conn.commit()

    # Marketing digital: historial de auditorias de posicionamiento (buscadores
    # y redes) con su puntaje, para ver la evolucion entre fechas.
    cur.execute(
        "CREATE TABLE IF NOT EXISTS marketing_analisis ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "objetivo TEXT NOT NULL,"
        "url TEXT NOT NULL,"
        "tipo TEXT NOT NULL DEFAULT 'url',"
        "puntaje INTEGER DEFAULT 0,"
        "motores TEXT DEFAULT '',"
        "redes TEXT DEFAULT '',"
        "tecnico TEXT DEFAULT '',"
        "contenido TEXT DEFAULT '',"
        "resumen TEXT DEFAULT '',"
        "consejos TEXT DEFAULT '',"
        "ia INTEGER DEFAULT 0,"
        "creado_el TEXT NOT NULL)")
    columnas_mk = [r[1] for r in cur.execute(
        "PRAGMA table_info(marketing_analisis)").fetchall()]
    if "contenido" not in columnas_mk:
        cur.execute("ALTER TABLE marketing_analisis ADD COLUMN contenido TEXT DEFAULT ''")
    conn.commit()

    # ---- Motor normativo y jurisprudencial de la sección "Base jurídica".
    # `motor_fuentes` guarda las páginas oficiales que se vigilan; `motor_normas`
    # es el catálogo de normas y providencias (descubiertas por el motor o
    # cargadas a mano) con su estado de revisión.
    cur.execute(
        "CREATE TABLE IF NOT EXISTS motor_fuentes ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "nombre TEXT NOT NULL,"
        "tipo TEXT NOT NULL DEFAULT 'norma',"
        "area TEXT DEFAULT '',"
        "url TEXT NOT NULL,"
        "activo INTEGER NOT NULL DEFAULT 1,"
        "huella TEXT DEFAULT '',"
        "ultimo_cambio TEXT DEFAULT NULL,"
        "ultima_revision TEXT DEFAULT NULL,"
        "novedades INTEGER NOT NULL DEFAULT 0,"
        "ultimo_error TEXT DEFAULT '',"
        "creado_el TEXT NOT NULL)")
    cur.execute(
        "CREATE TABLE IF NOT EXISTS motor_normas ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "titulo TEXT NOT NULL,"
        "tipo TEXT NOT NULL DEFAULT 'norma',"
        "categoria TEXT DEFAULT '',"
        "emisor TEXT DEFAULT '',"
        "numero TEXT DEFAULT '',"
        "fecha TEXT DEFAULT '',"
        "area TEXT DEFAULT '',"
        "url TEXT DEFAULT '',"
        "resumen TEXT DEFAULT '',"
        "fuente_id INTEGER DEFAULT NULL,"
        "origen TEXT NOT NULL DEFAULT 'manual',"
        "estado TEXT NOT NULL DEFAULT 'pendiente',"
        "creado_el TEXT NOT NULL,"
        "FOREIGN KEY (fuente_id) REFERENCES motor_fuentes (id) ON DELETE SET NULL)")
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_motor_normas_url "
        "ON motor_normas (url) WHERE url <> ''")
    fuentes = [r[0] for r in cur.execute("SELECT COUNT(*) FROM motor_fuentes").fetchall()]
    if fuentes and fuentes[0] == 0:
        _sembrar_fuentes(cur)
    conn.commit()


def _sembrar_fuentes(cur):
    """Fuentes oficiales del tema IAT que el motor vigila por defecto."""
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M")
    cur.executemany(
        "INSERT INTO motor_fuentes (nombre, tipo, area, url, activo, creado_el) "
        "VALUES (?, ?, ?, ?, 1, ?)",
        [
            ("MinVivienda · Normativa de agua, saneamiento y aprovechamiento (MVCT)",
             "norma", "IAT · Nacional",
             "https://minvivienda.gov.co/normativa", ahora),
            ("UAESP Bogotá · Normatividad de aprovechamiento y recicladores",
             "norma", "IAT · Bogotá",
             "https://www.uaesp.gov.co/transparencia/normatividad", ahora),
            ("Corte Constitucional · Relatoría (recicladores y aprovechamiento)",
             "jurisprudencia", "IAT · Recicladores",
             "https://www.corteconstitucional.gov.co/relatoria/", ahora),
            ("Diario Oficial · Imprenta Nacional (nuevas ediciones)",
             "norma", "IAT · General",
             "https://www.imprenta.gov.co/diario-oficial", ahora),
            ("Función Pública · Gestor Normativo (decretos y resoluciones)",
             "norma", "IAT · General",
             "https://www.funcionpublica.gov.co/", ahora),
        ])


def semilla(conn):
    cur = conn.cursor()
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M")

    cur.execute("SELECT COUNT(*) FROM usuarios WHERE rol = 'admin'")
    if cur.fetchone()[0] == 0:
        cur.execute(
            "INSERT INTO usuarios (nombre, email, password_hash, rol, activo, fecha_registro) VALUES (?, ?, ?, ?, 1, ?)",
            ("Administración Derechos On", "admin@derechos.on",
             generate_password_hash("Admin#Derechos2026!"), "admin", ahora),
        )

    cur.execute("SELECT COUNT(*) FROM areas")
    if cur.fetchone()[0] == 0:
        cur.executemany(
            "INSERT INTO areas (nombre, descripcion, icono) VALUES (?, ?, ?)",
            [
                ("Derecho Civil", "Contratos, responsabilidad civil, sucesiones e inmuebles.",
                 "book"),
                ("Derecho de Familia", "Divorcios, custodia, alimentos y sucesiones familiares.",
                 "users"),
                ("Derecho Laboral", "Contratos de trabajo, despidos, pensiones y riesgos laborales.",
                 "briefcase"),
                ("Derecho Penal", "Defensa penal, víctimas y asesoría en procesos penales.",
                 "gavel"),
                ("Derecho Comercial", "Constitución de sociedades, contratos mercantiles e insolvencia.",
                 "chart"),
                ("Derecho Administrativo", "Actuaciones frente a entidades públicas y nulidades.",
                 "building"),
            ],
        )

    _sembrar_contenido(cur)

    conn.commit()


def _sembrar_contenido(cur):
    """Valores por defecto de los textos editables de la página."""
    claves = {r[0] for r in cur.execute("SELECT clave FROM contenido").fetchall()}
    defaults = {
        "hero1_titulo": "Tu defensa jurídica, transparente y siempre a la mano",
        "hero1_texto": "Acompañamos a personas, familias y empresas. Regístrate y consulta en tiempo real el estado de cada uno de tus procesos desde tu página personal.",
        "hero2_titulo": "Consulta el estado de tus procesos en tiempo real",
        "hero2_texto": "Cada cliente tiene su propia página con el estado de cada caso, notas del equipo, expedientes y el abogado asignado. Sin llamadas de espera, sin dudas.",
        "hero3_titulo": "Especialistas en derecho de familia, laboral y civil",
        "hero3_texto": "Áreas de atención integrales con abogados colegiados y experiencia comprobada en cada rama del derecho.",
        "quienes_titulo": "Un despacho que entiende que la justicia también puede ser digital",
        "quienes_texto": "Derechos On nació para acercar la justicia a las personas. Nuestro equipo combina más de dos décadas de litigio con tecnología moderna para que cada cliente sepa, en todo momento, qué está pasando con su caso.",
        "quienes_texto2": "Comunicación clara, honorarios transparentes y seguimiento permanente. Por eso cada cliente tiene su propia página para consultar el estado de sus procesos.",
        "areas_titulo": "Especialidades jurídicas",
        "areas_sub": "Contamos con un equipo multidisciplinario para atender cada necesidad legal con precisión.",
        "abogados_titulo": "Los abogados a tu servicio",
        "abogados_sub": "Profesionales colegiados en cada rama del derecho.",
        "digital_titulo": "Todo tu caso desde tu dispositivo",
        "digital_texto": "Consulta el estado de tus procesos, lee las notas de tu abogado y revisa los expedientes de tu caso desde cualquier lugar, a cualquier hora.",
        "noticias_titulo": "Artículos jurídicos",
        "noticias_sub": "Información legal relevante para que estés al día con los cambios que te afectan.",
        "contacto_titulo": "Canales de atención",
        "contacto_sub": "Estamos disponibles para resolver tus dudas y agendar tu primera consulta.",
        "footer_desc": "Acompañamiento jurídico cercano, transparente y al día. Consulta el estado de tus procesos en tiempo real desde cualquier dispositivo.",
        "portal_mensaje": "Estos son los procesos que tenemos a tu cargo. El estado se actualiza automáticamente cuando nuestro equipo avanza tu caso.",
        "portal_aviso": "",
        "testimonios_titulo": "Lo que dicen nuestros clientes",
        "testimonios_sub": "Experiencias reales de quienes han confiado en Derechos On.",
        "contacto_form_titulo": "Escríbenos",
        "contacto_form_sub": "Cuéntanos tu caso y te contactaremos en menos de 24 horas hábiles.",
        "agendar_titulo": "Agenda tu primera consulta",
        "faq_titulo": "Preguntas frecuentes",
        "faq_sub": "Resolvemos las dudas más comunes antes de iniciar tu trámite.",
        "faq1_p": "¿La primera consulta tiene costo?",
        "faq1_r": "La primera asesoría tiene un valor preferencial y la información que compartas es confidencial.",
        "faq2_p": "¿Puedo consultar el estado de mi proceso en línea?",
        "faq2_r": "Sí. Cada cliente tiene su propio portal donde puede ver el estado, notas y expedientes.",
        "faq3_p": "¿Qué puedo agendar por la página?",
        "faq3_r": "Puedes agendar una cita de asesoría con un abogado. La agenda se confirma por correo.",
        "faq4_p": "¿Cómo se manejan mis datos personales?",
        "faq4_r": "Aplicamos la Ley 1581 de 2012. Consulta nuestra política de privacidad para más detalle.",
        "faq5_p": "¿Atienden de forma presencial y virtual?",
        "faq5_r": "Sí, ofrecemos atención presencial en nuestra oficina y virtual por videollamada y correo.",
        "iat_marco_normativo_html": """<h3 style="font-size:1.15rem;margin-bottom:10px">Marco normativo del IAT</h3>
<div class="table-wrap" style="max-width:860px">
  <table>
    <thead>
      <tr><th style="width:210px">Norma</th><th>Contenido</th></tr>
    </thead>
    <tbody>
      <tr><td><b>Ley 1753 de 2015, art. 88</b></td><td>Crea el IAT con cargo a la tarifa del servicio de aseo.</td></tr>
      <tr><td><b>Decreto 1077 de 2015, arts. 2.3.2.7.10 y 2.3.2.7.11</b></td><td>El municipio o distrito evalúa los proyectos de aprovechamiento presentados por los prestadores; en el parágrafo 1 del art. 2.3.2.7.11 se ordena una <b>evaluación diferencial para recicladores de oficio en proceso de formalización</b>.</td></tr>
      <tr><td><b>Decreto 2412 de 2018</b></td><td>Adicionó el capítulo del IAT al Decreto 1077 de 2015.</td></tr>
      <tr><td><b>Decreto 802 de 2022, art. 2.3.2.7.9</b></td><td>Reglamenta el IAT: los proyectos se radican ante la Secretaría General de la Alcaldía con las condiciones y requisitos del capítulo; sustituyó el capítulo 7 del Decreto 1077 de 2015.</td></tr>
      <tr><td><b>Resolución 547 de 2022 del MVCT</b></td><td>Criterios de elegibilidad de los proyectos (reemplazó la Resolución 176 de 2020).</td></tr>
    </tbody>
  </table>
</div>""",
        "iat_jurisprudencia_html": """<h3 style="font-size:1.15rem;margin-bottom:10px">Jurisprudencia de la Corte Constitucional</h3>
<p class="sub" style="max-width:860px">Línea de tiempo desde la sentencia hito hasta la más reciente. Las decisiones de la Corte han obligado a Bogotá y a los demás municipios a reconocer a los recicladores de oficio como gestores ambientales y sujetos de especial protección, y a garantizar su inclusión remunerada en el servicio de aseo.</p>
<ul class="timeline" style="max-width:860px">
  <li class="tl-item">
    <span class="tl-fecha">T-724 / 2003</span>
    <span class="tl-body"><span class="tl-desc"><b>Sentencia hito.</b> Ordena a Bogotá diseñar e implementar una política pública incluyente y permanente para los recicladores, reconociéndolos como <b>sujetos de especial protección constitucional</b> y como gestores ambientales; dispone acciones afirmativas y un seguimiento permanente. Es el punto de partida de toda la línea jurisprudencial.</span></span>
  </li>
  <li class="tl-item">
    <span class="tl-fecha">C-793 / 2009</span>
    <span class="tl-body"><span class="tl-desc">Exequibilidad condicionada del comparendo ambiental: el destino de los recicladores de oficio depende de la inclusión efectiva y remunerada en la prestación del servicio, no de la sanción a su actividad.</span></span>
  </li>
  <li class="tl-item">
    <span class="tl-fecha">T-291 / 2009</span>
    <span class="tl-body"><span class="tl-desc">Tutela de la Asociación de Recicladores de Navarro (Cali): reitera las órdenes de protección y el deber de vinculación efectiva en el esquema de aseo. Complementada por la T-411 de 2009.</span></span>
  </li>
  <li class="tl-item">
    <span class="tl-fecha">Auto 091 / 2010</span>
    <span class="tl-body"><span class="tl-desc">Asume el cumplimiento de la T-724 de 2003 y <b>suspende la licitación pública</b> que amenazaba la inclusión de los recicladores en el relleno sanitario de Doña Juana.</span></span>
  </li>
  <li class="tl-item">
    <span class="tl-fecha">Auto 268 / 2010</span>
    <span class="tl-body"><span class="tl-desc">Declara el incumplimiento de la licitación 001 de 2010 (barrido y limpieza con inclusión simulada) y reitera las órdenes de la sentencia hito.</span></span>
  </li>
  <li class="tl-item">
    <span class="tl-fecha">Auto 275 / 2011</span>
    <span class="tl-body"><span class="tl-desc">Declara el <b>incumplimiento definitivo</b> y deja sin efectos la licitación 001 de 2011 por no garantizar la inclusión efectiva y remunerada de los recicladores.</span></span>
  </li>
  <li class="tl-item">
    <span class="tl-fecha">Autos 084 / 2012, 366 y 118 / 2014, 587 / 2015</span>
    <span class="tl-body"><span class="tl-desc">Providencias de seguimiento: verifican avances, corrigen la formalización (autocertificación del censo, asociación efectiva) y mantienen la orden de no exclusión.</span></span>
  </li>
  <li class="tl-item">
    <span class="tl-fecha">Auto 736 / 2017</span>
    <span class="tl-body"><span class="tl-desc">Frente a la licitación 002 de 2017 de Bogotá, exige condiciones que garanticen la <b>inclusión real y la remuneración directa</b> de los recicladores según su participación en el censo.</span></span>
  </li>
  <li class="tl-item">
    <span class="tl-fecha">Auto 311 / 2020</span>
    <span class="tl-body"><span class="tl-desc">Rechaza la solicitud de cierre del seguimiento y ordena nuevas verificaciones: persisten falencias en la formalización y en la remuneración efectiva del aprovechamiento.</span></span>
  </li>
  <li class="tl-item">
    <span class="tl-fecha">Auto 1927 / 2022</span>
    <span class="tl-body"><span class="tl-desc">Define que el seguimiento a la T-724 de 2003 sigue vigente y precisa la competencia para continuarlo, manteniendo la supervisión de la política de inclusión.</span></span>
  </li>
  <li class="tl-item">
    <span class="tl-fecha">Auto 1001 / 2023</span>
    <span class="tl-body"><span class="tl-desc">Continúa el seguimiento: constata el cumplimiento parcial de las órdenes y requiere a la administración distrital medidas concretas para el esquema de aprovechamiento.</span></span>
  </li>
  <li class="tl-item">
    <span class="tl-fecha">Auto 2059 / 2025</span>
    <span class="tl-body"><span class="tl-desc"><b>Más reciente.</b> Ante el vencimiento de los contratos del esquema ASE (primera quincena de febrero de 2026), ordena a la CREG adoptar un régimen tarifario transitorio antes del 25 de enero de 2026 y a las autoridades locales garantizar la continuidad operacional y la remuneración efectiva de las organizaciones de recicladores.</span></span>
  </li>
</ul>
<p class="sub" style="max-width:860px;margin-top:6px">Cada una de estas providencias refuerza el principio que rige el IAT y todo el régimen de aprovechamiento: la organización de recicladores de oficio en proceso de formalización debe recibir <b>trato preferente y diferencial</b>, no un requisito adicional para competir en igualdad de condiciones.</p>""",
        "reconocimiento_html": """<div class="notas aviso" style="max-width:860px">
  <b>La Corte Constitucional</b> (sentencia T-724 de 2003 y providencias posteriores) ha declarado a los recicladores de oficio como <b>sujetos de especial protección constitucional</b>, en virtud de su labor como gestores ambientales y de su situación histórica de exclusión. Por eso, el reconocimiento de sus organizaciones debe leerse de forma garantista: las normas de formalización se interpretan y aplican en su favor, no en su contra.
</div>

<section style="margin-top:22px">
  <h3 style="font-size:1.15rem;margin-bottom:10px">1. Nivel nacional: marco constitucional y legal</h3>
  <div class="table-wrap" style="max-width:860px">
    <table>
      <thead>
        <tr><th style="width:230px">Norma</th><th>Contenido</th></tr>
      </thead>
      <tbody>
        <tr><td><b>Constitución Política</b> (arts. 13, 25, 38, 79-80 y 365-370)</td><td>Igualdad material y acciones afirmativas a favor de grupos en condición de debilidad (art. 13); derecho al trabajo (art. 25); libertad de asociación (art. 38); ambiente sano y deber de la Nación de fomentar la educación ambiental (arts. 79-80); el aseo como servicio público a cargo del Estado (arts. 365-370).</td></tr>
        <tr><td><b>Ley 79 de 1988</b></td><td>Régimen de las cooperativas y de las formas asociativas y solidarias de trabajo, base para la constitución de organizaciones sin ánimo de lucro de recicladores.</td></tr>
        <tr><td><b>Ley 142 de 1994, art. 15, numeral 4</b></td><td>Reconoce como prestadores del servicio público de aseo a las <b>organizaciones autorizadas</b> para la prestación de servicios públicos (entre ellas, organizaciones de recicladores), en los términos del artículo 365 de la Constitución.</td></tr>
        <tr><td><b>Decreto 2150 de 1995, arts. 40 a 45</b></td><td>Simplificación de trámites: la <b>personería jurídica de las organizaciones sin ánimo de lucro se obtiene por registro en la Cámara de Comercio</b> (constitución, estatutos, acta de asamblea de constitución y nombramiento de representantes), sin calificación previa del Estado.</td></tr>
        <tr><td><b>Decreto 427 de 1996</b></td><td>Reglamenta el numeral 4 del artículo 15 de la Ley 142 de 1994: requisitos para que las organizaciones autorizadas presten servicios públicos.</td></tr>
        <tr><td><b>Decreto 421 de 2000</b></td><td>Requisitos de las organizaciones solidarias de reciclaje para la prestación de la actividad de comercialización y la inscripción ante la Superintendencia de Servicios Públicos y la Comisión de Regulación de Agua Potable.</td></tr>
        <tr><td><b>Decreto 596 de 2016</b> (adiciona el Cap. 5, Tít. 2, Parte 3 del Decreto 1077 de 2015)</td><td>Régimen <b>transitorio de formalización</b> de los recicladores de oficio como prestadores de la actividad complementaria de aprovechamiento, con registro en el RUOR o instrumento equivalente y censo de recicladores.</td></tr>
        <tr><td><b>Resolución 276 de 2016 del MVCT</b></td><td>Adopta el <b>marco de referencia de la actividad de aprovechamiento</b> y los instrumentos para la transición hacia la formalización de los recicladores de oficio.</td></tr>
        <tr><td><b>Decreto 1345 de 2021</b></td><td>Extiende la progresividad del régimen transitorio de formalización del aprovechamiento (actualiza el Decreto 596 de 2016) a <b>8 años</b>, manteniendo la exclusividad del reciclador de oficio sobre el material aprovechable.</td></tr>
        <tr><td><b>Decreto 1381 de 2024</b></td><td>Nuevo régimen: ratifica la <b>exclusividad del aprovechamiento a favor de las organizaciones de recicladores de oficio por 15 años</b>, exige la verificación de que la organización agrupe al menos el <b>90 % del censo</b> de recicladores del área, y el registro ante la Superintendencia de Servicios Públicos Domiciliarios (SSPD).</td></tr>
        <tr><td><b>Resolución 754 de 2014 del MVCT</b></td><td>Metodología para la formulación, implementación, evaluación, seguimiento, control y actualización de los <b>PGIRS</b>; el PGIRS debe contener el programa de aprovechamiento y la inclusión social de los recicladores de oficio.</td></tr>
        <tr><td><b>CONPES 3871 de 2016</b></td><td>Política nacional para la gestión integral de residuos sólidos: inclusión de los recicladores de oficio en los esquemas de aseo y formalización progresiva.</td></tr>
      </tbody>
    </table>
  </div>
  <p class="sub" style="margin-top:10px">Para ejercer como prestador del servicio público de aseo (actividad de aprovechamiento por comercialización) la organización debe, además, tramitar la <b>personería jurídica</b> (vía Cámara de Comercio), los <b>permisos ambientales y sanitarios</b> (licencia ambiental, concesión de aguas, registro de vertimientos y autorización sanitaria conforme al Decreto 351 de 2014, entre otros) y el <b>registro de prestadores</b> ante la SSPD.</p>
</section>

<section style="margin-top:28px">
  <h3 style="font-size:1.15rem;margin-bottom:10px">2. Nivel departamental</h3>
  <p style="line-height:1.8;max-width:860px">Las gobernaciones no otorgan directamente la personería jurídica de estas organizaciones, pero cumplen un rol clave en el reconocimiento real de los recicladores: adoptan el <b>PGIRS departamental o regional</b>, coordinan los comités departamentales de seguimiento, gestionan los <b>Planes Departamentales de Agua y Saneamiento (PDAS)</b> y apoyan proyectos de formalización e inclusión social. Los programas giran alrededor de tres ejes: censo departamental de recicladores, inclusión social en los esquemas de aseo y fomento de asociaciones de recicladores con enfoque diferencial.</p>
  <p style="line-height:1.8;max-width:860px">Ejemplo verificado: la <b>Gobernación del Quindío</b> ha impulsado la inclusión de recuperadores ambientales dentro de su Plan Departamental de Agua y Saneamiento y sus PGIRS municipales, con pilotos de formalización en municipios como La Tebaida y Génova. Cada departamento, a través de su PGIRS y sus comités, define si sus municipios acogen el proceso de formalización del Decreto 596 de 2016 o el nuevo régimen del Decreto 1381 de 2024.</p>
</section>

<section style="margin-top:28px">
  <h3 style="font-size:1.15rem;margin-bottom:10px">3. Nivel municipal: censo, PGIRS y reconocimiento local</h3>
  <p style="line-height:1.8;max-width:860px">En el municipio es donde ocurre el reconocimiento efectivo. Los requisitos locales se concentran en tres instrumentos: el <b>censo municipal de recicladores</b>, el <b>programa de aprovechamiento e inclusión social del PGIRS</b>, y el <b>registro municipal</b> de las organizaciones y sus integrantes (RUOR distrital donde exista). El municipio conoce el censo (que debe mantenerse actualizado), incorpora el programa de aprovechamiento en el PGIRS y lo armoniza con el esquema de aseo, incluyendo la contratación directa con las organizaciones de recicladores bajo la modalidad de prestación establecida por el Decreto 596 de 2016.</p>
  <div class="table-wrap" style="max-width:860px;margin-top:8px">
    <table>
      <thead>
        <tr><th style="width:230px">Norma / instrumento</th><th>Contenido</th></tr>
      </thead>
      <tbody>
        <tr><td><b>Censo de recicladores + PGIRS</b></td><td>El PGIRS debe contener el programa de aprovechamiento y la inclusión social de los recicladores de oficio; el censo oficial es la base para verificar cuántos recicladores agrupa la organización (el Decreto 1381 de 2024 exige agrupar al menos el 90% del censo).</td></tr>
        <tr><td><b>Bogotá: Resolución 61 de 2013 de la UAESP</b></td><td>Crea el <b>RUOR</b> (Registro Único de Organizaciones de Recicladores) y el censo de integrantes, administrados por la Unidad Administrativa Especial de Servicios Públicos.</td></tr>
        <tr><td><b>Bogotá: Resolución 167 de 2021 de la UAESP</b></td><td>Define los <b>criterios, requisitos e incentivos</b> para la inscripción y permanencia en el RUOR (certificado de Cámara de Comercio, estatutos, acta de constitución, libro de asociados, listado de integrantes del censo activo).</td></tr>
        <tr><td><b>Bogotá: Resolución 504 de 2021 de la UAESP</b></td><td>Criterios para la <b>permanencia</b> de las organizaciones en el RUOR y su seguimiento.</td></tr>
        <tr><td><b>Bogotá: Decreto Distrital 620 de 2017</b></td><td>Adopta el modelo de <b>ASE</b> (Área de Servicio Exclusivo) de aprovechamiento en el Distrito Capital: el servicio de aprovechamiento se presta mediante ASE, contratado exclusivamente con organizaciones de recicladores inscritas en el RUOR, con remuneración al prestador del aseo.</td></tr>
        <tr><td><b>Bogotá: Decreto Distrital 014 de 2023</b></td><td>Reglamenta el servicio público de aseo en la actividad complementaria de aprovechamiento en Bogotá (norma que ha suscitado debates públicos y administrativos; su aplicación debe revisarse con cuidado).</td></tr>
      </tbody>
    </table>
  </div>
</section>

<section style="margin-top:28px;max-width:860px">
  <h3 style="font-size:1.15rem;margin-bottom:10px">Ruta práctica del reconocimiento</h3>
  <ol style="line-height:1.9;padding-left:20px">
    <li><b>Constituir la organización</b>: asamblea de constitución, estatutos, acta de nombramiento del representante legal y acta de asociados; registro en la <b>Cámara de Comercio</b> (Decreto 2150 de 1995, Ley 79 de 1988).</li>
    <li><b>Inscribir la organización y sus integrantes</b> en el registro municipal o distrital (RUOR en Bogotá; censo y registro en el resto del país), verificando que agrupe al menos el <b>90 % del censo</b> formalizado (Decreto 1381 de 2024).</li>
    <li><b>Registrarse ante la SSPD</b> como prestador de la actividad de aprovechamiento, obteniendo el registro definitivo o el tránsito del régimen transitorio del Decreto 596 de 2016 (actualizado por el Decreto 1345 de 2021).</li>
    <li><b>Integrar el programa de aprovechamiento</b> del PGIRS municipal con el censo actualizado y dar cumplimiento a los requisitos ambientales y sanitarios de la operación (Decreto 351 de 2014 y demás aplicables).</li>
    <li><b>Participar en la contratación del servicio</b>: en Bogotá, a través del ASE del Decreto 620 de 2017; en el resto del país, mediante la entrega y formalización establecida en el régimen de aprovechamiento, incluyendo los proyectos IAT (Ley 1753 de 2015, art. 88) para financiar la operación.</li>
  </ol>

  <div class="notas" style="margin-top:16px;background:var(--bg-soft);border-left:3px solid var(--blue-500);padding:10px 14px;border-radius:8px;font-size:.88rem;color:var(--ink)">
    <b>Nota jurisdiccional:</b> ante cualquier exigencia de reconocimiento o formalización, recuerda que la jurisprudencia constitucional (T-724 de 2003 y sus providencias de seguimiento) obliga a las autoridades a aplicar un <b>enfoque diferencial y de acción afirmativa</b> en favor de los recicladores de oficio. Si tu organización enfrenta una decisión desfavorable, en Derechos On te asesoramos para impugnarla dentro de los términos.
  </div>
</section>""",
    }
    for clave, valor in defaults.items():
        if clave not in claves:
            cur.execute("INSERT INTO contenido (clave, valor) VALUES (?, ?)", (clave, valor))


def consultar(sql, params=()):
    conn = conectar()
    try:
        if params:
            return [dict(r) for r in conn.execute(sql, params).fetchall()]
        return [dict(r) for r in conn.execute(sql).fetchall()]
    finally:
        conn.close()


def ejecutar(sql, params=()):
    conn = conectar()
    try:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def usuario_por_email(email):
    filas = consultar("SELECT * FROM usuarios WHERE LOWER(email) = LOWER(?)", (email,))
    return filas[0] if filas else None


def usuario_por_id(uid):
    filas = consultar("SELECT * FROM usuarios WHERE id = ?", (uid,))
    return filas[0] if filas else None


def procesos_de_cliente(cliente_id):
    return consultar(
        "SELECT p.*, a.nombre AS abogado_nombre FROM procesos p "
        "LEFT JOIN abogados a ON a.id = p.abogado_id "
        "WHERE p.cliente_id = ? ORDER BY p.fecha_actualizacion DESC",
        (cliente_id,),
    )


def abogados_lista(activos=None):
    sql = "SELECT * FROM abogados"
    params = ()
    if activos is not None:
        sql += " WHERE activo = ?"
        params = (1 if activos else 0,)
    sql += " ORDER BY nombre"
    return consultar(sql, params)


def abogado_por_id(aid):
    filas = consultar("SELECT * FROM abogados WHERE id = ?", (aid,))
    return filas[0] if filas else None


def abogado_por_correo(correo):
    filas = consultar("SELECT * FROM abogados WHERE LOWER(correo) = LOWER(?)", (correo or "",))
    return filas[0] if filas else None


def abogado_actualizar(aid, cambios):
    if not cambios:
        return
    campos = list(cambios.keys())
    valores = [cambios[c] for c in campos]
    sql = "UPDATE abogados SET %s WHERE id = ?" % ", ".join("%s = ?" % c for c in campos)
    valores.append(aid)
    ejecutar(sql, tuple(valores))


def procesos_de_abogado(abogado_id):
    return consultar(
        "SELECT p.*, u.nombre AS cliente, u.email AS correo_cliente "
        "FROM procesos p JOIN usuarios u ON u.id = p.cliente_id "
        "WHERE p.abogado_id = ? ORDER BY p.fecha_actualizacion DESC", (abogado_id,))


def actuaciones_de_abogado(abogado_id):
    return consultar(
        "SELECT a.*, p.titulo AS proceso, p.estado, p.id AS proceso_id, u.nombre AS cliente, "
        "u.id AS cliente_id "
        "FROM actuaciones a JOIN procesos p ON p.id = a.proceso_id "
        "JOIN usuarios u ON u.id = p.cliente_id "
        "WHERE p.abogado_id = ? ORDER BY a.fecha ASC, a.id ASC", (abogado_id,))


def anotaciones_de_proceso(proceso_id):
    return consultar(
        "SELECT n.*, a.nombre AS abogado_nombre FROM anotaciones n "
        "LEFT JOIN abogados a ON a.id = n.abogado_id "
        "WHERE n.proceso_id = ? ORDER BY n.id DESC", (proceso_id,))


def correo_config_de(abogado_id):
    filas = consultar("SELECT * FROM correo_config WHERE abogado_id = ?", (abogado_id,))
    return filas[0] if filas else None


def correo_config_guardar(abogado_id, datos):
    ejecutar(
        "INSERT INTO correo_config (abogado_id, servidor_imap, puerto_imap, servidor_smtp, puerto_smtp, correo, clave, activo) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 1) "
        "ON CONFLICT(abogado_id) DO UPDATE SET "
        "servidor_imap = excluded.servidor_imap, puerto_imap = excluded.puerto_imap, "
        "servidor_smtp = excluded.servidor_smtp, puerto_smtp = excluded.puerto_smtp, "
        "correo = excluded.correo, clave = excluded.clave, activo = 1",
        (abogado_id, datos["servidor_imap"], datos["puerto_imap"],
         datos["servidor_smtp"], datos["puerto_smtp"], datos["correo"], datos["clave"]))


def correo_config_quitar(abogado_id):
    ejecutar("DELETE FROM correo_config WHERE abogado_id = ?", (abogado_id,))


def expedientes_todos():
    return consultar(
        "SELECT e.*, p.titulo AS proceso, p.estado, u.nombre AS cliente "
        "FROM expedientes e JOIN procesos p ON p.id = e.proceso_id "
        "JOIN usuarios u ON u.id = p.cliente_id "
        "ORDER BY e.fecha DESC, e.id DESC"
    )


def expedientes_de_proceso(proceso_id):
    return consultar(
        "SELECT * FROM expedientes WHERE proceso_id = ? ORDER BY fecha ASC, id ASC",
        (proceso_id,),
    )


def expedientes_de_abogado(abogado_id):
    return consultar(
        "SELECT e.*, p.titulo AS proceso, p.estado, u.nombre AS cliente "
        "FROM expedientes e JOIN procesos p ON p.id = e.proceso_id "
        "JOIN usuarios u ON u.id = p.cliente_id "
        "WHERE p.abogado_id = ? "
        "ORDER BY e.fecha DESC, e.id DESC", (abogado_id,),
    )


def actuaciones_de_proceso(proceso_id):
    return consultar(
        "SELECT * FROM actuaciones WHERE proceso_id = ? ORDER BY fecha ASC, id ASC",
        (proceso_id,),
    )


def actuaciones_todas():
    return consultar(
        "SELECT a.*, p.titulo AS proceso, p.estado, u.nombre AS cliente "
        "FROM actuaciones a JOIN procesos p ON p.id = a.proceso_id "
        "JOIN usuarios u ON u.id = p.cliente_id "
        "ORDER BY a.fecha DESC, a.id DESC"
    )


def documentos_todos():
    return consultar(
        "SELECT d.*, a.proceso_id FROM documentos d "
        "JOIN actuaciones a ON a.id = d.actuacion_id "
        "ORDER BY d.id DESC"
    )


def noticias_recientes(limite=6):
    return consultar(
        "SELECT * FROM noticias ORDER BY id DESC LIMIT ?", (limite,)
    )


def areas_todas():
    return consultar("SELECT * FROM areas ORDER BY nombre")


def contenido_todos():
    try:
        filas = consultar("SELECT clave, valor FROM contenido")
        return {f["clave"]: f["valor"] for f in filas}
    except Exception:
        return {}


def contenido_guardar(cambios):
    conn = conectar()
    try:
        for clave, valor in cambios.items():
            conn.execute(
                "INSERT INTO contenido (clave, valor) VALUES (?, ?) "
                "ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor",
                (clave, valor))
        conn.commit()
    finally:
        conn.close()


def secciones_todas():
    return consultar("SELECT * FROM secciones ORDER BY posicion, id")


def secciones_activas():
    return consultar("SELECT * FROM secciones WHERE activa = 1 ORDER BY posicion, id")


# ---------------------------------------------------------------- contacto
def contacto_crear(datos):
    ejecutar(
        "INSERT INTO contactos (nombre, correo, telefono, asunto, mensaje, creado_el) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (datos["nombre"], datos["correo"], datos.get("telefono", ""),
         datos.get("asunto", ""), datos["mensaje"],
         datetime.now().strftime("%Y-%m-%d %H:%M")))


def contactos_todos(leido=None):
    sql = "SELECT * FROM contactos"
    params = ()
    if leido is not None:
        sql += " WHERE leido = ?"
        params = (1 if leido else 0,)
    sql += " ORDER BY id DESC"
    return consultar(sql, params)


def contacto_estado(cid, leido):
    ejecutar("UPDATE contactos SET leido = ? WHERE id = ?", (1 if leido else 0, cid))


def contacto_eliminar(cid):
    ejecutar("DELETE FROM contactos WHERE id = ?", (cid,))


# ---------------------------------------------------------------- citas
def cita_crear(datos):
    ejecutar(
        "INSERT INTO citas (nombre, correo, telefono, abogado_id, fecha, hora, motivo, estado, creado_el) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 'Pendiente', ?)",
        (datos["nombre"], datos["correo"], datos.get("telefono", ""),
         datos.get("abogado_id"), datos["fecha"], datos["hora"],
         datos.get("motivo", ""), datetime.now().strftime("%Y-%m-%d %H:%M")))


def citas_todas():
    return consultar(
        "SELECT c.*, a.nombre AS abogado_nombre FROM citas c "
        "LEFT JOIN abogados a ON a.id = c.abogado_id "
        "ORDER BY c.fecha ASC, c.hora ASC")


def citas_en_fecha(fecha):
    return consultar(
        "SELECT hora, abogado_id FROM citas WHERE fecha = ? AND estado != 'Cancelada' AND estado != 'Cancelado'",
        (fecha,))


def citas_de_abogado(abogado_id):
    return consultar(
        "SELECT * FROM citas WHERE abogado_id = ? "
        "AND estado != 'Cancelada' AND estado != 'Cancelado' "
        "ORDER BY fecha ASC, hora ASC", (abogado_id,))


def cita_estado(cid, estado):
    ejecutar("UPDATE citas SET estado = ? WHERE id = ?", (estado, cid))


def cita_eliminar(cid):
    ejecutar("DELETE FROM citas WHERE id = ?", (cid,))


# ---------------------------------------------------------------- testimonios
def testimonios_todos(activos=None):
    sql = ("SELECT t.*, u.email AS cliente_email "
           "FROM testimonios t LEFT JOIN usuarios u ON u.id = t.cliente_id")
    params = ()
    if activos is not None:
        sql += " WHERE t.activo = ?"
        params = (1 if activos else 0,)
    sql += " ORDER BY t.id DESC"
    return consultar(sql, params)


def testimonios_activos():
    return consultar("SELECT * FROM testimonios WHERE activo = 1 ORDER BY id DESC")


def testimonio_de_cliente(cliente_id):
    filas = consultar(
        "SELECT * FROM testimonios WHERE cliente_id = ? ORDER BY id DESC LIMIT 1",
        (cliente_id,))
    return filas[0] if filas else None


def testimonio_crear(datos, cliente_id=None):
    """Crea un testimonio.

    Si viene de un cliente (cliente_id), queda inactivo (pendiente de la
    validación del administrador). Los creados por la administración pueden
    marcarse como activos directamente.
    """
    if cliente_id is not None:
        activo = 0
    else:
        activo = 1 if datos.get("activo") == "1" else 0
    ejecutar(
        "INSERT INTO testimonios (cliente_nombre, texto, calificacion, activo, cliente_id, creado_el) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (datos["cliente_nombre"], datos["texto"],
         int(datos.get("calificacion", 5) or 5),
         activo, cliente_id, datetime.now().strftime("%Y-%m-%d %H:%M")))


def testimonio_editar(tid, datos):
    ejecutar(
        "UPDATE testimonios SET cliente_nombre = ?, texto = ?, calificacion = ?, activo = ? WHERE id = ?",
        (datos["cliente_nombre"], datos["texto"],
         int(datos.get("calificacion", 5) or 5),
         1 if datos.get("activo") == "1" else 0, tid))


def testimonio_publicar(tid):
    ejecutar("UPDATE testimonios SET activo = 1 WHERE id = ?", (tid,))


def testimonio_ocultar(tid):
    ejecutar("UPDATE testimonios SET activo = 0 WHERE id = ?", (tid,))


def testimonio_eliminar(tid):
    ejecutar("DELETE FROM testimonios WHERE id = ?", (tid,))


# ---------------------------------------------------------------- notificaciones
def notif_config_de():
    filas = consultar("SELECT * FROM notificacion_config WHERE id = 1")
    return filas[0] if filas else None


def notif_config_guardar(datos):
    ejecutar(
        "INSERT INTO notificacion_config (id, servidor_smtp, puerto_smtp, correo, clave, destino, activo) "
        "VALUES (1, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET "
        "servidor_smtp = excluded.servidor_smtp, puerto_smtp = excluded.puerto_smtp, "
        "correo = excluded.correo, clave = excluded.clave, destino = excluded.destino, "
        "activo = excluded.activo",
        (datos["servidor_smtp"], int(datos.get("puerto_smtp", 465) or 465),
         datos.get("correo", ""), datos.get("clave", ""),
         datos.get("destino", ""), 1 if datos.get("activo") == "1" else 0))


# ---------------------------------------------------------------- actividades del abogado
def actividad_crear(datos):
    ejecutar(
        "INSERT INTO actividades (abogado_id, titulo, tipo, fecha, hora, hora_fin, descripcion, creado_el) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (datos["abogado_id"], datos["titulo"], datos.get("tipo", "Actividad"),
         datos["fecha"], datos["hora"], datos.get("hora_fin", datos["hora"]),
         datos.get("descripcion", ""), datetime.now().strftime("%Y-%m-%d %H:%M")))


def actividades_de_abogado(abogado_id):
    return consultar(
        "SELECT * FROM actividades WHERE abogado_id = ? "
        "ORDER BY fecha ASC, hora ASC", (abogado_id,))


def actividades_en_mes(abogado_id, prefijo):
    return consultar(
        "SELECT * FROM actividades WHERE abogado_id = ? AND fecha LIKE ? "
        "ORDER BY fecha ASC, hora ASC", (abogado_id, prefijo + "%"))


def actividades_en_fecha(fecha):
    return consultar(
        "SELECT * FROM actividades WHERE fecha = ? ORDER BY hora ASC", (fecha,))


def actividad_eliminar(aid):
    ejecutar("DELETE FROM actividades WHERE id = ?", (aid,))


# ---------------------------------------------------------------- cartera
def clientes_todos():
    return consultar(
        "SELECT id, nombre, email FROM usuarios WHERE rol = 'cliente' ORDER BY nombre")


# ------------------------------------------- servicios propios del despacho
def tarifario_extras():
    """Servicios agregados por el usuario que no vienen en el tarifario oficial."""
    return consultar(
        "SELECT * FROM tarifario_extra ORDER BY area_numero, numero")


def tarifario_extra_por_id(tid):
    filas = consultar("SELECT * FROM tarifario_extra WHERE id = ?", (tid,))
    return filas[0] if filas else None


def tarifario_extra_por_numero(numero):
    filas = consultar("SELECT * FROM tarifario_extra WHERE numero = ?", (str(numero).strip(),))
    return filas[0] if filas else None


def tarifario_extra_crear(numero, servicio, valor, area="", area_numero="",
                          smmlv=None, nota="", fuente="", estudio=""):
    cur = conectar().cursor()
    cur.execute(
        "INSERT INTO tarifario_extra (numero, servicio, area, area_numero, smmlv, valor,"
        " nota, fuente, estudio, creado_el) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (str(numero).strip(), str(servicio).strip(), area, str(area_numero or "").strip(),
         smmlv, float(valor or 0), nota, fuente, estudio, _ahora()))
    conn = cur.connection
    conn.commit()
    return cur.lastrowid


def tarifario_extra_actualizar(tid, cambios):
    permitidos = ("numero", "servicio", "area", "area_numero", "smmlv", "valor",
                  "nota", "fuente")
    pares = [(k, v) for k, v in cambios.items() if k in permitidos]
    if not pares:
        return
    set_sql = ", ".join("%s = ?" % k for k, _ in pares)
    ejecutar("UPDATE tarifario_extra SET %s WHERE id = ?" % set_sql,
             tuple(v for _, v in pares) + (tid,))


def tarifario_extra_eliminar(tid):
    ejecutar("DELETE FROM tarifario_extra WHERE id = ?", (tid,))


# ------------------------------------- areas del derecho propias del despacho

def tarifario_areas():
    """Areas propias creadas por el despacho, ordenadas por raiz numerica."""
    return consultar("SELECT * FROM tarifario_area ORDER BY "
                     "CAST(numero AS INTEGER), nombre")


def tarifario_area_por_id(aid):
    filas = consultar("SELECT * FROM tarifario_area WHERE id = ?", (aid,))
    return filas[0] if filas else None


def tarifario_area_por_numero(numero):
    filas = consultar("SELECT * FROM tarifario_area WHERE numero = ?",
                      (str(numero).strip(),))
    return filas[0] if filas else None


def tarifario_area_crear(numero, nombre, color=""):
    cur = conectar().cursor()
    cur.execute(
        "INSERT INTO tarifario_area (numero, nombre, color, creado_el) "
        "VALUES (?,?,?,?)",
        (str(numero).strip(), nombre.strip(), (color or "").strip(), _ahora()))
    conn = cur.connection
    conn.commit()
    return cur.lastrowid


def tarifario_area_eliminar(aid):
    ejecutar("DELETE FROM tarifario_area WHERE id = ?", (aid,))


def cartera_todas():
    return consultar(
        "SELECT c.*, u.nombre AS cliente, u.email AS correo_cliente "
        "FROM cartera c JOIN usuarios u ON u.id = c.cliente_id "
        "ORDER BY c.vencimiento ASC, c.id DESC")


def cartera_de_cliente(cliente_id):
    return consultar(
        "SELECT * FROM cartera WHERE cliente_id = ? ORDER BY vencimiento ASC, id DESC",
        (cliente_id,))


def cartera_crear(datos):
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M")
    return ejecutar(
        "INSERT INTO cartera (cliente_id, servicio, descripcion, valor_total, pagado, "
        "vencimiento, creado_el, actualizado_el) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (datos["cliente_id"], datos["servicio"], datos.get("descripcion", ""),
         float(datos.get("valor_total", 0) or 0), float(datos.get("pagado", 0) or 0),
         datos.get("vencimiento", ""), ahora, ahora))


def cartera_editar(cid, datos):
    ejecutar(
        "UPDATE cartera SET servicio = ?, descripcion = ?, valor_total = ?, pagado = ?, "
        "vencimiento = ?, actualizado_el = ? WHERE id = ?",
        (datos["servicio"], datos.get("descripcion", ""),
         float(datos.get("valor_total", 0) or 0), float(datos.get("pagado", 0) or 0),
         datos.get("vencimiento", ""), datetime.now().strftime("%Y-%m-%d %H:%M"), cid))


def cartera_eliminar(cid):
    ejecutar("DELETE FROM cartera WHERE id = ?", (cid,))


# ---------------------------------------------------------------- comprobantes de pago
def comprobante_crear(datos):
    return ejecutar(
        "INSERT INTO comprobantes (cliente_id, cartera_id, nombre_archivo, archivo, tamano, importe, nota, "
        "estado, cargado_el, validado_el) VALUES (?, ?, ?, ?, ?, ?, ?, 'Pendiente', ?, '')",
        (datos["cliente_id"], datos.get("cartera_id"), datos["nombre_archivo"],
         datos.get("archivo", ""), datos.get("tamano", 0),
         float(datos.get("importe", 0) or 0),
         datos.get("nota", ""), datetime.now().strftime("%Y-%m-%d %H:%M")))


def comprobante_por_id(cid):
    filas = consultar("SELECT * FROM comprobantes WHERE id = ?", (cid,))
    return filas[0] if filas else None


def comprobantes_de_cliente(cliente_id):
    return consultar(
        "SELECT cp.*, c.servicio FROM comprobantes cp "
        "LEFT JOIN cartera c ON c.id = cp.cartera_id "
        "WHERE cp.cliente_id = ? ORDER BY cp.id DESC", (cliente_id,))


def comprobantes_todos():
    return consultar(
        "SELECT cp.*, u.nombre AS cliente, u.email AS correo_cliente, c.servicio AS servicio "
        "FROM comprobantes cp JOIN usuarios u ON u.id = cp.cliente_id "
        "LEFT JOIN cartera c ON c.id = cp.cartera_id "
        "ORDER BY cp.estado = 'Pendiente' DESC, cp.id DESC")


def comprobante_estado(cid, estado, validado_por=""):
    sella = estado in ("Validado", "Rechazado")
    ejecutar(
        "UPDATE comprobantes SET estado = ?, validado_el = ?, validado_por = ? WHERE id = ?",
        (estado,
         datetime.now().strftime("%Y-%m-%d %H:%M") if sella else "",
         validado_por if sella else "",
         cid))


# ---------------------------------------------------------------- formas de pago
def forma_pago_crear(datos):
    return ejecutar(
        "INSERT INTO formas_pago (nombre, tipo, beneficiario, datos, instrucciones, activa, orden, creado_el) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (datos["nombre"], datos.get("tipo", "bancaria") or "bancaria",
         datos.get("beneficiario", ""), datos.get("datos", ""),
         datos.get("instrucciones", ""),
         1 if datos.get("activa") in (1, "1", True) else 0,
         int(datos.get("orden", 0) or 0),
         datetime.now().strftime("%Y-%m-%d %H:%M")))


def forma_pago_por_id(fpid):
    filas = consultar("SELECT * FROM formas_pago WHERE id = ?", (fpid,))
    return filas[0] if filas else None


def formas_pago_lista(solo_activas=False):
    sql = "SELECT * FROM formas_pago"
    if solo_activas:
        sql += " WHERE activa = 1"
    sql += " ORDER BY orden ASC, id ASC"
    return consultar(sql)


def forma_pago_actualizar(fpid, cambios):
    if not cambios:
        return
    ejc = ", ".join("%s = ?" % k for k in cambios)
    ejecutar("UPDATE formas_pago SET %s WHERE id = ?" % ejc,
             list(cambios.values()) + [fpid])


def forma_pago_eliminar(fpid):
    ejecutar("DELETE FROM formas_pago WHERE id = ?", (fpid,))


# ---------------------------------------------------------------- contratos electrónicos
def contrato_crear(datos):
    return ejecutar(
        "INSERT INTO contratos (cliente_id, numero, servicio, ciudad, texto, estado, creado_el) "
        "VALUES (?, ?, ?, ?, ?, 'Activo', ?)",
        (datos["cliente_id"], datos.get("numero", ""), datos.get("servicio", ""),
         datos.get("ciudad", "Bogotá D.C."), datos.get("texto", ""),
         datetime.now().strftime("%Y-%m-%d %H:%M")))


def contrato_actualizar(cid, datos):
    ejc = ", ".join("%s = ?" % k for k in datos)
    ejecutar("UPDATE contratos SET %s WHERE id = ?" % ejc,
             list(datos.values()) + [cid])


# ---------------------------------------------------------------- agente comercial
def prospecto_crear(datos):
    return ejecutar(
        "INSERT INTO prospectos (nombre, tipo, documento, sector, naturaleza, fuente, "
        "consulta_origen, correo, telefono, sitio_web, representante_legal, domicilio, "
        "direccion, score, estado, propuesta, creado_el) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (datos["nombre"], datos.get("tipo", "natural") or "natural",
         datos.get("documento", ""), datos.get("sector", ""),
         datos.get("naturaleza", ""), datos.get("fuente", "Manual") or "Manual",
         datos.get("consulta_origen", ""), datos.get("correo", ""),
         datos.get("telefono", ""), datos.get("sitio_web", ""),
         datos.get("representante_legal", ""), datos.get("domicilio", ""),
         datos.get("direccion", ""),
         datos.get("score", 0) or 0, datos.get("estado", "Nuevo") or "Nuevo",
         datos.get("propuesta", ""), datetime.now().strftime("%Y-%m-%d %H:%M")))


def prospecto_actualizar(pid, cambios):
    if not cambios:
        return
    ejc = ", ".join("%s = ?" % k for k in cambios)
    ejecutar("UPDATE prospectos SET %s WHERE id = ?" % ejc,
             list(cambios.values()) + [pid])


def prospecto_por_id(pid):
    filas = consultar("SELECT * FROM prospectos WHERE id = ?", (pid,))
    return filas[0] if filas else None


def prospectos_lista(tipo=None, fuente=None, estado=None, q=None):
    sql = "SELECT * FROM prospectos WHERE 1 = 1"
    params = []
    if tipo:
        sql += " AND tipo = ?"
        params.append(tipo)
    if fuente:
        sql += " AND fuente = ?"
        params.append(fuente)
    if estado:
        sql += " AND estado = ?"
        params.append(estado)
    if q:
        sql += (" AND (nombre LIKE ? OR documento LIKE ? OR sector LIKE ? OR naturaleza LIKE ? "
                "OR correo LIKE ? OR representante_legal LIKE ? OR domicilio LIKE ? OR direccion LIKE ?)")
        like = "%%%s%%" % q
        params.extend([like] * 8)
    sql += " ORDER BY score DESC, id DESC"
    return consultar(sql, tuple(params))


def prospecto_eliminar(pid):
    ejecutar("DELETE FROM prospectos WHERE id = ?", (pid,))


def busqueda_agente_crear(texto, fuentes):
    return ejecutar(
        "INSERT INTO busquedas_agente (texto, fuentes, resultado, nro_resultados, creado_el) "
        "VALUES (?, ?, 'Pendiente por importar', 0, ?)",
        (texto, fuentes, datetime.now().strftime("%Y-%m-%d %H:%M")))


def busquedas_agente_lista(limite=30):
    return consultar("SELECT * FROM busquedas_agente ORDER BY id DESC LIMIT %d" % (limite or 30))


def busqueda_agente_por_id(bid):
    filas = consultar("SELECT * FROM busquedas_agente WHERE id = ?", (bid,))
    return filas[0] if filas else None


def busquedas_agente_limpiar(personas=False):
    """Limpia el historial del motor: personas (prefijo 'Personas |') o empresas."""
    if personas:
        return ejecutar("DELETE FROM busquedas_agente WHERE fuentes LIKE 'Personas |%'")
    return ejecutar("DELETE FROM busquedas_agente WHERE fuentes NOT LIKE 'Personas |%'")


def contrato_por_id(cid):
    filas = consultar(
        "SELECT ct.*, u.nombre AS cliente_nombre, u.email, u.documento, u.telefono, u.tipo_servicio "
        "FROM contratos ct JOIN usuarios u ON u.id = ct.cliente_id WHERE ct.id = ?", (cid,))
    return filas[0] if filas else None


def contratos_de_cliente(cliente_id):
    return consultar(
        "SELECT * FROM contratos WHERE cliente_id = ? ORDER BY id DESC", (cliente_id,))


# ---------------------------------------------------------------- telemetría

def _ahora():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def visita_crear(sesion, pagina, dispositivo, navegador, es_vuelta):
    return ejecutar(
        "INSERT INTO visitas (sesion, pagina, dispositivo, navegador, es_vuelta, creado_el) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (sesion, pagina, dispositivo, navegador, 1 if es_vuelta else 0, _ahora()))


def interaccion_crear(tipo, detalle="", pagina="", sesion=""):
    return ejecutar(
        "INSERT INTO interacciones (tipo, pagina, detalle, sesion, creado_el) "
        "VALUES (?, ?, ?, ?, ?)",
        (tipo, pagina, detalle, sesion, _ahora()))


def publicacion_red_crear(plataforma, articulo_id, estado, detalle="", url_externa=""):
    return ejecutar(
        "INSERT INTO publicaciones_redes (plataforma, articulo_id, url_externa, estado, detalle, creado_el) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (plataforma, articulo_id, url_externa, estado, detalle, _ahora()))


def red_metrica_guardar(plataforma, seguidores=0, alcance=0, impresiones=0,
                        interacciones=0, notas="", unico_diario=False):
    """Registra una medicion de una red.

    Con unico_diario=True la fila del dia se actualiza en lugar de acumular
    una por cada ejecucion automatica (que corre cada pocas horas).
    """
    fecha = datetime.now().strftime("%Y-%m-%d")
    if unico_diario:
        filas = consultar(
            "SELECT id FROM redes_metricas WHERE plataforma=? AND fecha=?",
            (plataforma, fecha))
        if filas:
            ejecutar(
                "UPDATE redes_metricas SET seguidores=?, alcance=?, impresiones=?, "
                "interacciones=?, notas=? WHERE id=?",
                (seguidores, alcance, impresiones, interacciones, notas,
                 filas[0]["id"]))
            return filas[0]["id"]
    return ejecutar(
        "INSERT INTO redes_metricas (plataforma, fecha, seguidores, alcance, "
        "impresiones, interacciones, notas) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (plataforma, fecha, seguidores, alcance, impresiones, interacciones, notas))


def red_sync_registrar(disparador, plataformas, guardadas, errores, detalle=""):
    """Deja constancia de una ejecucion del registro automatico de metricas."""
    return ejecutar(
        "INSERT INTO redes_sync (ejecutado_el, disparador, plataformas, guardadas, "
        "errores, detalle) VALUES (?, ?, ?, ?, ?, ?)",
        (_ahora(), disparador, ",".join(plataformas or []), int(guardadas or 0),
         int(errores or 0), (detalle or "")[:500]))


def red_sync_ultimo():
    """Ultima ejecucion registrada del sincronizador de redes."""
    filas = consultar("SELECT * FROM redes_sync ORDER BY id DESC LIMIT 1")
    return filas[0] if filas else None


def red_sync_historico(limite=10):
    return consultar("SELECT * FROM redes_sync ORDER BY id DESC LIMIT ?", (int(limite),))


# ---------------- marketing digital: historial de auditorias
def marketing_guardar(objetivo, url, tipo, puntaje, motores, redes, tecnico,
                      resumen, contenido=None, consejos="", ia=0):
    """Guarda una auditoria de posicionamiento y devuelve su id."""
    import json as _json
    return ejecutar(
        "INSERT INTO marketing_analisis (objetivo, url, tipo, puntaje, motores, redes, "
        "tecnico, contenido, resumen, consejos, ia, creado_el) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (objetivo, url, tipo, int(puntaje or 0),
         _json.dumps(motores or [], ensure_ascii=False),
         _json.dumps(redes or [], ensure_ascii=False),
         _json.dumps(tecnico or [], ensure_ascii=False),
         _json.dumps(contenido or {}, ensure_ascii=False),
         (resumen or "")[:2000], (consejos or "")[:20000], 1 if ia else 0, _ahora()))


def marketing_actualizar_consejos(analisis_id, consejos, ia=1):
    ejecutar("UPDATE marketing_analisis SET consejos=?, ia=? WHERE id=?",
             ((consejos or "")[:20000], 1 if ia else 0, int(analisis_id)))


def marketing_analisis(analisis_id):
    filas = consultar("SELECT * FROM marketing_analisis WHERE id=?", (int(analisis_id),))
    return filas[0] if filas else None


def marketing_historial(limite=30, url=""):
    if url:
        return consultar(
            "SELECT * FROM marketing_analisis WHERE url=? ORDER BY id DESC LIMIT ?",
            (url, int(limite)))
    return consultar("SELECT * FROM marketing_analisis ORDER BY id DESC LIMIT ?",
                     (int(limite),))


def marketing_eliminar(analisis_id):
    ejecutar("DELETE FROM marketing_analisis WHERE id=?", (int(analisis_id),))


# ---------------------------------------------------------------- IAT / recicladores
def iat_crear(datos):
    """Radicado de un proyecto de aprovechamiento. Devuelve el id."""
    anio = datetime.now().year
    base = f"IAT-{anio}-"
    filas = consultar(
        "SELECT radicado FROM iat_solicitudes WHERE radicado LIKE ? ORDER BY id DESC",
        (base + "%",))
    ultimo = 0
    if filas:
        try:
            ultimo = int(filas[0]["radicado"].rsplit("-", 1)[1])
        except (ValueError, IndexError):
            ultimo = len(filas)
    radicado = base + str(ultimo + 1).zfill(5)
    return ejecutar(
        "INSERT INTO iat_solicitudes (usuario_id, radicado, titulo, tipo, descripcion, "
        "toneladas, municipio, estado, observaciones, datos, fecha_radicado, creado_el) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (int(datos["usuario_id"]), radicado, datos["titulo"],
         datos.get("tipo", "Aprovechamiento"), datos["descripcion"],
         float(datos.get("toneladas") or 0), datos.get("municipio", ""),
         datos.get("estado", "Radicado"), datos.get("observaciones", ""),
         json.dumps(datos.get("datos") or {}, ensure_ascii=False),
         _ahora(), _ahora()))


def iat_de_usuario(usuario_id, limite=100):
    return consultar(
        "SELECT * FROM iat_solicitudes WHERE usuario_id=? ORDER BY id DESC LIMIT ?",
        (int(usuario_id), int(limite)))


def iat_todos(limite=200):
    return consultar(
        "SELECT * FROM iat_solicitudes ORDER BY id DESC LIMIT ?", (int(limite),))


def iat_por_id(sid):
    filas = consultar("SELECT * FROM iat_solicitudes WHERE id=?", (int(sid),))
    return filas[0] if filas else None


def iat_actualizar(sid, cambios):
    campos, valores = [], []
    for clave in ("titulo", "tipo", "descripcion", "toneladas", "municipio",
                  "estado", "observaciones", "datos"):
        if clave in cambios:
            campos.append(f"{clave}=?")
            valores.append(cambios[clave])
    if not campos:
        return 0
    campos.append("modificado_el=?")
    valores.append(_ahora())
    valores.append(int(sid))
    return ejecutar("UPDATE iat_solicitudes SET " + ", ".join(campos) + " WHERE id=?",
                    tuple(valores))


def iat_eliminar(sid):
    ejecutar("DELETE FROM iat_solicitudes WHERE id=?", (int(sid),))


# ------------------------------------------------- motor normativo / jurisprudencial
def motor_fuentes_lista(solo_activas=False):
    sql = "SELECT * FROM motor_fuentes"
    if solo_activas:
        sql += " WHERE activo = 1"
    sql += " ORDER BY tipo, nombre"
    return consultar(sql)


def motor_fuente_crear(nombre, tipo, area, url):
    return ejecutar(
        "INSERT INTO motor_fuentes (nombre, tipo, area, url, activo, creado_el) "
        "VALUES (?, ?, ?, ?, 1, ?)",
        (nombre, tipo or "norma", area or "", url, _ahora()))


def motor_fuente_actualizar(fid, cambios):
    campos = list(cambios.keys())
    if not campos:
        return
    valores = [cambios[c] for c in campos]
    valores.append(int(fid))
    ejecutar("UPDATE motor_fuentes SET %s WHERE id = ?"
             % ", ".join("%s = ?" % c for c in campos), tuple(valores))


def motor_fuente_eliminar(fid):
    ejecutar("DELETE FROM motor_fuentes WHERE id=?", (int(fid),))


def motor_normas_lista(estado=None, limite=300):
    sql = "SELECT * FROM motor_normas"
    params = ()
    if estado:
        sql += " WHERE estado = ?"
        params = (estado,)
    sql += " ORDER BY id DESC LIMIT ?"
    return consultar(sql, params + (int(limite),))


def motor_norma_por_id(nid):
    filas = consultar("SELECT * FROM motor_normas WHERE id=?", (int(nid),))
    return filas[0] if filas else None


def motor_norma_existe(url):
    if not url:
        return None
    filas = consultar("SELECT id FROM motor_normas WHERE url = ?", (url,))
    return filas[0]["id"] if filas else None


def motor_norma_existe_titulo(titulo):
    filas = consultar("SELECT id FROM motor_normas WHERE LOWER(titulo) = LOWER(?)",
                      ((titulo or "").strip(),))
    return filas[0]["id"] if filas else None


def motor_norma_crear(datos):
    """Inserta una norma/providencia. Devuelve el id; None si la URL ya existe."""
    url = (datos.get("url") or "").strip()
    if url and motor_norma_existe(url):
        return None
    nuevo = ejecutar(
        "INSERT INTO motor_normas (titulo, tipo, categoria, emisor, numero, fecha, "
        "area, url, resumen, fuente_id, origen, estado, creado_el) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (datos["titulo"], datos.get("tipo", "norma"), datos.get("categoria", ""),
         datos.get("emisor", ""), datos.get("numero", ""), datos.get("fecha", ""),
         datos.get("area", ""), url, datos.get("resumen", ""),
         datos.get("fuente_id"), datos.get("origen", "manual"),
         datos.get("estado", "pendiente"), _ahora()))
    return nuevo


def motor_norma_estado(nid, estado):
    if estado not in ("pendiente", "aprobada", "descartada"):
        return
    ejecutar("UPDATE motor_normas SET estado=? WHERE id=?", (estado, int(nid)))


def motor_norma_eliminar(nid):
    ejecutar("DELETE FROM motor_normas WHERE id=?", (int(nid),))


def motor_resumen():
    total = consultar("SELECT COUNT(*) n FROM motor_normas")[0]["n"]
    pend = consultar("SELECT COUNT(*) n FROM motor_normas WHERE estado='pendiente'")[0]["n"]
    aprob = consultar("SELECT COUNT(*) n FROM motor_normas WHERE estado='aprobada'")[0]["n"]
    fuentes = consultar("SELECT COUNT(*) n FROM motor_fuentes WHERE activo=1")[0]["n"]
    return {"total": total, "pendientes": pend, "aprobadas": aprob, "fuentes": fuentes}