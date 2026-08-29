"""Des crochets autour de l'execution d'une capacite — un point d'extension
que rien d'autre n'avait, sans toucher a l'ordre verrouille qui protege le
projet.

**Provenance** : l'idee vient de l'audit de `deepseek-ai/deepseek-harness`
(MIT), demande le 29/08/2026. Son moteur (Cordis) fait tourner CHAQUE appel
d'outil a travers trois « waterfalls » — `tools/pre-execute`, `tools/execute`,
`tools/post-execute` — pour que des politiques transverses (delai, alerte de
repetition, dans son propre depot : `packages/guard/`) s'ajoutent SANS
reecrire le coeur. Aucune ligne de son TypeScript n'est reprise : Cordis est
un bus d'evenements pour un runtime Node avec un contexte partage typé ; ce
module est deux listes de fonctions Python, ecrites pour le meme besoin.

**Pourquoi ici, et pas ailleurs** : `core/connectors/base.py` est verrouille
(`PROJECT_MEMORY/LOCKED_ZONES.md`) — « l'ordre controle -> confirmation ->
sante -> quota » ne bouge pas. Ce module ne le reordonne pas : il ajoute DEUX
points, tous deux APRES que ces quatre controles ont deja tranche. Un crochet
ne peut ni autoriser ce qui a ete refuse, ni sauter la confirmation, ni
retarder la sonde de sante — il ne voit l'appel qu'une fois que ces quatre
verrous ont deja dit oui.

**Deux points, jamais plus que ce qui sert un besoin reel :**

1. `avant_execution` — une chaine, appelee dans l'ordre d'inscription, juste
   avant que `_executer()` ne tourne. Le premier crochet qui rend une raison
   arrete la chaine : c'est un veto **operationnel** (le disjoncteur en est
   l'exemple), jamais une permission — la difference est ecrite dans le
   `ResultatAction` qu'il produit : `ECHEC`, jamais `DENIED`.

2. `apres_execution` — un observateur, jamais un veto : il voit le resultat
   final, il ne le modifie pas. Un crochet qui le reecrirait romprait la
   garantie « un `SUCCESS` ne se construit pas sans preuve »
   (`core/actions/resultat.py`) — l'observateur regarde une preuve deja
   verifiee, il n'en fabrique pas une autre.

**Une regle porte les deux** : un crochet qui leve ne casse jamais l'appel
qu'il observe. Une politique transverse cassee ne doit pas rendre un
connecteur inutilisable — elle se rapporte dans les journaux, et l'appel
continue comme si ce crochet n'existait pas.
"""
import logging
from typing import Any, Callable, Dict, List, Optional

from core.actions.resultat import ResultatAction

logger = logging.getLogger("usman.execution.hooks")

#: `(connecteur, capacite, parametres) -> raison de refus, ou None pour laisser passer.`
AvantExecution = Callable[[str, str, Dict[str, Any]], Optional[str]]

#: `(connecteur, capacite, resultat) -> None.` N'a jamais le droit de retour.
ApresExecution = Callable[[str, str, ResultatAction], None]


class RegistreDeCrochets:
    """Deux chaines de crochets, partagees par tous les connecteurs qui la
    reçoivent — comme `journal` ou `file_attente`, un seul objet construit une
    fois dans `runtime.py` et distribue a chacun."""

    def __init__(self) -> None:
        self._avant: List[AvantExecution] = []
        self._apres: List[ApresExecution] = []

    def avant(self, crochet: AvantExecution) -> None:
        """Inscrit un crochet `avant_execution`. L'ordre d'inscription est l'ordre d'appel."""
        self._avant.append(crochet)

    def apres(self, crochet: ApresExecution) -> None:
        """Inscrit un crochet `apres_execution`."""
        self._apres.append(crochet)

    def executer_avant(self, connecteur: str, capacite: str,
                       parametres: Dict[str, Any]) -> Optional[str]:
        """Rend la raison du premier veto, ou `None` si tous laissent passer."""
        for crochet in self._avant:
            try:
                raison = crochet(connecteur, capacite, parametres)
            except Exception as erreur:  # noqa: BLE001 — un crochet casse n'arrete pas l'appel
                logger.error("Crochet avant_execution (%s) en erreur sur %s.%s : %s",
                            getattr(crochet, "__name__", crochet), connecteur, capacite, erreur)
                continue
            if raison:
                return raison
        return None

    def executer_apres(self, connecteur: str, capacite: str,
                       resultat: ResultatAction) -> None:
        """Notifie chaque observateur. Une exception y reste — jamais propagee."""
        for crochet in self._apres:
            try:
                crochet(connecteur, capacite, resultat)
            except Exception as erreur:  # noqa: BLE001 — idem
                logger.error("Crochet apres_execution (%s) en erreur sur %s.%s : %s",
                            getattr(crochet, "__name__", crochet), connecteur, capacite, erreur)
