"""Ce que le lanceur importe doit être installable.

**Défaut mesuré le 02/09/2026, sur la machine du propriétaire**, au moment où
il démarre ARENA pour la première fois de la soirée :

```
python -c "import qrcode,sys; ..."
ModuleNotFoundError: No module named 'qrcode'
```

`scripts/lancer_arena.ps1` appelle `qrcode` depuis PowerShell, par
`python -c`. Un scan d'imports Python ne voit **rien** : ce n'est pas un
`import` dans un `.py`, c'est une chaîne dans un script shell. Le paquet n'a
donc jamais été déclaré dans `requirements.txt`, jamais installé par
`pip install -r requirements.txt`, et **le QR code n'a jamais marché chez
personne** depuis que le lanceur existe.

Ce fichier ferme ce trou : tout module importé par un `python -c` du lanceur
doit être déclaré, ou faire partie de la bibliothèque standard.

`test_le_lanceur_ne_plante_pas_sans_le_paquet` tient l'autre moitié — le
défaut visible n'était pas l'absence du carré, c'était la trace Python en
plein démarrage, qui se lit comme « ARENA n'a pas démarré » alors que tout
tournait.
"""
import re
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
LANCEUR = RACINE / "scripts" / "lancer_arena.ps1"

#: Les modules importés dans un `python -c "..."` du script.
_IMPORT_DANS_PYTHON_C = re.compile(r"""python\s+-c\s+["'](.*?)["']""", re.DOTALL)
_MODULES = re.compile(r"\bimport\s+([\w,\s.]+)")


def _modules_du_lanceur() -> set:
    """Les modules que le lanceur importe, vus depuis son texte."""
    texte = LANCEUR.read_text(encoding="utf-8")
    trouves = set()
    for extrait in _IMPORT_DANS_PYTHON_C.findall(texte):
        for groupe in _MODULES.findall(extrait):
            for module in groupe.split(","):
                nom = module.strip().split(".")[0].split(" ")[0]
                if nom:
                    trouves.add(nom)
    return trouves


def _paquets_declares() -> set:
    """Les paquets de `requirements.txt`, en minuscules."""
    lignes = (RACINE / "requirements.txt").read_text(encoding="utf-8").splitlines()
    return {
        re.split(r"[=<>!\[]", ligne.strip(), maxsplit=1)[0].strip().lower()
        for ligne in lignes if ligne.strip() and not ligne.strip().startswith("#")
    }


def test_le_lanceur_importe_bien_quelque_chose():
    """Garde du garde : si la lecture cassait, le test suivant passerait à vide."""
    assert _modules_du_lanceur(), "aucun import lu dans le lanceur : la mesure est morte"


def test_tout_ce_que_le_lanceur_importe_est_declare():
    """Le défaut du 02/09/2026 : `qrcode` appelé, jamais déclaré, jamais installé."""
    declares = _paquets_declares()
    standard = sys.stdlib_module_names

    manquants = sorted(
        module for module in _modules_du_lanceur()
        if module.lower() not in declares and module not in standard
    )

    assert manquants == [], (
        "le lanceur importe des paquets que `pip install -r requirements.txt` "
        f"n'installe pas : {manquants}")


def test_qrcode_est_declare_avec_le_fichier_qui_l_utilise():
    """`requirements.txt` dit de lui-même : « uniquement ce que le code importe »,
    et chaque ligne nomme le fichier concerné. Celle-ci ne fait pas exception."""
    texte = (RACINE / "requirements.txt").read_text(encoding="utf-8")

    ligne = next(ligne for ligne in texte.splitlines()
                 if ligne.strip().startswith("qrcode"))
    assert "lancer_arena" in ligne, "la dependance ne dit pas qui s'en sert"


def test_le_lanceur_ne_plante_pas_sans_le_paquet():
    """Le défaut visible n'était pas l'absence du carré, c'était la trace Python.

    Elle s'affichait après « ARENA -- demarrage » et juste avant « Laisse les
    deux fenetres ouvertes » : au milieu d'un démarrage réussi.
    """
    texte = LANCEUR.read_text(encoding="utf-8")

    assert "2>$null" in texte, "l'erreur Python remonte encore a l'ecran"
    assert "$LASTEXITCODE" in texte, "le lanceur ne regarde pas si le carre a ete produit"
    assert "pip install qrcode" in texte, "il ne dit pas comment retrouver le carre"


def test_l_adresse_est_donnee_meme_sans_carre():
    """Sans QR code, il reste à taper l'adresse : elle doit être annoncée."""
    texte = LANCEUR.read_text(encoding="utf-8")

    apres_le_carre = texte.split("$LASTEXITCODE", 1)[1]
    assert "tape-la" in apres_le_carre or "adresse ci-dessus" in apres_le_carre


def test_la_phrase_scanne_ce_carre_n_est_dite_que_s_il_y_a_un_carre():
    """L'annoncer avant de savoir, c'était promettre ce qui allait échouer."""
    texte = LANCEUR.read_text(encoding="utf-8")

    position_test = texte.index("$LASTEXITCODE")
    position_phrase = texte.index("Scanne ce carre")

    assert position_phrase > position_test, (
        "« Scanne ce carre » est encore affiche avant de savoir s'il y en a un")
