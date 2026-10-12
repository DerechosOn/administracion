#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# Instalación de Derechos On en VPS Hostinger (Debian/Ubuntu).
#
# Requisitos:
#   - VPS Hostinger KVM con Ubuntu/Debian y acceso SSH como root.
#   - El proyecto ya subido a /home/derechoson/derechos-on (por FTP/SCP o
#     subiendo derechos-on-produccion.zip y descomprimiéndolo ahí).
#   - Dominio derechoson.online apuntando (DNS) a la IP del VPS.
#
# Uso (desde la carpeta del proyecto en el VPS):
#   sudo bash deploy/instalar.sh
# -----------------------------------------------------------------------------
set -euo pipefail

APP=/home/derechoson/derechos-on
VPS_USER=derechoson
DOMAIN=derechoson.online
PORT=8000

if [ "$(id -u)" -ne 0 ]; then
  echo "Error: ejecuta como root." >&2
  echo "  sudo bash $APP/deploy/instalar.sh" >&2
  exit 1
fi

if [ ! -f "$APP/app.py" ]; then
  echo "Error: no se encontró app.py en $APP. Sube primero el proyecto." >&2
  exit 1
fi

echo "==> 1/7 Usuario del sistema"
id -u $VPS_USER >/dev/null 2>&1 || useradd -m -s /bin/bash $VPS_USER
mkdir -p "$APP"

echo "==> 2/7 Entorno virtual e instalación de dependencias"
apt-get update -y
apt-get install -y python3 python3-venv python3-pip nginx
python3 -m venv "$APP/venv"
"$APP/venv/bin/pip" install --upgrade pip
"$APP/venv/bin/pip" install -r "$APP/requirements.txt"

echo "==> 3/7 Clave secreta de producción"
if [ ! -s /etc/derechoson.env ]; then
  umask 077
  printf 'SECRET_KEY=%s\n' "$(openssl rand -hex 32)" > /etc/derechoson.env
  chown root:root /etc/derechoson.env
  chmod 600 /etc/derechoson.env
fi

# Registro automatico de metricas de redes (1 = activado, cada 6 horas).
grep -q '^REDES_AUTO=' /etc/derechoson.env || printf 'REDES_AUTO=1\n' >> /etc/derechoson.env
grep -q '^REDES_AUTO_MINUTOS=' /etc/derechoson.env || printf 'REDES_AUTO_MINUTOS=360\n' >> /etc/derechoson.env

# Apoyo de redaccion con IA (Anthropic Claude). Sin IA_CLAVE la seccion de
# contratos funciona igual, solo la IA queda apagada.
grep -q '^IA_MODELO=' /etc/derechoson.env || printf 'IA_MODELO=claude-sonnet-5\n' >> /etc/derechoson.env
grep -q '^IA_MAX_CARACTERES=' /etc/derechoson.env || printf 'IA_MAX_CARACTERES=12000\n' >> /etc/derechoson.env
if ! grep -q '^IA_CLAVE=' /etc/derechoson.env; then
  printf '# IA_CLAVE=sk-ant-...   (descomenta y pega tu clave de Anthropic)\n' >> /etc/derechoson.env
fi
chown root:root /etc/derechoson.env
chmod 600 /etc/derechoson.env

echo "==> 4/7 Permisos (base de datos y subidas)"
touch "$APP/derechos.db"
chown -R $VPS_USER:$VPS_USER "$APP"

echo "==> 5/7 Servicio systemd"
cp "$APP/deploy/derechoson.service" /etc/systemd/system/derechoson.service
sed -i "s|/home/derechoson/derechos-on|$APP|g" /etc/systemd/system/derechoson.service
sed -i "s|--bind 127.0.0.1:8000|--bind 127.0.0.1:$PORT|g" /etc/systemd/system/derechoson.service
systemctl daemon-reload
systemctl enable derechoson
systemctl restart derechoson

echo "==> 6/7 Configuración de Nginx"
cp "$APP/deploy/nginx_derechoson.conf" /etc/nginx/sites-available/derechoson
sed -i "s|derechoson\.online|$DOMAIN|g" /etc/nginx/sites-available/derechoson
ln -sf /etc/nginx/sites-available/derechoson /etc/nginx/sites-enabled/derechoson
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx

echo "==> 7/7 Estado del servicio"
sleep 2
systemctl status derechoson --no-pager || true
echo
echo "Listo. El sitio debería responder en http://$DOMAIN"
echo "Siguiente paso (recomendado): instalar HTTPS con"
echo "  apt-get install -y certbot python3-certbot-nginx"
echo "  certbot --nginx -d $DOMAIN -d www.$DOMAIN"
echo
if grep -q '^IA_CLAVE=sk-' /etc/derechoson.env; then
  echo "IA de contratos: activada (Anthropic Claude)."
else
  echo "IA de contratos: apagada. Para activarla:"
  echo "  nano /etc/derechoson.env      # agrega IA_CLAVE=sk-ant-..."
  echo "  systemctl restart derechoson"
fi