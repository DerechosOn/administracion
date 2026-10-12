"""Publicación de artículos en redes sociales (LinkedIn, X, Instagram).

La configuración (tokens, credenciales) se guarda en redes.json dentro del
proyecto. Ese archivo contiene secretos: no lo subas a repositorios ni lo
expongas en el hosting fuera del proyecto.
"""

import json
import os
import time
from datetime import datetime

import requests
from requests_oauthlib import OAuth1Session

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RUTA_CONFIG = os.path.join(BASE_DIR, "redes.json")
RUTA_LOCK = os.path.join(BASE_DIR, ".redes_sync.lock")

URL_BASE_DEFECTO = "http://127.0.0.1:5000/"

VACIOS = {
    "linkedin": {"activa": False, "auto": True, "token": "", "autor_urn": ""},
    "x": {"activa": False, "auto": True,
          "api_key": "", "api_secret": "", "access_token": "", "access_secret": ""},
    "instagram": {"activa": False, "auto": True, "token": "", "id_cuenta": ""},
}

NOMBRES = {"linkedin": "LinkedIn", "x": "X", "instagram": "Instagram"}

# Plataformas sin API de lectura: se omiten del reporte automatico.
SIN_METRICAS = {"x"}

# Cada cuanto se recogen las metricas automaticamente (minutos).
INTERVALO_MINUTOS = 360

LONGITUD_MAX = {"linkedin": 3000, "x": 280, "instagram": 2200}


def leer_config():
    cfg = {p: dict(v) for p, v in VACIOS.items()}
    try:
        with open(RUTA_CONFIG, "r", encoding="utf-8") as f:
            guardado = json.load(f)
        for p in cfg:
            cfg[p].update({k: v for k, v in guardado.get(p, {}).items() if k in cfg[p]})
    except (OSError, ValueError):
        pass
    return cfg


def guardar_config(cfg):
    with open(RUTA_CONFIG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def redactar(cfg):
    copia = {p: dict(c) for p, c in cfg.items()}
    for p in ("linkedin", "instagram"):
        tok = copia[p].get("token", "")
        if tok:
            copia[p]["token"] = tok[:8] + "…" + tok[-4:]
    if copia["x"].get("api_key"):
        copia["x"]["api_key"] = "•" * 10
    if copia["x"].get("api_secret"):
        copia["x"]["api_secret"] = "•" * 10
    if copia["x"].get("access_token"):
        copia["x"]["access_token"] = copia["x"]["access_token"][:8] + "…"
    if copia["x"].get("access_secret"):
        copia["x"]["access_secret"] = "•" * 10
    return copia


def bloquear(plataforma):
    """Devuelve (ok, mensaje). ok=False si la configuración no está completa."""
    cfg = leer_config()[plataforma]
    if plataforma == "linkedin":
        if not cfg["token"]:
            return False, "Falta el token de acceso de LinkedIn."
        return True, ""
    if plataforma == "x":
        faltan = [k for k in ("api_key", "api_secret", "access_token", "access_secret")
                  if not cfg[k]]
        if faltan:
            return False, "Faltan credenciales de la app de X: " + ", ".join(faltan).replace("_", " ")
        return True, ""
    if plataforma == "instagram":
        if not cfg["token"] or not cfg["id_cuenta"]:
            return False, "Faltan el token y el ID de la cuenta de Instagram."
        return True, ""


def _http_linkedin(token, json_datos):
    return requests.post(
        "https://api.linkedin.com/v2/userinfo",
        headers={"Authorization": "Bearer " + token},
        timeout=20)


def _http_linkedin_post(token, json_datos, version="202501"):
    return requests.post(
        "https://api.linkedin.com/rest/posts",
        headers={"Authorization": "Bearer " + token,
                 "X-Restli-Protocol-Version": "2.0.0",
                 "LinkedIn-Version": version,
                 "Content-Type": "application/json"},
        json=json_datos,
        timeout=20)


def _http_x(cfg, json_datos):
    sesion = OAuth1Session(cfg["api_key"], cfg["api_secret"],
                           cfg["access_token"], cfg["access_secret"])
    return sesion.post("https://api.twitter.com/2/tweets", json=json_datos, timeout=20)


def _http_ig(url, datos=None, cabeceras=None, archivo=None):
    cabeceras = cabeceras or {}
    if archivo:
        with open(archivo, "rb") as f:
            return requests.post(url, data=datos or {},
                                 files={"file": (os.path.basename(archivo), f)},
                                 headers=cabeceras, timeout=60)
    return requests.post(url, data=datos or {}, headers=cabeceras, timeout=20)


def test_linkedin():
    ok, msg = bloquear("linkedin")
    if not ok:
        return False, msg
    try:
        r = _http_linkedin(leer_config()["linkedin"]["token"], None)
        if r.status_code in (200, 201):
            return True, "Token de LinkedIn válido."
        return False, "LinkedIn respondió HTTP %s: %s" % (r.status_code, r.text[:200])
    except requests.RequestException as e:
        return False, "Error de conexión: %s" % e


def test_x():
    ok, msg = bloquear("x")
    if not ok:
        return False, msg
    try:
        r = _http_x(leer_config()["x"], {"text": "Derechos On · prueba de conexión"})
        if r.status_code in (200, 201):
            return True, "Credenciales de X válidas (se publicó un tuit de prueba)."
        return False, "X respondió HTTP %s: %s" % (r.status_code, r.text[:200])
    except requests.RequestException as e:
        return False, "Error de conexión: %s" % e


def test_instagram():
    ok, msg = bloquear("instagram")
    if not ok:
        return False, msg
    cfg = leer_config()["instagram"]
    try:
        r = requests.get("https://graph.facebook.com/v19.0/%s" % cfg["id_cuenta"],
                         params={"fields": "id,username", "access_token": cfg["token"]},
                         timeout=20)
        if r.status_code == 200:
            return True, "Token de Instagram válido (cuenta: %s)." % r.json().get("username", "?")
        return False, "Instagram respondió HTTP %s: %s" % (r.status_code, r.text[:200])
    except requests.RequestException as e:
        return False, "Error de conexión: %s" % e


def _acortar(texto, tope):
    if len(texto) <= tope:
        return texto
    recorte = texto[:tope - 3].rsplit(" ", 1)[0]
    return recorte + "…"


def _componer_mensaje(articulo, url, plataforma):
    texto = articulo["titulo"].strip()
    if articulo.get("resumen"):
        texto += "\n\n" + articulo["resumen"].strip()
    etiqueta = (articulo.get("etiqueta") or "").strip()
    if etiqueta and etiqueta.lower() != "artículo":
        texto += "\n\n#" + etiqueta.replace(" ", "").replace("-", "")
    texto += "\n\n" + url
    return _acortar(texto, LONGITUD_MAX[plataforma])


def publicar_linkedin(texto, url):
    cfg = leer_config()["linkedin"]
    autor_urn = cfg.get("autor_urn")
    if not autor_urn:
        r = _http_linkedin(cfg["token"], None)
        if r.status_code not in (200, 201):
            return False, "No se pudo obtener el perfil de LinkedIn (HTTP %s)." % r.status_code
        sub = r.json().get("sub")
        if not sub:
            return False, "LinkedIn no devolvió un identificador de perfil."
        autor_urn = "urn:li:person:%s" % sub
        cfg["autor_urn"] = autor_urn
        guardar_config(leer_config())
    cuerpo = {
        "author": autor_urn,
        "commentary": texto + "\n\n" + url,
        "visibility": "PUBLIC",
        "distribution": {"feedDistribution": "MAIN_FEED",
                         "targetEntities": [], "thirdPartyDistributionChannels": []},
    }
    r = _http_linkedin_post(cfg["token"], cuerpo)
    if r.status_code in (200, 201):
        return True, "Publicado en LinkedIn."
    return False, "LinkedIn respondió HTTP %s: %s" % (r.status_code, r.text[:200])


def publicar_x(texto, url):
    r = _http_x(leer_config()["x"], {"text": texto})
    if r.status_code in (200, 201):
        return True, "Publicado en X."
    return False, "X respondió HTTP %s: %s" % (r.status_code, r.text[:200])


def publicar_instagram(texto, url, ruta_imagen):
    cfg = leer_config()["instagram"]
    if not ruta_imagen or not os.path.exists(ruta_imagen):
        return False, "El artículo no tiene imagen para publicar en Instagram."
    base = "https://graph.facebook.com/v19.0"
    cab = {"Authorization": "Bearer " + cfg["token"]}
    r = _http_ig(base + "/%s/media" % cfg["id_cuenta"],
                 datos={"caption": texto}, cabeceras=cab, archivo=ruta_imagen)
    if r.status_code not in (200, 201):
        return False, "Instagram (media) HTTP %s: %s" % (r.status_code, r.text[:200])
    contenedor = r.json().get("id")
    r2 = _http_ig(base + "/%s/media_publish" % cfg["id_cuenta"],
                  datos={"creation_id": contenedor}, cabeceras=cab)
    if r2.status_code in (200, 201):
        return True, "Publicado en Instagram."
    return False, "Instagram (publicar) HTTP %s: %s" % (r2.status_code, r2.text[:200])


def publicar_articulo(articulo, url, ruta_imagen=None):
    """Publica en todas las redes activas. Devuelve listado (plataforma, ok, mensaje)."""
    cfg = leer_config()
    resultados = []
    if cfg["linkedin"]["activa"]:
        ok, msg = bloquear("linkedin")
        if ok:
            try:
                ok, msg = publicar_linkedin(_componer_mensaje(articulo, url, "linkedin"), url)
            except requests.RequestException as e:
                ok, msg = False, "Error de conexión: %s" % e
        resultados.append(("LinkedIn", ok, msg))
    if cfg["x"]["activa"]:
        ok, msg = bloquear("x")
        if ok:
            try:
                ok, msg = publicar_x(_componer_mensaje(articulo, url, "x"), url)
            except requests.RequestException as e:
                ok, msg = False, "Error de conexión: %s" % e
        resultados.append(("X", ok, msg))
    if cfg["instagram"]["activa"]:
        ok, msg = bloquear("instagram")
        if ok:
            try:
                ok, msg = publicar_instagram(
                    _componer_mensaje(articulo, url, "instagram"), url, ruta_imagen)
            except requests.RequestException as e:
                ok, msg = False, "Error de conexión: %s" % e
        resultados.append(("Instagram", ok, msg))
    return resultados


def obtener_metricas():
    """Intenta leer métricas básicas de las redes activas. Devuelve
    {clave: (ok, mensaje, {seguidores, alcance, impresiones, interacciones})}.
    Es de mejor esfuerzo: si la API no está disponible o falta permiso,
    (ok=False) con mensaje para el operador."""
    from datetime import date, timedelta

    cfg = leer_config()
    res = {}

    if cfg["instagram"]["activa"] and cfg["instagram"]["token"] and cfg["instagram"]["id_cuenta"]:
        base = "https://graph.facebook.com/v19.0"
        token = cfg["instagram"]["token"]
        cuenta = cfg["instagram"]["id_cuenta"]
        try:
            seg, media = 0, 0
            r = requests.get(base + "/%s" % cuenta,
                             params={"fields": "followers_count,media_count",
                                     "access_token": token}, timeout=20)
            if r.status_code == 200:
                seg = int(r.json().get("followers_count") or 0)
                media = int(r.json().get("media_count") or 0)
            alcance = imp = inte = 0
            if r.status_code == 200:
                desde = int((date.today() - timedelta(days=30) -
                             timedelta(seconds=17200)).timestamp())
                hasta = int((date.today() + timedelta(days=1) -
                             timedelta(seconds=17200)).timestamp())
                ri = requests.get(
                    base + "/%s/insights" % cuenta,
                    params={"metric": "reach,impressions,profile_views",
                            "period": "day", "since": desde, "until": hasta,
                            "access_token": token}, timeout=20)
                if ri.status_code == 200:
                    for bloque in ri.json().get("data", []):
                        for v in bloque.get("values", []):
                            valor = int(v.get("value") or 0)
                            if bloque.get("name") == "reach":
                                alcance += valor
                            elif bloque.get("name") == "impressions":
                                imp += valor
                            elif bloque.get("name") == "profile_views":
                                inte += valor
            res["instagram"] = (True,
                                "Actualizado desde Instagram (%s publicaciones)." % media,
                                {"seguidores": seg, "alcance": alcance,
                                 "impresiones": imp, "interacciones": inte})
        except requests.RequestException as e:
            res["instagram"] = (False, "Error de conexión: %s" % e, {})

    if cfg["linkedin"]["activa"] and cfg["linkedin"]["token"]:
        token = cfg["linkedin"]["token"]
        autor_urn = cfg.get("autor_urn")
        if not autor_urn:
            try:
                r = _http_linkedin(token, None)
                if r.status_code in (200, 201) and r.json().get("sub"):
                    autor_urn = "urn:li:person:%s" % r.json()["sub"]
            except requests.RequestException as e:
                autor_urn = None
                res["linkedin"] = (False, "Error de conexión: %s" % e, {})
        if autor_urn:
            try:
                r = requests.get(
                    "https://api.linkedin.com/v2/networkSizes",
                    params={"q": "members", "ids": "List(%s)" % autor_urn},
                    headers={"Authorization": "Bearer " + token,
                             "X-Restli-Protocol-Version": "2.0.0"},
                    timeout=20)
                if r.status_code == 200:
                    datos = r.json().get("results", [{}])[0]
                    redes_sz = (datos.get("networkSizes") or [{}])[0]
                    seg = int(redes_sz.get("firstDegreeSize") or 0)
                    res["linkedin"] = (True, "Actualizado desde LinkedIn.",
                                       {"seguidores": seg, "alcance": 0,
                                        "impresiones": 0, "interacciones": 0})
                else:
                    res["linkedin"] = (False,
                                       "LinkedIn HTTP %s: %s" % (r.status_code, r.text[:160]), {})
            except requests.RequestException as e:
                res["linkedin"] = (False, "Error de conexión: %s" % e, {})
        elif "linkedin" not in res:
            res["linkedin"] = (False, "No se pudo identificar el perfil de LinkedIn.", {})

    res["x"] = (False, "X no expone métricas por API sin permisos adicionales. Regístralas manualmente.", {})
    return res


def plataformas_conectadas():
    """Redes activas y con credenciales completas. [(clave, nombre)]."""
    cfg = leer_config()
    lista = []
    for clave in ("linkedin", "x", "instagram"):
        if cfg[clave]["activa"] and bloquear(clave)[0]:
            lista.append((clave, NOMBRES[clave]))
    return lista


def _tomar_lock(intervalo_minutos):
    """Lock de archivo con creacion atomica: evita que los varios workers de
    gunicorn recojan las metricas al mismo tiempo. Los locks viejos caducan."""
    for _ in range(2):
        try:
            fd = os.open(RUTA_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                edad = time.time() - os.path.getmtime(RUTA_LOCK)
            except OSError:
                edad = 0
            if edad < max(intervalo_minutos, 5) * 60:
                return False
            try:
                os.remove(RUTA_LOCK)
            except OSError:
                return False
            continue
        except OSError:
            return False
        try:
            with os.fdopen(fd, "w") as f:
                f.write(str(os.getpid()))
        except OSError:
            return True
        return True
    return False


def _soltar_lock():
    try:
        os.remove(RUTA_LOCK)
    except OSError:
        pass


def registrar_automaticas(disparador="auto", forzar=False,
                          minutos=INTERVALO_MINUTOS):
    """Registra las metricas de las redes ya conectadas.

    Solo corre si hay al menos una red activa con credenciales completas, de
    modo que no genera ruido antes de conectarlas. Guarda un solo registro por
    plataforma y dia (actualiza el existente) y deja constancia del intento.

    Devuelve dict: ok, omitido, motivo, guardadas, errores, detalle, plataformas.
    """
    import db

    conectadas = plataformas_conectadas()
    if not conectadas:
        return {"ok": True, "omitido": True, "motivo": "sin_redes", "guardadas": 0,
                "errores": 0, "plataformas": [],
                "detalle": "Ninguna red está activa y configurada todavía."}

    if not forzar:
        ultimo = db.red_sync_ultimo()
        if ultimo and _minutos_desde(ultimo.get("ejecutado_el")) < minutos:
            return {"ok": True, "omitido": True, "motivo": "reciente", "guardadas": 0,
                    "errores": 0, "plataformas": [],
                    "detalle": "La última actualización fue hace menos de %d min." % minutos}

    if not _tomar_lock(minutos):
        return {"ok": True, "omitido": True, "motivo": "ocupado", "guardadas": 0,
                "errores": 0, "plataformas": [],
                "detalle": "Ya hay una actualización en curso en otro proceso."}

    try:
        resultados = obtener_metricas()
        guardadas, errores, detalle, guardadas_nombres = 0, 0, [], []
        for clave, (ok, msg, datos) in resultados.items():
            if clave in SIN_METRICAS:
                continue
            if ok:
                db.red_metrica_guardar(
                    clave,
                    int(datos.get("seguidores") or 0),
                    int(datos.get("alcance") or 0),
                    int(datos.get("impresiones") or 0),
                    int(datos.get("interacciones") or 0),
                    notas="Actualización automática: %s" % msg,
                    unico_diario=True)
                guardadas += 1
                guardadas_nombres.append(NOMBRES.get(clave, clave))
                detalle.append("%s: %s" % (NOMBRES.get(clave, clave), msg))
            else:
                errores += 1
                detalle.append("%s: %s" % (NOMBRES.get(clave, clave), msg))

        conectadas_nombres = [n for _, n in conectadas]
        db.red_sync_registrar(disparador, conectadas_nombres, guardadas, errores,
                              " · ".join(detalle)[:500])
        return {"ok": errores == 0, "omitido": False, "motivo": "",
                "guardadas": guardadas, "errores": errores,
                "plataformas": guardadas_nombres, "conectadas": conectadas_nombres,
                "detalle": " · ".join(detalle)}
    finally:
        _soltar_lock()


def _minutos_desde(texto):
    """Minutos transcurridos desde una marca 'YYYY-MM-DD HH:MM:SS' (o '')."""
    if not texto:
        return 10 ** 6
    try:
        desde = datetime.strptime(str(texto)[:19], "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return 10 ** 6
    return max(0.0, (datetime.now() - desde).total_seconds() / 60.0)