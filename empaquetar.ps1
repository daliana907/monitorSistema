# Arma el archivo .nvda-addon de cada complemento: una copia limpia de la
# carpeta, comprimida y con la extension que NVDA reconoce.
#
# Deja fuera todo lo que no forma parte del complemento (el historial de
# GitHub, las pruebas, los archivos .bat, la portada del repositorio...).
# Eso no se instala en el equipo de nadie y solo haria el paquete mas pesado.

$carpetaAddons = Join-Path $env:APPDATA "nvda\addons"
$destino = Join-Path $env:USERPROFILE "Desktop"
$complementos = @("monitorSistema", "climaAccesible", "biosManager")

# Lo que NO se copia al paquete
$fuera = @(".git", ".github", "tests", "__pycache__")
$fueraArchivos = @("*.bat", "*.ps1", "*.yml", "README.md", "CHANGELOG.md",
                   ".gitignore", "resultado_github.txt", "*.nvda-addon")

foreach ($nombre in $complementos) {
    $origen = Join-Path $carpetaAddons $nombre
    Write-Output "===== $nombre ====="

    if (-not (Test-Path $origen)) {
        Write-Output "  No encuentro la carpeta. Saltando."
        continue
    }

    # leer la version de la ficha del complemento
    $manifiesto = Join-Path $origen "manifest.ini"
    $version = "sin-version"
    foreach ($linea in Get-Content $manifiesto -Encoding UTF8) {
        if ($linea -match '^\s*version\s*=\s*"?([^"\r\n]+)"?\s*$') {
            $version = $Matches[1].Trim()
            break
        }
    }
    Write-Output "  Version segun la ficha: $version"

    # copia limpia en una carpeta temporal
    $temporal = Join-Path $env:TEMP ("paquete_" + $nombre)
    if (Test-Path $temporal) { Remove-Item $temporal -Recurse -Force }
    New-Item -ItemType Directory -Path $temporal | Out-Null

    Get-ChildItem -Path $origen -Force | ForEach-Object {
        if ($fuera -contains $_.Name) { return }
        $descartar = $false
        foreach ($patron in $fueraArchivos) {
            if ($_.Name -like $patron) { $descartar = $true }
        }
        if ($descartar) { return }
        Copy-Item $_.FullName -Destination $temporal -Recurse -Force
    }
    # por si quedaron carpetas de python compiladas dentro
    Get-ChildItem -Path $temporal -Recurse -Force -Directory |
        Where-Object { $_.Name -eq "__pycache__" } |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

    # comprobar que lo imprescindible esta dentro
    $faltan = @()
    foreach ($obligatorio in @("manifest.ini", "globalPlugins")) {
        if (-not (Test-Path (Join-Path $temporal $obligatorio))) { $faltan += $obligatorio }
    }
    if ($faltan.Count -gt 0) {
        Write-Output ("  ERROR: al paquete le falta " + ($faltan -join ", ") + ". No se crea.")
        continue
    }

    $paquete = Join-Path $destino ("$nombre-$version.nvda-addon")
    $zipTemporal = Join-Path $env:TEMP ("$nombre-$version.zip")
    if (Test-Path $zipTemporal) { Remove-Item $zipTemporal -Force }
    if (Test-Path $paquete) { Remove-Item $paquete -Force }

    Compress-Archive -Path (Join-Path $temporal "*") -DestinationPath $zipTemporal -CompressionLevel Optimal
    Move-Item $zipTemporal $paquete

    $tamano = [math]::Round((Get-Item $paquete).Length / 1MB, 2)
    Write-Output "  Paquete creado: $nombre-$version.nvda-addon ($tamano MB)"
    Write-Output "  Esta en tu Escritorio."

    # que quedo dentro, para poder revisarlo
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [System.IO.Compression.ZipFile]::OpenRead($paquete)
    $carpetasDentro = $zip.Entries | ForEach-Object { ($_.FullName -split "/")[0] } | Sort-Object -Unique
    Write-Output ("  Contiene: " + ($carpetasDentro -join ", "))
    Write-Output ("  Archivos dentro: " + $zip.Entries.Count)
    $zip.Dispose()

    Remove-Item $temporal -Recurse -Force
    Write-Output ""
}
Write-Output "Terminado."
