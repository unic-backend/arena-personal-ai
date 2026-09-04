"""Le pont vers le SDK Faceplugin — 49 lignes que rien n'executait.

**Mesure du 04/09/2026 :** `core/connectors/ponts/faceplugin_pont.py`,
couverture **0 %**. Aucun test ne le chargeait, ne l'appelait, ne le lisait.
C'est pourtant lui qui tourne sur sa machine quand une capacite « visage »
est demandee — le connecteur ne fait que le lancer et lire sa sortie.

Ce qui n'etait tenu par rien, et qui compte le plus : **la garde qui retire
les gabarits biometriques** de `detecter` et `reperes`. Le proprietaire a pose
la contrainte en toutes lettres — « pas d'enregistrement biometrique
implicite » — et elle ne vivait que dans une fonction que personne ne
verifiait.

**Comment ces tests sont honnetes.** Le pont est lance comme il l'est en vrai :
un sous-processus, sur son vrai fichier, par sa vraie ligne de commande. Seul
le SDK — absent de cette machine, et hors du depot — est remplace par un
double qui rend des nombres inventes et le dit. On ne teste donc jamais le
SDK, et **aucune donnee biometrique reelle n'entre ici** : uniquement des
listes de flottants ecrites a la main.

**`--cov` continuera d'afficher 0 % sur ce fichier, et ce n'est pas une
erreur** : l'outil de couverture mesure le processus qui le lance, pas les
sous-processus. C'est justement cette mesure a 0 % qui a fait croire, le
04/09/2026, que le pont etait du code mort. Le nombre a lire ici est le
nombre de tests, pas le pourcentage.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
PONT = RACINE / "core" / "connectors" / "ponts" / "faceplugin_pont.py"
MARQUEUR = "@@ARENA@@"

#: Un double du SDK. Il imite l'API relevee dans le `run.py` reel — rien de
#: plus — et bavarde sur la sortie standard comme le vrai le fait.
FAUX_SDK = '''
print("priors nums:4420")  # le vrai moteur ecrit ceci avant de rendre la main

VISAGES = 2


class Tableau(list):
    """Le strict minimum de ce que le pont attend d'un tableau : `reshape`."""

    def reshape(self, *_):
        plat = []
        for element in self:
            plat.extend(element if isinstance(element, (list, tuple)) else [element])
        return Tableau(plat)


def GetImageInfo(image, faceMaxCount):
    n = min(VISAGES, faceMaxCount)
    boxes = [Tableau([1.0, 2.0, 3.0, 4.0]) for _ in range(n)]
    scores = [Tableau([[0.9]]) for _ in range(n)]
    landmarks = [Tableau([[5.0, 6.0]]) for _ in range(n)]
    aligns = [None] * n
    features = [Tableau([0.1, 0.2, 0.3]) for _ in range(n)]
    return n, boxes, scores, landmarks, aligns, features


def get_similarity(f1, f2):
    return (sum(a * b for a, b in zip(list(f1), list(f2))) + 1) * 50
'''

#: Doubles des deux bibliotheques du SDK, deposees a cote de `run.py`.
#:
#: **Elles ne sont pas une commodite : elles sont la condition pour que ce test
#: existe.** Le premier jet importait le vrai `cv2` et le vrai `numpy`, presents
#: sur la machine de developpement — et le CI est tombe avec douze
#: `ModuleNotFoundError` (mesure du 04/09/2026). Les exiger aurait fait entrer
#: dans ARENA les dependances du SDK que l'installeur garde justement dehors,
#: pour une raison de licence. On double donc ce qui n'appartient pas a ARENA,
#: et on teste ce qui lui appartient.
FAUX_CV2 = '''
IMREAD_COLOR = 1

def imread(chemin, drapeau=None):
    """Rend un objet quelconque si le fichier existe, `None` sinon — c'est le
    seul contrat dont le pont depend."""
    import os
    return object() if os.path.exists(chemin) else None
'''

FAUX_NUMPY = '''
def array(valeurs):
    return list(valeurs)
'''


def _sdk(tmp_path: Path, visages: int = 2) -> Path:
    """Ecrit le double du SDK **et de ses deux bibliotheques**, et rend le
    dossier. Le pont insere son `cwd` en tete de `sys.path` : ce sont donc ces
    fichiers-la qu'il importe, pas ceux de la machine."""
    (tmp_path / "run.py").write_text(
        FAUX_SDK.replace("VISAGES = 2", f"VISAGES = {visages}"), encoding="utf-8")
    (tmp_path / "cv2.py").write_text(FAUX_CV2, encoding="utf-8")
    (tmp_path / "numpy.py").write_text(FAUX_NUMPY, encoding="utf-8")
    return tmp_path


def _image(tmp_path: Path) -> Path:
    """Un fichier qui existe. **Aucune image reelle, et surtout aucun visage** —
    la contrainte du proprietaire est qu'aucune donnee biometrique reelle
    n'entre dans ces tests."""
    chemin = tmp_path / "carre.png"
    chemin.write_bytes(b"pas une vraie image, et c'est voulu")
    return chemin


def lancer(dossier_sdk: Path, *arguments: str):
    """Le pont, exactement comme le connecteur le lance : `cwd` a la racine du
    SDK. Rend (code de sortie, dictionnaire JSON) ou (code, None)."""
    processus = subprocess.run(
        [sys.executable, str(PONT), *arguments],
        cwd=str(dossier_sdk), capture_output=True, text=True, timeout=120)
    for ligne in processus.stdout.splitlines():
        if ligne.startswith(MARQUEUR):
            return processus.returncode, json.loads(ligne[len(MARQUEUR):])
    return processus.returncode, None


class TestLaGardeBiometrique:
    """**La raison d'etre de ce fichier.**"""

    def test_detecter_ne_rend_aucun_gabarit(self, tmp_path):
        """Detecter compte des visages. Rendre les vecteurs « au cas ou »
        ferait voyager de la biometrie a chaque appel — le contraire d'une
        capacite explicitement declenchee."""
        code, sortie = lancer(_sdk(tmp_path), "detecter", "--image", str(_image(tmp_path)))

        assert code == 0
        assert sortie["ok"] is True
        assert sortie["nombre"] == 2
        assert "caracteristiques" not in sortie

    def test_reperes_ne_rend_aucun_gabarit(self, tmp_path):
        code, sortie = lancer(_sdk(tmp_path), "reperes", "--image", str(_image(tmp_path)))

        assert sortie["ok"] is True
        assert "caracteristiques" not in sortie
        assert sortie["reperes"]

    def test_seule_loperation_qui_les_demande_les_recoit(self, tmp_path):
        """Ils ne sont pas supprimes du monde : ils sont rendus **quand on les
        demande**, et seulement la."""
        code, sortie = lancer(_sdk(tmp_path), "caracteristiques",
                              "--image", str(_image(tmp_path)))

        assert sortie["ok"] is True
        assert len(sortie["caracteristiques"]) == 2


class TestComparer:
    def test_deux_visages_donnent_un_score_mesure(self, tmp_path):
        image = _image(tmp_path)
        code, sortie = lancer(_sdk(tmp_path), "comparer",
                              "--image", str(image), "--image2", str(image))

        assert sortie["ok"] is True
        assert isinstance(sortie["score"], float)
        assert "get_similarity" in sortie["echelle"]

    def test_sans_visage_aucun_score_nest_invente(self, tmp_path):
        """**Un `0` se lirait « comparees, tres differentes ».** Il n'y a rien
        eu a comparer : c'est ce que la sortie doit dire."""
        image = _image(tmp_path)
        code, sortie = lancer(_sdk(tmp_path, visages=0), "comparer",
                              "--image", str(image), "--image2", str(image))

        assert code == 1
        assert sortie["ok"] is False
        assert "score" not in sortie
        assert "aucun visage" in sortie["erreur"]


class TestCeQuiLeRendLisible:
    def test_le_marqueur_survit_au_bavardage_du_moteur(self, tmp_path):
        """Le SDK ecrit « priors nums:4420 » sur la MEME sortie. Sans prefixe,
        le connecteur lisait ce melange comme du JSON casse (mesure du
        03/09/2026)."""
        processus = subprocess.run(
            [sys.executable, str(PONT), "sante"],
            cwd=str(_sdk(tmp_path)), capture_output=True, text=True, timeout=120)

        assert "priors nums:4420" in processus.stdout
        lignes = [x for x in processus.stdout.splitlines() if x.startswith(MARQUEUR)]
        assert len(lignes) == 1
        assert json.loads(lignes[0][len(MARQUEUR):])["ok"] is True

    def test_sans_le_sdk_la_sante_est_fausse_et_le_dit(self, tmp_path):
        """Pas de dossier `run.py` : `sante` doit echouer en nommant la cause,
        jamais declarer « operationnel » sur la presence d'un dossier."""
        code, sortie = lancer(tmp_path, "sante")

        assert code == 1
        assert sortie["ok"] is False
        assert "ModuleNotFoundError" in sortie["erreur"]

    def test_une_image_illisible_est_rapportee_pas_inventee(self, tmp_path):
        code, sortie = lancer(_sdk(tmp_path), "detecter",
                              "--image", str(tmp_path / "absente.png"))

        assert code == 1
        assert sortie["ok"] is False
        assert "illisible" in sortie["erreur"]

    @pytest.mark.parametrize("operation", ["sante", "detecter", "reperes",
                                           "caracteristiques", "comparer"])
    def test_chaque_operation_rend_une_ligne_marquee(self, tmp_path, operation):
        """Quoi qu'il arrive, une et une seule ligne exploitable. Le connecteur
        n'a pas d'autre facon de savoir ce qui s'est passe."""
        image = _image(tmp_path)
        code, sortie = lancer(_sdk(tmp_path), operation,
                              "--image", str(image), "--image2", str(image))

        assert sortie is not None
        assert isinstance(sortie["ok"], bool)
