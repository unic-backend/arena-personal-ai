# Installe MoneyPrinterTurbo A COTE d'ARENA, jamais dedans.
#
# Ce projet-la est un service separe : il a ses dependances, sa configuration et
# ses cles. Le copier dans ce depot melangerait deux histoires et ferait entrer
# ses secrets dans notre historique. ARENA lui parle par son API HTTP, comme il
# parle a WanGP.
#
#   powershell -ExecutionPolicy Bypass -File scripts\installer_moneyprinter.ps1
#
# Rien n'est lance a la fin : l'installation et le demarrage sont deux gestes
# distincts, et le second se fait quand tu decides de depenser ta carte graphique.

$ErrorActionPreference = "Stop"

$Racine = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Cible = Join-Path (Split-Path -Parent $Racine) "MoneyPrinterTurbo"

Write-Host "=============================================================="
Write-Host "  MoneyPrinterTurbo — installation a cote d'ARENA"
Write-Host "  Destination : $Cible"
Write-Host "=============================================================="

# 1. Ce qu'il faut avant de commencer. On verifie, on ne suppose pas.
foreach ($outil in @("git", "python", "ffmpeg")) {
    if (-not (Get-Command $outil -ErrorAction SilentlyContinue)) {
        Write-Host "[ABSENT] $outil est introuvable." -ForegroundColor Red
        if ($outil -eq "ffmpeg") {
            Write-Host "         -> winget install ffmpeg   (le montage ne peut pas s'en passer)"
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
    git clone --depth 1 https://github.com/harry0703/MoneyPrinterTurbo.git $Cible
}

# 3. Son propre environnement virtuel. Il ne partage pas celui d'ARENA : ses
#    dependances sont lourdes et n'ont rien a faire dans les notres.
$Venv = Join-Path $Cible ".venv"
if (-not (Test-Path $Venv)) {
    python -m venv $Venv
}
& (Join-Path $Venv "Scripts\python.exe") -m pip install --upgrade pip
& (Join-Path $Venv "Scripts\python.exe") -m pip install -r (Join-Path $Cible "requirements.txt")

# 4. Sa configuration. On copie l'exemple sans jamais y ecrire une cle : c'est
#    a toi de le faire, et elle ne doit exister que sur cette machine.
$Config = Join-Path $Cible "config.toml"
if (-not (Test-Path $Config)) {
    Copy-Item (Join-Path $Cible "config.example.toml") $Config
    Write-Host "[CREE]   config.toml"
}

Write-Host ""
Write-Host "=============================================================="
Write-Host "  IL RESTE DEUX CHOSES A FAIRE, ET ELLES SONT A TOI"
Write-Host "=============================================================="
Write-Host ""
Write-Host "1. Ouvre $Config et mets :"
Write-Host ""
Write-Host '     llm_provider = "ollama"' -ForegroundColor Yellow
Write-Host '     ollama_base_url = "http://127.0.0.1:11434"'
Write-Host '     ollama_model_name = "qwen3.5:9b"'
Write-Host ""
Write-Host "   Sans cette ligne, tes scripts video partent chez un fournisseur"
Write-Host "   d'IA. C'est exactement ce que DEC-0002 refuse."
Write-Host ""
Write-Host "2. Une cle Pexels (gratuite, pexels.com/api) pour les plans video :"
Write-Host ""
Write-Host '     pexels_api_keys = ["ta-cle"]' -ForegroundColor Yellow
Write-Host ""
Write-Host "   Elle vit dans CE fichier-la, jamais dans le depot d'ARENA."
Write-Host ""
Write-Host "Pour le lancer, ensuite :"
Write-Host ""
Write-Host "   cd $Cible" -ForegroundColor Green
Write-Host "   .venv\Scripts\python.exe -m uvicorn app.asgi:app --host 127.0.0.1 --port 8080" -ForegroundColor Green
Write-Host ""
Write-Host "Puis, depuis ARENA :  python scripts\doctor.py"
Write-Host "La ligne « Video courte (MPT) » doit passer a [OK]."
Write-Host ""
