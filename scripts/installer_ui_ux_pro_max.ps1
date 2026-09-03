# Installe UI/UX Pro Max DANS tools\design\ui_ux_pro_max\, hors de git.
#
# Ce moteur est MIT — rien n'interdirait de le versionner. Il reste dehors par
# CONVENTION : tout moteur externe vit a cote d'ARENA ici (VoiceStudio, WanGP,
# MoneyPrinterTurbo, OpenTakeoff, Xaar Kaname), et une seule regle vaut mieux
# que deux selon la licence. Sa notice MIT voyage avec lui, dans son propre
# fichier LICENSE, jamais separee de son code.
#
#   powershell -ExecutionPolicy Bypass -File scripts\installer_ui_ux_pro_max.ps1
#
# Aucune dependance a installer : le moteur est en Python pur (bibliotheque
# standard seule) et tourne avec l'interpreteur d'ARENA. Seules ses donnees
# comptent, environ 23 Mo de tables CSV.

$ErrorActionPreference = "Stop"

$Racine = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Cible = Join-Path $Racine "tools\design\ui_ux_pro_max"

Write-Host "=============================================================="
Write-Host "  UI/UX Pro Max — intelligence de design, a cote d'ARENA"
Write-Host "  Destination : $Cible"
Write-Host "=============================================================="

$Moteur = Join-Path $Cible "src\ui-ux-pro-max\scripts\search.py"
if (Test-Path $Moteur) {
    Write-Host "Deja present. Mise a jour du depot..."
    git -C $Cible pull --ff-only
} else {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Cible) | Out-Null
    git clone --depth 1 https://github.com/nextlevelbuilder/ui-ux-pro-max-skill $Cible
}

Write-Host ""
Write-Host "Termine. Verifie avec :"
Write-Host "  python scripts\doctor.py     -> ligne « Design (UI/UX Pro Max) »"
