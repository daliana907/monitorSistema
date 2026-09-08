# Pregunta a GitHub como fueron las ultimas ejecuciones de las pruebas.
# No hace falta contrasena: los repositorios publicos se pueden consultar libremente.

$cabeceras = @{ "User-Agent" = "nvda-addons-daliana" }
$repos = @("monitorSistema", "climaAccesible", "biosManager")

foreach ($repo in $repos) {
    Write-Output "===== $repo ====="
    try {
        $url = "https://api.github.com/repos/daliana907/$repo/actions/runs?per_page=3"
        $datos = Invoke-RestMethod -Uri $url -Headers $cabeceras -TimeoutSec 30

        if ($datos.total_count -eq 0) {
            Write-Output "  Todavia no hay ninguna ejecucion registrada."
        }

        foreach ($ejecucion in $datos.workflow_runs) {
            Write-Output ("  {0}" -f $ejecucion.name)
            Write-Output ("     estado: {0} | resultado: {1}" -f $ejecucion.status, $ejecucion.conclusion)
            Write-Output ("     fecha: {0}" -f $ejecucion.created_at)
            Write-Output ("     enlace: {0}" -f $ejecucion.html_url)

            if ($ejecucion.conclusion -eq "failure") {
                Write-Output "     --- que fallo exactamente ---"
                try {
                    $trabajos = Invoke-RestMethod -Uri $ejecucion.jobs_url -Headers $cabeceras -TimeoutSec 30
                    foreach ($trabajo in $trabajos.jobs) {
                        foreach ($paso in $trabajo.steps) {
                            if ($paso.conclusion -eq "failure") {
                                Write-Output ("     fallo el paso: {0}" -f $paso.name)
                            }
                        }
                    }
                } catch {
                    Write-Output ("     no se pudo saber el detalle: " + $_.Exception.Message)
                }
            }
            Write-Output ""
        }
    } catch {
        Write-Output ("  No se pudo consultar: " + $_.Exception.Message)
        Write-Output "  (si dice 404, puede que el repositorio sea privado)"
    }
    Write-Output ""
}
