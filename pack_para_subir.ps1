# Empaqueta el proyecto Derechos On para subirlo al VPS.
# Genera: derechos-on-produccion.zip (en el Escritorio de este equipo)
$ErrorActionPreference = "Stop"
$origen = "C:\Users\jcifu\Documents\Default Project\derechos-on"
$destino = "C:\Users\jcifu\Desktop\derechos-on-produccion.zip"
$temporal = "C:\Users\jcifu\AppData\Local\Temp\opencode\derechos-on-paquete"

# Rutas que NO deben viajar a producción
$excluir = @(
    "__pycache__",
    "derechos.db",      # la BD local de prueba no se sube (se crea limpia en el VPS)
    "derechos_backup_before_cleanup.db",  # copia local de seguridad, no viaja
    "crm.db",           # BD local del CRM, se recrea limpia en el VPS
    "uploads",          # comprobantes de prueba
    "venv",
    ".git"
)

if (Test-Path $temporal) { Remove-Item $temporal -Recurse -Force }
New-Item -ItemType Directory -Path $temporal | Out-Null

$items = Get-ChildItem -LiteralPath $origen -Force
foreach ($item in $items) {
    if ($excluir -contains $item.Name) { continue }
    Copy-Item -LiteralPath $item.FullName -Destination $temporal -Recurse -Force
}

if (Test-Path $destino) { Remove-Item $destino }
Compress-Archive -Path "$temporal\*" -DestinationPath $destino
Remove-Item $temporal -Recurse -Force

Write-Host "ZIP generado: $destino"
Write-Host ""
Write-Host "Pasos en el VPS:"
Write-Host "  1) Subir derechos-on-produccion.zip (File Manager o SCP)"
Write-Host "  2) Descomprimir en: /home/derechoson/derechos-on"
Write-Host "  3) sudo bash deploy/instalar.sh"