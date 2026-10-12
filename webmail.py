# -*- coding: utf-8 -*-
"""Webmail para el portal del abogado (IMAP + SMTP).

Conexión a una cuenta de correo institucional (por defecto Hostinger)
con un cliente de correo propio integrado al portal, similar a Outlook.
"""

import base64
import email
import imaplib
import smtplib
from email.header import decode_header, make_header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, parseaddr

IMAP_HOST = "imap.hostinger.com"
IMAP_PUERTO = 993
SMTP_HOST = "smtp.hostinger.com"
SMTP_PUERTO = 465

CARPETAS = [
    ("INBOX", "Recibidos"),
    ("Sent", "Enviados"),
    ("Trash", "Papelera"),
    ("Junk", "No deseado"),
    ("Drafts", "Borradores"),
]


class ErrorCorreo(Exception):
    pass


def _texto(campo):
    if not campo:
        return ""
    try:
        return str(make_header(decode_header(campo)))
    except Exception:
        return str(campo)


def _fecha(msj):
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(msj.get("Date", "")).strftime("%d/%m/%Y %H:%M")
    except Exception:
        return msj.get("Date", "")[:25]


def _remitente(msj):
    nombre, correo = parseaddr(msj.get("From", ""))
    return _texto(nombre) or correo, correo


def _con_ssl(cfg):
    try:
        con = imaplib.IMAP4_SSL(cfg["servidor_imap"], int(cfg["puerto_imap"]), timeout=25)
        con.login(cfg["correo"], cfg["clave"])
        return con
    except (imaplib.IMAP4.error, OSError, Exception) as e:
        if isinstance(e, (imaplib.IMAP4.error, OSError)):
            raise ErrorCorreo("No se pudo conectar al correo: %s" % e)
        raise ErrorCorreo("Error de conexión al correo: %s" % e)


def probar(cfg):
    con = _con_ssl(cfg)
    con.logout()
    return True


def carpetas(cfg):
    con = _con_ssl(cfg)
    try:
        status, datos = con.list()
        if status != "OK":
            raise ErrorCorreo("El servidor no devolvió las carpetas.")
        nombres = []
        for fila in datos:
            s = fila.decode("utf-8", "replace")
            if '"' in s:
                nombres.append(s.split('"')[-2])
            else:
                nombres.append(s.rsplit("/", 1)[-1].strip())
        return nombres
    finally:
        try:
            con.logout()
        except Exception:
            pass


def listar(cfg, carpeta="INBOX", limite=50):
    con = _con_ssl(cfg)
    try:
        status, sel = con.select(carpeta, readonly=True)
        if status != "OK":
            raise ErrorCorreo("La carpeta '%s' no existe o no se pudo abrir." % carpeta)
        status, datos = con.search(None, "ALL")
        uids = [u.decode("ascii", "replace") for u in datos[0].split()] if datos and datos[0] else []
        uids = uids[-limite:] if limite else uids
        mensajes = []
        if uids:
            num = ",".join(uids)
            status, mdata = con.uid("FETCH", num,
                                    "(FLAGS BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
            if status == "OK":
                i = 0
                while i < len(mdata):
                    entrada = mdata[i]
                    if not isinstance(entrada, tuple):
                        i += 1
                        continue
                    cab = entrada[0].decode("utf-8", "replace") if isinstance(entrada[0], bytes) else str(entrada[0])
                    body_b = entrada[1]
                    numeric = cab.split("UID ")[1].split(" ")[0] if "UID " in cab else "?"
                    if "FLAGS (" in cab:
                        flag_fin = cab.split("FLAGS (")[1].split(")")[0]
                        no_leido = "Seen" not in flag_fin
                    else:
                        no_leido = False
                    msj = email.message_from_bytes(body_b if isinstance(body_b, bytes) else b"")
                    de_nombre, de_correo = _remitente(msj)
                    asunto = _texto(msj.get("Subject", "")) or "(sin asunto)"
                    fecha = _fecha(msj)
                    mensajes.append({"uid": numeric, "carpeta": carpeta,
                                     "de": de_nombre or de_correo, "correo_de": de_correo,
                                     "asunto": asunto, "fecha": fecha, "no_leido": no_leido})
                    i += 1
        return mensajes
    finally:
        try:
            con.close()
            con.logout()
        except Exception:
            pass


def _cuerpo_parte(parte):
    chs = parte.get_content_charset() or "utf-8"
    try:
        datos = parte.get_payload(decode=True)
        return datos.decode(chs, "replace")
    except Exception:
        return ""


def leer(cfg, carpeta, uid):
    con = _con_ssl(cfg)
    try:
        status, _ = con.select(carpeta, readonly=False)
        if status != "OK":
            raise ErrorCorreo("No se pudo abrir la carpeta %s." % carpeta)
        con.uid("STORE", uid, "+FLAGS", "(\\Seen)")
        status, mdata = con.uid("FETCH", uid, "(BODY.PEEK[] FLAGS)")
        if status != "OK" or not mdata or not isinstance(mdata[0], tuple):
            raise ErrorCorreo("No se pudo leer el mensaje.")
        msj = email.message_from_bytes(mdata[0][1])

        texto_html, texto_plano, adjuntos = "", "", []
        for indice, parte in enumerate(msj.walk()):
            nombre = parte.get_filename()
            if nombre:
                nombre = _texto(nombre)
                tamano = len(base64.b64decode(parte.get_payload()) ) if parte.get_content_type().startswith("image") else len(parte)
                payload = parte.get_payload(decode=True) or b""
                adjuntos.append({"indice": indice, "nombre": nombre,
                                 "tamano": len(payload)})
                continue
            ctype = parte.get_content_type()
            if ctype == "text/html" and not texto_html:
                texto_html = _cuerpo_parte(parte)
            elif ctype == "text/plain" and not texto_plano:
                texto_plano = _cuerpo_parte(parte)

        if not texto_html and texto_plano:
            import html as html_mod
            texto_html = html_mod.escape(texto_plano).replace("\n", "<br>")

        de_nombre, de_correo = _remitente(msj)
        return {
            "uid": uid, "carpeta": carpeta,
            "asunto": _texto(msj.get("Subject", "")) or "(sin asunto)",
            "de_nombre": de_nombre, "de_correo": de_correo,
            "para": msj.get("To", ""), "cc": msj.get("Cc", ""),
            "fecha": _fecha(msj), "html": texto_html or "",
            "message_id": msj.get("Message-ID", ""),
            "references": msj.get("References", ""),
            "adjuntos": adjuntos,
        }
    finally:
        try:
            con.close()
            con.logout()
        except Exception:
            pass


def marcar(cfg, carpeta, uid, leido):
    con = _con_ssl(cfg)
    try:
        status, _ = con.select(carpeta, readonly=False)
        if status == "OK":
            bandera = "+" if leido else "-"
            con.uid("STORE", uid, "%sFLAGS" % bandera, "(\\Seen)")
    finally:
        try:
            con.close()
            con.logout()
        except Exception:
            pass


def eliminar(cfg, carpeta, uid):
    con = _con_ssl(cfg)
    try:
        status, _ = con.select(carpeta, readonly=False)
        if status == "OK":
            con.uid("STORE", uid, "+FLAGS", "(\\Deleted)")
            con.expunge()
    finally:
        try:
            con.close()
            con.logout()
        except Exception:
            pass


def adjunto(cfg, carpeta, uid, indice):
    con = _con_ssl(cfg)
    try:
        status, _ = con.select(carpeta, readonly=True)
        status, mdata = con.uid("FETCH", uid, "(BODY.PEEK[])")
        if status != "OK" or not mdata or not isinstance(mdata[0], tuple):
            raise ErrorCorreo("No se pudo leer el adjunto.")
        msj = email.message_from_bytes(mdata[0][1])
        for i, parte in enumerate(msj.walk()):
            if i != indice:
                continue
            nombre = _texto(parte.get_filename()) or ("adjunto-%d" % indice)
            payload = parte.get_payload(decode=True) or b""
            mime = parte.get_content_type()
            return nombre, payload, mime
        raise ErrorCorreo("Adjunto no encontrado.")
    finally:
        try:
            con.close()
            con.logout()
        except Exception:
            pass


def _limpiar_asunto(asunto):
    t = asunto.strip()
    prefijos = ("Re:", "RE:", "Fw:", "FW:", "RES:")
    while any(t.startswith(p) for p in prefijos):
        t = t[3:].strip()
    return t


def enviar(cfg, para, asunto, cuerpo_html, cc="", responder=None):
    mensaje = MIMEMultipart("alternative")
    mensaje["From"] = cfg["correo"]
    mensaje["To"] = para
    mensaje["Cc"] = cc or ""
    mensaje["Date"] = formatdate(localtime=True)
    mensaje["Subject"] = asunto
    if responder:
        if responder.get("message_id"):
            mensaje["In-Reply-To"] = responder["message_id"]
            mensaje["References"] = (responder.get("references", "") + " " + responder["message_id"]).strip()

    import html as html_mod
    cuerpo_plano = (cuerpo_html or "").replace("<br>", "\n").replace("</p>", "\n\n")
    mensaje.attach(MIMEText(cuerpo_html or "", "html", "utf-8"))
    mensaje.attach(MIMEText(cuerpo_plano, "plain", "utf-8"))

    try:
        sesion = smtplib.SMTP_SSL(cfg["servidor_smtp"], int(cfg["puerto_smtp"]), timeout=25)
    except (smtplib.SMTPException, OSError, ValueError) as e:
        raise ErrorCorreo("No se pudo conectar al servidor de salida: %s" % e)
    try:
        sesion.login(cfg["correo"], cfg["clave"])
        sesion.sendmail(cfg["correo"], _destinatarios(para, cc), mensaje.as_string())
    except smtplib.SMTPException as e:
        raise ErrorCorreo("El servidor rechazó el envío: %s" % e)
    finally:
        try:
            sesion.quit()
        except Exception:
            pass


def _destinatarios(para, cc):
    dest = []
    for campo in (para, cc):
        for token in (campo or "").replace(";", ",").split(","):
            nombre, correo = parseaddr(token)
            if correo:
                dest.append(correo)
    return dest


def respuesta_previa(original, cuerpo_nuevo):
    """Devuelve el mensaje original citado como bloque Outlook."""
    from email.utils import formatdate
    linea = '<br><div style="border-left:3px solid #c6d4e8;padding:6px 14px;margin-top:12px;color:#5b6775">'
    linea += "<b>%s</b> &lt;%s&gt; escribió el %s:<br>" % (
        html_escape(original.get("de_nombre")), html_escape(original.get("de_correo")),
        html_escape(original.get("fecha")))
    linea += original.get("html", "") + "</div>"
    return (cuerpo_nuevo or "") + linea


def html_escape(texto):
    import html as html_mod
    return html_mod.escape(texto or "")