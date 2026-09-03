# Installe le SDK Faceplugin DANS tools\vision\faceplugin\, hors de git.
#
# Ce depot ne porte AUCUN fichier LICENSE : seulement un badge " Open Source "
# dans son README, qui ne concede rien en droit. Sans licence explicite, tous
# droits reserves - son source ne peut donc pas entrer dans un depot public.
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
Write-Host "  Faceplugin - analyse de visages, installe a cote d'ARENA"
Write-Host "  Destination : $Cible"
Write-Host "=============================================================="

# --- Le Python du SDK, choisi et pas subi -----------------------------------
#
# Mesure du 03/09/2026 sur la machine du proprietaire : son Python est 3.14,
# et `torch==2.4.1` n'a de roues que pour 3.8 a 3.12. L'environnement cree a
# partir de son interpreteur ne pouvait donc RIEN installer, et cet installeur
# affichait quand meme " Termine ". Le diagnostic a rattrape le mensonge une
# etape plus loin : "ModuleNotFoundError: No module named 'cv2'".
#
# On cherche donc une version compatible via le lanceur `py` de Windows, et on
# s'arrete en le disant si aucune n'est presente. Un environnement construit
# sur le mauvais interpreteur est pire qu'une absence d'environnement : il a
# l'air installe.
$Python = $null
foreach ($v in @("3.12", "3.11", "3.10")) {
    & py "-$v" -c "import sys" 2>$null
    if ($LASTEXITCODE -eq 0) { $Python = @("py", "-$v"); break }
}

if (-not $Python) {
    Write-Host ""
    Write-Host "ARRET : aucun Python 3.10, 3.11 ou 3.12 trouve sur cette machine."
    Write-Host "Le SDK Faceplugin depend de torch 2.4.1, qui n'existe pas pour"
    Write-Host "Python 3.13 ni 3.14. Rien n'a ete installe."
    Write-Host ""
    Write-Host "Installe Python 3.12, puis relance ce script :"
    Write-Host "  winget install Python.Python.3.12"
    exit 1
}
Write-Host "Interpreteur retenu pour le SDK : $($Python -join ' ')"

if (Test-Path (Join-Path $Cible "run.py")) {
    Write-Host "Deja present. Mise a jour du depot..."
    git -C $Cible pull --ff-only
} else {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Cible) | Out-Null
    git clone --depth 1 https://github.com/Faceplugin-ltd/Open-Source-Face-Recognition-SDK $Cible
}

$Venv = Join-Path $Cible ".venv"
$Py = Join-Path $Venv "Scripts\python.exe"

# Un environnement deja construit sur un mauvais interpreteur doit partir :
# le reutiliser reproduirait exactement la panne qu'on repare.
if (Test-Path $Py) {
    & $Py -c "import sys; sys.exit(0 if sys.version_info[:2] <= (3, 12) else 1)"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Environnement existant bati sur un Python trop recent : il est refait."
        Remove-Item -Recurse -Force $Venv
    }
}

if (-not (Test-Path $Py)) {
    Write-Host "Creation de son environnement Python..."
    & $Python[0] $Python[1] -m venv $Venv
    if ($LASTEXITCODE -ne 0) { Write-Host "ARRET : creation de l'environnement en echec."; exit 1 }
}

Write-Host "Installation de ses dependances (torch, opencv...)..."
& $Py -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { Write-Host "ARRET : mise a jour de pip en echec."; exit 1 }

& $Py -m pip install -r (Join-Path $Cible "requirements.txt")
# `$ErrorActionPreference` ne couvre PAS le code de sortie d'un programme
# externe sous PowerShell 5.1 : sans ce controle, un pip en echec passait
# inapercu et le script annoncait " Termine ".
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "ARRET : l'installation des dependances a echoue. Rien n'est utilisable."
    Write-Host "Envoie les lignes ci-dessus telles quelles."
    exit 1
}

# Le controle qui compte : le moteur s'importe-t-il vraiment ?
Push-Location $Cible
& $Py -c "import cv2, torch; from run import GetImageInfo; print('moteur importe : OK')"
$ok = $LASTEXITCODE
Pop-Location
if ($ok -ne 0) {
    Write-Host "ARRET : les paquets sont poses mais le moteur ne s'importe pas."
    exit 1
}

Write-Host ""
Write-Host "Termine. Verifie avec :"
Write-Host "  python scripts\doctor.py     -> ligne ' Visages (Faceplugin) '"
Write-Host ""
Write-Host "Rappel : les fonctions biometriques (extraire un gabarit, comparer"
Write-Host "deux visages) demandent ta confirmation a chaque appel. ARENA ne"
Write-Host "tient aucune base de visages et n'en constitue pas."
