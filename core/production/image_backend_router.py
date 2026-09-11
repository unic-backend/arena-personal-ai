"""Le choix DIRECT vs COMFYUI pour la capacite image-generation canonique.

Mission ARENA x COMFYUI (DEC-0087, mission §4). ARENA a maintenant deux
moteurs d'execution possibles pour la meme capacite (« generer une image ») :
`core/connectors/hidream.py` (direct, un seul modele) et
`core/connectors/comfyui.py` (un backend generique, plusieurs workflows).
La mission l'interdit explicitement : **jamais un deuxieme agent image**,
un seul point d'entree (`VideoProductionAgent.generer_image`,
DEC-0085), qui choisit son moteur ici.

**La regle est volontairement simple, et le comportement par defaut ne
change pas** (mission §31 : ne pas casser le routage existant). Un appelant
qui ne precise rien obtient exactement le comportement de DEC-0085 :
`hidream`. Le nouveau comportement est strictement ADDITIF :

1. Un `backend` explicite est toujours respecte tel quel — jamais
   reinterprete.
2. Sans `backend` explicite, `hidream` reste le premier choix (compatibilite
   DEC-0085).
3. **Seul un echec `NOT_CONFIGURED` du premier choix** declenche un essai de
   l'autre moteur, et seulement s'il est reellement declare dans le
   registre (mission §39 : repli si le moteur choisi est indisponible,
   jamais si la demande a echoue pour une autre raison — un prompt vide
   reste un prompt vide sur les deux moteurs).
"""
from __future__ import annotations

from typing import Optional

#: Constantes nommees plutot que des chaines libres dans le tuple : c'est ce
#: que `tests/test_connecteurs_dormants.py` (DEC-0068) exige de chaque
#: connecteur enregistre — un nom cite dans du code de production reel, pas
#: seulement dans son propre module/registre. `comfyui` n'apparaissait sinon
#: nulle part comme argument d'appel ou affectation nommee : atteignable en
#: pratique (le routeur le passe reellement a `registre.executer`), mais
#: invisible a l'analyse statique. Regression trouvee par la suite complete,
#: corrigee ici — jamais ajoute a `DORMANTS_CONNUS` : ce serait faux, le
#: connecteur EST joignable (test de redemarrage reel, DEC-0087).
BACKEND_HIDREAM = "hidream"
BACKEND_COMFYUI = "comfyui"

#: Ordre par defaut — hidream reste premier pour ne rien changer au
#: comportement mesure par DEC-0085 tant qu'aucun backend n'est demande.
BACKENDS_CONNUS = (BACKEND_HIDREAM, BACKEND_COMFYUI)
BACKEND_PAR_DEFAUT = BACKEND_HIDREAM


def backend_choisi(backend_demande: Optional[str]) -> str:
    """Le backend a essayer en premier. Un nom explicite gagne toujours,
    meme s'il n'est pas dans `BACKENDS_CONNUS` — le connecteur (ou son
    absence dans le registre) est l'autorite finale, pas cette fonction."""
    if backend_demande:
        return backend_demande
    return BACKEND_PAR_DEFAUT


def backend_de_secours(backend_essaye: str) -> Optional[str]:
    """L'autre moteur connu, ou `None` s'il n'y en a pas (mission §39). Un
    backend inconnu n'a pas de secours defini ici — decider d'un repli pour
    un nom qu'on ne reconnait pas serait deviner."""
    if backend_essaye not in BACKENDS_CONNUS:
        return None
    autres = [nom for nom in BACKENDS_CONNUS if nom != backend_essaye]
    return autres[0] if autres else None
