# Installe OpenTakeoff A COTE d'ARENA, jamais dedans.
#
# Le moteur de metre : un depot separe (Kentucky-ai, Apache-2.0), ses propres
# dependances Node. Le copier dans ce depot melangerait deux historiques pour
# rien — ARENA le lance lui-meme comme un processus, exactement comme il
# refuse d'executer du code sans Docker (DEC-0004) : rien n'entre ici sauf le
# chemin vers son dossier construit.
#
#   powershell -ExecutionPolicy Bypass -File scripts\installer_opentakeoff.ps1
#
# Rien n'est lance a la fin : il n'y a rien a lancer en continu. ARENA demarre
# et arrete le processus Node a chaque metre — voir core/mcp/stdio_transport.py.

$ErrorActionPreference = "Stop"

$Racine = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Cible = Join-Path (Split-Path -Parent $Racine) "opentakeoff"

Write-Host "=============================================================="
Write-Host "  OpenTakeoff — installation a cote d'ARENA"
Write-Host "  Destination : $Cible"
Write-Host "=============================================================="

# 1. Ce qu'il faut avant de commencer. On verifie, on ne suppose pas.
foreach ($outil in @("git", "node", "npm")) {
    if (-not (Get-Command $outil -ErrorAction SilentlyContinue)) {
        Write-Host "[ABSENT] $outil est introuvable." -ForegroundColor Red
        if ($outil -eq "node" -or $outil -eq "npm") {
            Write-Host "         -> installe Node.js (winget install OpenJS.NodeJS.LTS)"
        } else {
            Write-Host "         -> installe $outil puis relance ce script."
        }
        exit 1
    }
    Write-Host "[OK]     $outil"
}

# 2. Le depot. S'il est deja la, on le met a jour plutot que de le recopier.
if (Test-Path $Cible) {
    Write-Host "[INFO]   Deja present : mise a jour."
    git -C $Cible pull --ff-only
} else {
    git clone --depth 1 https://github.com/Kentucky-ai/opentakeoff.git $Cible
}

# 3. Ses dependances. Deux dossiers : `web/` porte le moteur de mesure
#    (pdf.js, la geometrie) que `mcp/` importe directement en TypeScript.
Write-Host "[INFO]   npm install (web)"
Push-Location (Join-Path $Cible "web")
npm install
Pop-Location

Write-Host "[INFO]   npm install + build (mcp)"
Push-Location (Join-Path $Cible "mcp")
npm install
npm run build
Pop-Location

$Construit = Join-Path $Cible "mcp\dist\server.js"
if (-not (Test-Path $Construit)) {
    Write-Host "[ECHEC]  $Construit n'existe pas apres la construction." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "=============================================================="
Write-Host "  IL RESTE UNE CHOSE A FAIRE, ET ELLE EST A TOI"
Write-Host "=============================================================="
Write-Host ""
Write-Host "Dans le .env d'ARENA, ajoute :"
Write-Host ""
Write-Host "     OPENTAKEOFF_MCP_DIR=$($Cible -replace '\\','\\')\mcp" -ForegroundColor Yellow
Write-Host ""
Write-Host "Rien d'autre a lancer : ARENA demarre et arrete le processus Node"
Write-Host "lui-meme, a chaque plan mesure."
Write-Host ""
Write-Host "Puis, depuis ARENA :  python scripts\doctor.py"
Write-Host "La ligne « Metre de plan (OpenTakeoff) » doit passer a [OK]."
Write-Host ""
