"""Un `.ps1` non-ASCII ne se lance pas du tout sous Windows PowerShell.

**Mesuré le 03/09/2026, sur la machine du propriétaire.** Deux installeurs
refusent de démarrer :

    Le terminateur " est manquant dans la chaîne.
    ... ite-Host "  UI/UX Pro Max â€" intelligence de design, a cote d'ARENA"

Windows PowerShell 5.1 décode un `.ps1` **sans BOM** en cp1252, pas en UTF-8.
Un `—` (trois octets en UTF-8) devient trois caractères parasites, `«` et `»`
en produisent deux chacun. Quand ces octets tombent dans une chaîne, le
guillemet fermant n'est plus trouvé et **le script entier est refusé avant la
première ligne**.

La solution évidente — enregistrer en UTF-8 avec BOM — est fermée ici :
`test_aucun_fichier_ne_commence_par_un_bom` l'interdit, pour de bonnes
raisons de son côté. Reste la seule qui marche partout : **de l'ASCII pur**.

Ce que ça a coûté avant d'être vu : cinq des sept scripts du dépôt en
contenaient. Les trois plus anciens n'avaient pas encore cassé — leurs
caractères ne tombaient pas dans une chaîne. Ils attendaient la mauvaise
ligne au mauvais endroit.
"""
import json
import re
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Optional

import pytest

RACINE = Path(__file__).resolve().parent.parent
SCRIPTS = sorted((RACINE / "scripts").glob("*.ps1"))

#: Ce qu'on écrit spontanément en français et qui casse : les guillemets
#: chevrons et le tiret cadratin. Écrire `"` et `-` à la place ne coûte rien.
PIEGES = {"«": '"', "»": '"', "—": "-", "’": "'"}


def test_il_y_a_bien_des_scripts_a_verifier():
    """Une garde qui ne mesure rien passe toujours."""
    assert SCRIPTS, "aucun .ps1 trouve : ce fichier ne garde plus rien"


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_chaque_script_powershell_est_en_ascii_pur(script):
    texte = script.read_text(encoding="utf-8")
    hors = sorted({c for c in texte if ord(c) > 127})

    conseil = ", ".join(f"« {c} » -> « {PIEGES[c]} »" for c in hors if c in PIEGES)
    assert not hors, (
        f"{script.name} contient {hors} : PowerShell 5.1 lit ce fichier en "
        f"cp1252 et refusera de le lancer. {conseil or 'Remplace par de l ASCII.'}")


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_aucune_ligne_ne_laisse_une_chaine_ouverte(script):
    """Le symptôme exact vu par le propriétaire : « Le terminateur " est
    manquant ». Il vient d'un guillemet en trop dans un `Write-Host`, que
    l'ASCII seul ne garantit pas."""
    impaires = [n for n, ligne in enumerate(script.read_text(encoding="utf-8").split("\n"), 1)
                if ligne.count('"') % 2]

    assert not impaires, (
        f"{script.name} : guillemets impairs lignes {impaires}. PowerShell "
        "refusera le script entier, pas seulement cette ligne.")


def test_le_piege_est_nomme_dans_le_fichier():
    """Une règle sans sa raison se fait retirer par le prochain qui trouve
    l'ASCII inutilement austère dans un dépôt francophone."""
    source = Path(__file__).read_text(encoding="utf-8")

    assert "cp1252" in source
    assert "BOM" in source, "le lecteur ne saura pas pourquoi le BOM est exclu"


#: Les installeurs qui lancent un programme externe. `git`, `pip`, `python` :
#: aucun ne leve d'exception PowerShell en echouant.
INSTALLEURS = [p for p in SCRIPTS if p.name.startswith("installer_")]


@pytest.mark.parametrize("script", INSTALLEURS, ids=lambda p: p.name)
def test_un_installeur_verifie_le_code_de_sortie_de_ce_quil_lance(script):
    """**`$ErrorActionPreference = "Stop"` ne couvre PAS un programme externe.**

    Mesuré le 03/09/2026 sur la machine du propriétaire. Son Python est 3.14 ;
    `torch==2.4.1` n'a de roues que pour 3.8 à 3.12. Le `pip install` a donc
    échoué de bout en bout — et l'installeur a affiché « Termine ».

    Le mensonge n'a été rattrapé qu'une étape plus loin, par le diagnostic :
    `ModuleNotFoundError: No module named 'cv2'`. Sans cette ligne au
    diagnostic, il aurait cru la capacité installée.

    Un installeur qui ne regarde pas `$LASTEXITCODE` annonce un succès qu'il
    n'a pas mesuré. C'est la règle 3 de la mentalité d'Usman, appliquée à un
    script.
    """
    texte = script.read_text(encoding="utf-8")

    assert "$LASTEXITCODE" in texte, (
        f"{script.name} ne regarde jamais le code de sortie de ce qu'il lance : "
        "il annoncera « Termine » sur un echec.")


@pytest.mark.parametrize("script", INSTALLEURS, ids=lambda p: p.name)
def test_un_installeur_sarrete_au_lieu_de_continuer(script):
    """Voir l'échec ne suffit pas : il faut s'arrêter dessus."""
    texte = script.read_text(encoding="utf-8")

    assert "exit 1" in texte, (
        f"{script.name} peut voir un echec sans jamais s'arreter")


def test_un_appel_optionnel_neutralise_la_preference_derreur():
    """`2>$null` ne suffit pas quand `$ErrorActionPreference = "Stop"`.

    **Mesuré deux fois le 03/09/2026, sur sa machine.** Le paquet `qrcode`
    manque, donc `python -c "import qrcode..."` écrit sur la sortie d'erreur.
    Sous `Stop`, PowerShell 5.1 en fait une erreur **bloquante**
    (`NativeCommandError`) avant même la redirection : la trace Python
    s'affichait en rouge à la fin d'un démarrage parfaitement réussi.

    Un premier correctif avait ajouté `2>$null` et une branche sur
    `$LASTEXITCODE`, en croyant la redirection suffisante. **Elle ne l'est
    pas** — et c'est pour ça que ce test existe plutôt qu'un commentaire.

    Ce que ça coûtait : le propriétaire lit « ARENA n'a pas démarré » alors
    que le serveur, le tunnel et l'adresse sont juste au-dessus.
    """
    texte = (RACINE / "scripts" / "lancer_arena.ps1").read_text(encoding="utf-8")
    # Ancre sur `$prefPrecedente` : `$carre = $null` apparait trois fois
    # (initialisation, echec du code de sortie, catch), et couper dessus
    # mesurait un morceau qui ne contenait pas le `finally` — le test
    # tombait alors sur un fichier parfaitement correct.
    bloc = texte.split("$prefPrecedente = $ErrorActionPreference")[1][:900]

    assert '$ErrorActionPreference = "Continue"' in bloc, (
        "l'appel optionnel tourne encore sous Stop : sa trace s'affichera")
    assert "finally" in bloc, (
        "la preference n'est pas rendue : une vraie erreur ne bloquerait plus "
        "le reste du script")


def test_chaque_reglage_lu_par_un_script_est_documente_dans_env_example():
    """**Un reglage que personne ne peut decouvrir est un reglage que personne
    ne mettra.**

    Mesure du 04/09/2026 : `lancer_arena.ps1` lisait `USMAN_ANNONCE_URL` — la
    ligne sans laquelle le telephone ne trouve pas la machine — et cette
    variable n'apparaissait nulle part dans `.env.example`. Le seul endroit
    ou elle etait ecrite etait un message de chat. Un lanceur qui dit
    « pas d'annonce : USMAN_ANNONCE_URL absente de .env » ne sert a rien si le
    fichier d'exemple ne la mentionne jamais.

    Le meme defaut a deja coute une consigne fausse (`ALLOWED_ORIGINS` au lieu
    de `USMAN_ALLOWED_ORIGINS`, 03/09/2026) : quand le nom exact ne vit que
    dans une conversation, il finit par etre recopie de travers.
    """
    exemple = (RACINE / ".env.example").read_text(encoding="utf-8")

    manquantes = {}
    for script in SCRIPTS:
        texte = script.read_text(encoding="utf-8", errors="replace")
        for nom in sorted(set(re.findall(r"USMAN_[A-Z0-9_]+", texte))):
            if nom not in exemple:
                manquantes.setdefault(nom, []).append(script.name)

    assert not manquantes, (
        "Reglage(s) lu(s) par un script mais absent(s) de .env.example : "
        + ", ".join(f"{nom} ({', '.join(ou)})" for nom, ou in manquantes.items())
    )


# --- L'analyse reelle, quand un interpreteur est disponible -----------------------
#
# Tout ce qui precede lit le TEXTE des scripts. C'est utile et ca a attrape de
# vraies fautes, mais aucune de ces gardes ne repond a la seule question qui
# compte le matin ou il double-clique : **est-ce que PowerShell accepte ce
# fichier ?** Deux fois dans la nuit du 03/09/2026, la reponse etait non, et il
# l'a apprise par un ecran rouge sur sa machine.

def _interpreteur() -> Optional[str]:
    """Un PowerShell utilisable ici, ou `None`. Jamais suppose present."""
    for nom in ("pwsh", "powershell", "/opt/pwsh/pwsh"):
        chemin = shutil.which(nom) or (nom if Path(nom).exists() else None)
        if chemin:
            return chemin
    return None


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_powershell_accepte_vraiment_le_fichier(script):
    """Le script est **analyse par PowerShell**, pas relu par une expression.

    Saute quand aucun interpreteur n'est la — dire « OK » sans avoir analyse
    serait exactement le defaut que ce depot traque partout ailleurs.
    """
    pwsh = _interpreteur()
    if not pwsh:
        pytest.skip("aucun PowerShell ici : rien n'a ete analyse, et on le dit")

    ordre = (
        "$e = $null; "
        f"[System.Management.Automation.Language.Parser]::ParseFile('{script}', "
        "[ref]$null, [ref]$e) | Out-Null; "
        "if ($e.Count) { $e | ForEach-Object { "
        "'ligne ' + $_.Extent.StartLineNumber + ' : ' + $_.Message } }"
    )
    issue = subprocess.run([pwsh, "-NoProfile", "-Command", ordre],
                           capture_output=True, text=True, timeout=180)

    assert issue.returncode == 0 and not issue.stdout.strip(), (
        f"PowerShell refuse {script.name} :\n{issue.stdout}{issue.stderr}")


def test_la_re_annonce_envoie_vraiment_ce_quil_faut():
    """Le bloc de re-annonce du lanceur est **execute**, contre un faux serveur.

    Pourquoi ce test et pas seulement l'analyse syntaxique : un script qui
    s'analyse peut n'envoyer nulle part, ou envoyer sans la cle. Ce qui compte
    est ce qui arrive au serveur permanent.

    Ce qu'il garde : une seule annonce ne suffit pas. Le serveur permanent
    oublie l'adresse a chaque redemarrage — cinq mises en ligne dans la nuit du
    04/09/2026 — pendant que la machine, elle, tourne toujours. Sans re-annonce,
    le telephone retombe sur le serveur permanent et les modeles lourds ne
    servent plus, sans que rien ne le dise.

    `Start-Sleep` est neutralise : on teste l'appel, pas l'attente de dix
    minutes.
    """
    pwsh = _interpreteur()
    if not pwsh:
        pytest.skip("aucun PowerShell ici : rien n'a ete execute, et on le dit")

    texte = (RACINE / "scripts" / "lancer_arena.ps1").read_text(encoding="utf-8")
    marque = 'Start-Job -Name "arena-annonce" -ScriptBlock {'
    assert marque in texte, "le lanceur n'annonce plus son adresse en tache de fond"

    # Le bloc REEL, decoupe sur ses accolades — jamais recopie ici : un test
    # qui contient sa propre copie du code ne surveille que lui-meme.
    reste = texte[texte.index(marque) + len(marque):]
    profondeur, bloc = 1, ""
    for caractere in reste:
        if caractere == "{":
            profondeur += 1
        elif caractere == "}":
            profondeur -= 1
            if profondeur == 0:
                break
        bloc += caractere

    recu: list = []

    class Ecouteur(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802 — nom impose par http.server
            taille = int(self.headers.get("Content-Length", 0))
            recu.append({"chemin": self.path,
                         "auth": self.headers.get("Authorization"),
                         "corps": json.loads(self.rfile.read(taille) or b"{}")})
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')

        def log_message(self, *args):
            pass

    serveur = HTTPServer(("127.0.0.1", 0), Ecouteur)
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    port = serveur.server_address[1]
    try:
        programme = (
            "function Start-Sleep { param($Seconds) }\n"
            "$bloc = { " + bloc + " }\n"
            f'& $bloc "http://127.0.0.1:{port}" "cle-de-test" '
            '"https://tunnel-du-jour.test" "PC-DE-TEST"\n'
        )
        processus = subprocess.Popen([pwsh, "-NoProfile", "-Command", programme],
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     text=True)
        try:
            processus.wait(timeout=4)  # la boucle est infinie : on la coupe
        except subprocess.TimeoutExpired:
            processus.kill()
    finally:
        serveur.shutdown()

    assert recu, "le bloc de re-annonce n'a rien envoye"
    premiere = recu[0]
    assert premiere["chemin"] == "/machine/adresse"
    assert premiere["auth"] == "Bearer cle-de-test", (
        "sans la cle, le serveur permanent refuse et la re-annonce ne sert a rien")
    assert premiere["corps"]["adresse"] == "https://tunnel-du-jour.test"
    assert premiere["corps"]["machine"] == "PC-DE-TEST"
