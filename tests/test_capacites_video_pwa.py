"""Le panneau de l'interface propose exactement ce que le serveur accepte.

**Mesuré le 03/09/2026.** Le propriétaire demande comment lancer Xaar Kaname
depuis son téléphone. La chaîne était complète — modale → `POST
/api/video/projet` → agent vidéo → connecteur → confirmation → moteur — mais
`xaar_kaname` **manquait dans la liste de l'interface**. La capacité existait
partout sauf sur l'écran d'où on la déclenche.

Le commentaire au-dessus de la liste TypeScript prévenait déjà :

    must mirror `core/production/plan_video.py:CAPACITES_VIDEO` exactly.
    A UI list that drifted from the server's closed list would let the
    user "select" something the backend refuses anyway, silently.

**Un commentaire n'empêche pas une dérive, il la raconte après coup.** Ce
fichier la mesure. La dérive s'est produite dans l'autre sens que celui
redouté : pas une capacité refusée par le serveur, une capacité que rien ne
permettait de choisir.
"""
import re
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
PLAN = RACINE / "core" / "production" / "plan_video.py"
STORE = RACINE / "apps" / "pwa" / "src" / "lib" / "store" / "videoProjectStore.ts"
MODALE = RACINE / "apps" / "pwa" / "src" / "components" / "chat" / "VideoProjectModal.tsx"


def _capacites_serveur() -> list[str]:
    source = PLAN.read_text(encoding="utf-8")
    bloc = source.split("CAPACITES_VIDEO: Tuple[str, ...] = (")[1].split(")")[0]
    return re.findall(r'"([a-z_0-9]+)"', bloc)


def _capacites_interface() -> list[str]:
    source = STORE.read_text(encoding="utf-8")
    bloc = source.split("export const CAPACITES_VIDEO = [")[1].split("]")[0]
    return re.findall(r"'([a-z_0-9]+)'", bloc)


def test_les_deux_listes_sont_identiques():
    """Même contenu ET même ordre : l'agent désigne les capacités par leur nom,
    mais un ordre qui diverge trahit une liste recopiée sans être relue."""
    assert _capacites_interface() == _capacites_serveur()


def test_xaar_kaname_est_proposable_depuis_linterface():
    """Le cas qui a motivé ce fichier : la capacité existait partout sauf sur
    l'écran d'où on la déclenche."""
    assert "xaar_kaname" in _capacites_interface()


def test_chaque_capacite_a_son_icone_et_son_libelle():
    """Une capacité sans icône fait planter la modale au rendu ; une capacité
    sans libellé s'affiche sous son nom technique."""
    modale = MODALE.read_text(encoding="utf-8")
    icones = modale.split("const ICONE_CAPACITE")[1].split("};")[0]
    libelles = modale.split("const labels: Record<CapaciteVideo")[1].split("};")[0]

    for capacite in _capacites_interface():
        assert f"{capacite}:" in icones, f"{capacite} n'a pas d'icone"
        assert f"{capacite}:" in libelles, f"{capacite} n'a pas de libelle"
