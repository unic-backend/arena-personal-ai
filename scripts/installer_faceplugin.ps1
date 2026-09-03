# Installe le SDK Faceplugin DANS tools\vision\faceplugin\, hors de git.
#
# Ce depot ne porte AUCUN fichier LICENSE : seulement un badge « Open Source »
# dans son README, qui ne concede rien en droit. Sans licence explicite, tous
# droits reserves — son source ne peut donc pas entrer dans un depot public.
# `.gitignore` couvre `tools/vision/faceplugin/` en entier, et un test le
# verifie (`tests/test_moteurs_externes_restent_dehors.py`).
#
#   powershell -ExecutionPolicy Bypass -File scripts\installer_faceplugin.ps1
#
# Le SDK demande torch, torchvision et opencv : environ 1,1 Go avec ses
# dependances. Ils vont dans SON environnement, jamais dans celui d'ARENA.
# Rien n'est lance a la fin : installer et executer sont deux gestes distincts.

$ErrorActionPreference = "Stop"

$Racine = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Cible = Join-Path $Racine "tools\vision\faceplugin\Open-Source-Face-Recognition-SDK"

Write-Host "=============================================================="
Write-Host "  Faceplugin — analyse de visages, installe a cote d'ARENA"
Write-Host "  Destination : $Cible"
Write-Host "=============================================================="

if (Test-Path (Join-Path $Cible "run.py")) {
    Write-Host "Deja present. Mise a jour du depot..."
    git -C $Cible pull --ff-only
} else {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Cible) | Out-Null
    git clone --depth 1 https://github.com/Faceplugin-ltd/Open-Source-Face-Recognition-SDK $Cible
}

$Venv = Join-Path $Cible ".venv"
if (-not (Test-Path (Join-Path $Venv "Scripts\python.exe"))) {
    Write-Host "Creation de son environnement Python..."
    python -m venv $Venv
}

$Py = Join-Path $Venv "Scripts\python.exe"
Write-Host "Installation de ses dependances (torch, opencv...)..."
& $Py -m pip install --upgrade pip
& $Py -m pip install -r (Join-Path $Cible "requirements.txt")

Write-Host ""
Write-Host "Termine. Verifie avec :"
Write-Host "  python scripts\doctor.py     -> ligne « Visages (Faceplugin) »"
Write-Host ""
Write-Host "Rappel : les fonctions biometriques (extraire un gabarit, comparer"
Write-Host "deux visages) demandent ta confirmation a chaque appel. ARENA ne"
Write-Host "tient aucune base de visages et n'en constitue pas."
