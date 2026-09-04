# Lance ARENA en entier : le serveur, le tunnel, et l'adresse a mettre dans le
# telephone -- affichee en QR code pour ne pas avoir a la retaper.
#
# L'adresse d'un tunnel Cloudflare gratuit change a chaque demarrage. La
# recopier a la main sur un telephone est le genre de corvee qui fait qu'on
# n'utilise plus l'outil. D'ou le QR.
#
# CE FICHIER EST EN ASCII PUR, ET CE N'EST PAS UN DETAIL DE STYLE.
# PowerShell 5 lit un .ps1 sans BOM comme de l'ANSI : un tiret long ou un
# guillemet francais y devient deux caracteres parasites, dont l'un casse les
# guillemets du code. Mesure le 2026-08-27 : le script entier a refuse de se
# lancer a cause d'un seul tiret long dans un Write-Host.
# Ne pas reintroduire d'accents ici.
#
# Ce script ne cache aucune panne : si Ollama est absent, si cloudflared est
# introuvable, si l'adresse ne sort pas, il le dit et s'arrete.

$ErrorActionPreference = "Stop"
$racine = Split-Path -Parent $PSScriptRoot
Set-Location $racine

Write-Host ""
Write-Host "  ARENA -- demarrage" -ForegroundColor Cyan
Write-Host "  $racine"
Write-Host ""

# --- 1. Ollama ---------------------------------------------------------------
# On regarde avant de lancer : un serveur qui demarre sans modele repond a
# chaque message "Ollama est hors-ligne", et on cherche pourquoi.
try {
    Invoke-WebRequest -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 3 -UseBasicParsing | Out-Null
    Write-Host "  [ok] Ollama repond" -ForegroundColor Green
} catch {
    Write-Host "  [!]  Ollama ne repond pas sur le port 11434." -ForegroundColor Yellow
    Write-Host "       Lance 'ollama serve' dans un autre terminal, sinon ARENA" -ForegroundColor Yellow
    Write-Host "       refusera chaque message au lieu d'inventer une reponse." -ForegroundColor Yellow
}

# --- 2. cloudflared ----------------------------------------------------------
$cloudflared = $null
foreach ($chemin in @(
    "C:\Program Files (x86)\cloudflared\cloudflared.exe",
    "C:\Program Files\cloudflared\cloudflared.exe"
)) {
    if (Test-Path $chemin) { $cloudflared = $chemin; break }
}
if (-not $cloudflared) {
    $trouve = Get-Command cloudflared -ErrorAction SilentlyContinue
    if ($trouve) { $cloudflared = $trouve.Source }
}
if (-not $cloudflared) {
    Write-Host "  [X] cloudflared introuvable." -ForegroundColor Red
    Write-Host "      Installe-le : winget install --id Cloudflare.cloudflared -e --source winget"
    exit 1
}

# --- 2 bis. L'interface -------------------------------------------------------
#
# **Le serveur sert l'ANCIENNE interface en silence quand la nouvelle n'est
# pas compilee.** `apps/pwa/dist/` est ignore par git (Vite le regenere), donc
# il n'existe jamais apres un clone ou un `git pull` : `interface_servie()`
# retombe sur `apps/frontend/index.html` sans le dire.
#
# Mesure du 03/09/2026 : le proprietaire branche son telephone sur son PC,
# voit son ancienne interface et l'espace Dioumtoukay disparu, et croit que
# du travail a ete perdu. Rien ne l'etait - un fichier de compilation
# manquait, et personne ne le disait.
$dist = Join-Path $racine "apps\pwa\dist\index.html"
if (Test-Path $dist) {
    Write-Host "  [ok] interface : la nouvelle (PWA)" -ForegroundColor Green
} else {
    $npm = Get-Command npm -ErrorAction SilentlyContinue
    if (-not $npm) {
        Write-Host "  [X] interface : l'ANCIENNE sera servie." -ForegroundColor Yellow
        Write-Host "      La nouvelle n'est pas compilee et npm est introuvable."
        Write-Host "      Sans elle : pas d'espace Dioumtoukay, pas de projet video."
        Write-Host "      Installe Node : winget install OpenJS.NodeJS.LTS"
        Write-Host "      puis relance ce script."
    } else {
        Write-Host "  [..] interface : compilation de la nouvelle (une fois)..." -ForegroundColor Cyan
        $pwa = Join-Path $racine "apps\pwa"
        Push-Location $pwa
        $prefNpm = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try {
            if (-not (Test-Path (Join-Path $pwa "node_modules"))) { npm ci 2>&1 | Out-Null }
            npm run build 2>&1 | Out-Null
        } finally {
            $ErrorActionPreference = $prefNpm
            Pop-Location
        }
        if (Test-Path $dist) {
            Write-Host "  [ok] interface : la nouvelle (PWA), compilee a l'instant" -ForegroundColor Green
        } else {
            Write-Host "  [X] interface : la compilation a echoue, l'ANCIENNE sera servie." -ForegroundColor Yellow
            Write-Host "      Pour voir l'erreur : cd apps\pwa ; npm run build"
        }
    }
}

# --- 3. Le serveur -----------------------------------------------------------
$activation = Join-Path $racine ".venv\Scripts\Activate.ps1"
if (Test-Path $activation) {
    $demarrage = "& '$activation' ; python -m uvicorn apps.backend.main:app --port 8000"
} else {
    $demarrage = "python -m uvicorn apps.backend.main:app --port 8000"
}
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$racine' ; $demarrage"
Write-Host "  [ok] serveur lance dans sa propre fenetre" -ForegroundColor Green

# --- 4. Le tunnel ------------------------------------------------------------
$journal = Join-Path $env:TEMP "arena-tunnel.log"
Remove-Item $journal -ErrorAction SilentlyContinue
$commandeTunnel = "& '$cloudflared' tunnel --url http://localhost:8000 --logfile '$journal'"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $commandeTunnel
Write-Host "  [ok] tunnel lance dans sa propre fenetre" -ForegroundColor Green
Write-Host ""
Write-Host "  Recherche de l'adresse publique..." -NoNewline

$adresse = $null
foreach ($essai in 1..40) {
    Start-Sleep -Milliseconds 750
    Write-Host "." -NoNewline
    if (-not (Test-Path $journal)) { continue }
    $texte = Get-Content $journal -Raw -ErrorAction SilentlyContinue
    if ($texte -match "(https://[a-z0-9-]+\.trycloudflare\.com)") {
        $adresse = $Matches[1]
        break
    }
}
Write-Host ""

if (-not $adresse) {
    Write-Host ""
    Write-Host "  [X] Pas d'adresse apres 30 secondes." -ForegroundColor Red
    Write-Host "      Regarde la fenetre du tunnel : elle dit pourquoi."
    Write-Host "      Journal : $journal"
    exit 1
}

# --- 5. L'adresse, lisible et scannable --------------------------------------
Write-Host ""
Write-Host "  ================================================================"
Write-Host "   $adresse" -ForegroundColor Green
Write-Host "  ================================================================"
Write-Host ""
try {
    Set-Clipboard -Value $adresse
    Write-Host "  (copiee dans le presse-papier)" -ForegroundColor DarkGray
} catch { }

# --- Annonce au serveur permanent ---------------------------------------------
#
# **Le tunnel change de nom a chaque demarrage.** Sans cette annonce, le
# proprietaire recopiait une nouvelle adresse dans son telephone chaque fois
# qu'il allumait sa machine - plusieurs fois par semaine, pour un PC qui
# tourne environ quatre heures par jour (mesure du 03/09/2026).
#
# Le PC depose donc son adresse du jour sur le serveur permanent, et le
# telephone la demande. Rien ne transite par ce serveur quand la machine
# repond : il ne sert que d'annuaire.
#
# Sans `USMAN_ANNONCE_URL` dans `.env`, rien n'est tente et rien n'est promis.
$annonceUrl = $null
$annonceCle = $null
$fichierEnv = Join-Path $racine ".env"
if (Test-Path $fichierEnv) {
    foreach ($ligne in Get-Content $fichierEnv) {
        if ($ligne -match '^\s*USMAN_ANNONCE_URL\s*=\s*(.+)$') { $annonceUrl = $Matches[1].Trim() }
        if ($ligne -match '^\s*USMAN_API_KEY\s*=\s*(.+)$')     { $annonceCle = $Matches[1].Trim() }
    }
}

if ($annonceUrl -and $annonceCle) {
    $prefAnnonce = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $corps = @{ adresse = $adresse; machine = $env:COMPUTERNAME } | ConvertTo-Json
        Invoke-RestMethod -Method Post -Uri "$($annonceUrl.TrimEnd('/'))/machine/adresse" `
            -Headers @{ Authorization = "Bearer $annonceCle" } `
            -ContentType "application/json" -Body $corps -TimeoutSec 20 | Out-Null
        Write-Host "  [ok] adresse annoncee au serveur permanent" -ForegroundColor Green
        Write-Host "       ton telephone la trouvera tout seul." -ForegroundColor DarkGray
    } catch {
        # Une annonce ratee n'empeche pas ARENA de tourner : elle prive
        # seulement le telephone de la trouver sans copier-coller. On le dit
        # au lieu de laisser croire que c'est fait.
        Write-Host "  [X] annonce au serveur permanent impossible." -ForegroundColor Yellow
        Write-Host "      $($_.Exception.Message)" -ForegroundColor DarkGray
        Write-Host "      ARENA tourne quand meme - colle l'adresse a la main."
    } finally {
        $ErrorActionPreference = $prefAnnonce
    }
} else {
    Write-Host "  (pas d'annonce : USMAN_ANNONCE_URL absente de .env)" -ForegroundColor DarkGray
}

# Le carre a scanner. Le paquet `qrcode` peut manquer : il n'etait declare
# nulle part avant le 02/09/2026, donc il n'etait installe chez personne, et
# un environnement monte avant cette date ne l'aura toujours pas.
#
# Ce que ca donnait : une trace Python en plein demarrage, qui se lit comme
# " ARENA n'a pas demarre " alors que le serveur ET le tunnel tournent, et que
# l'adresse est juste au-dessus. Le QR code est un confort ; l'adresse suffit.
#
# La phrase " scanne ce carre " n'est plus affichee que s'il y a un carre :
# l'annoncer avant de savoir, c'etait promettre ce qui allait echouer.
# `2>$null` ne suffit PAS. Sous `$ErrorActionPreference = "Stop"`, la sortie
# d'erreur d'un programme EXTERNE devient une erreur bloquante
# (`NativeCommandError`) avant meme la redirection : la trace Python
# s'affichait quand meme, en rouge, a la fin d'un demarrage reussi
# (mesure du 03/09/2026 sur sa machine, apres un premier correctif qui
# croyait la redirection suffisante).
#
# On rend donc la preference a "Continue" le temps de cet appel, et on la
# remet ensuite : ailleurs dans ce script, une erreur DOIT arreter.
$carre = $null
$prefPrecedente = $ErrorActionPreference
$ErrorActionPreference = "Continue"
try {
    $carre = python -c "import qrcode,sys; q=qrcode.QRCode(border=2); q.add_data(sys.argv[1]); q.make(); q.print_ascii(invert=True)" $adresse 2>$null
    if ($LASTEXITCODE -ne 0) { $carre = $null }
} catch {
    $carre = $null
} finally {
    $ErrorActionPreference = $prefPrecedente
}

Write-Host ""
if ($carre) {
    Write-Host "  Scanne ce carre avec ton telephone, puis colle l'adresse dans le"
    Write-Host "  panneau Backend de l'application." -ForegroundColor Cyan
    Write-Host ""
    $carre | ForEach-Object { Write-Host $_ }
} else {
    Write-Host "  Pas de QR code : le paquet qrcode n'est pas installe." -ForegroundColor DarkGray
    Write-Host "  L'adresse ci-dessus marche telle quelle - tape-la dans le panneau"
    Write-Host "  Backend de ton telephone." -ForegroundColor Cyan
    Write-Host "  Pour avoir le carre au prochain demarrage : pip install qrcode" -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "  Laisse les deux fenetres ouvertes. Fermer celle du tunnel change"
Write-Host "  l'adresse au prochain demarrage." -ForegroundColor DarkGray
Write-Host ""