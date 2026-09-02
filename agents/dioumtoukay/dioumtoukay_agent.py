"""Dioumtoukay : celui qui entre vraiment dans les fichiers et le terminal.

Nommé par le propriétaire le 02/09/2026 : « il doit être comme claude code
entrer dans mon terminal mon github et travailler sur le projet ». **DEC-0038**
enregistre qu'il a levé DEC-0014 en connaissance de cause — donc ici on
n'analyse pas, on **fait**.

C'est ce qui le sépare de `RepoEngineerAgent`, qui lit et propose sans jamais
modifier un fichier. Les deux existent, et le second n'est pas remplacé : lire
avant d'agir reste utile.

**La boucle.** Le modèle ne rend pas une réponse, il rend **une action à la
fois**. L'action est exécutée par `tools/atelier`, et son résultat réel —
sortie, erreur, code de sortie — revient dans l'invite suivante. Il travaille
donc sur ce qui s'est vraiment passé, jamais sur ce qu'il imaginait.

**Quatre choses que cet agent ne fait pas, et qui ne sont pas des garde-fous :**

1. **Il n'invente aucun résultat.** Une commande qui n'a pas tourné rend son
   erreur. Sans modèle joignable, il répond `NOT_CONFIGURED` avec ce qui manque
   — jamais un compte-rendu de travail qui n'a pas eu lieu.
2. **Il ne déclare pas la réussite à la place des commandes.** Ce qui est
   rapporté au propriétaire est la liste de ce qui a tourné, avec les codes de
   sortie tels quels. Un `pytest` rouge se lit rouge.
3. **Il s'arrête.** `TOURS_MAX` borne la boucle : un modèle qui tourne en rond
   consomme la machine sans rien produire, et une boucle sans fin est la
   première façon dont un agent autonome devient nuisible.
4. **Il laisse une trace.** Chaque action passe par `JournalDesActions` via
   l'atelier. Ce n'est pas une autorisation à demander, c'est un compte-rendu à
   lire.
"""
from __future__ import annotations

import logging
import re
import shlex
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.agent.base_agent import BaseAgent
from core.memory.memory_manager import MemoryManager
from core.models.base import ModelProvider
from tools.atelier.atelier import Atelier, Resultat

logger = logging.getLogger("usman.agent.dioumtoukay")

#: Combien d'actions au maximum pour une demande. Un modèle qui tourne en rond
#: consomme la machine sans rien produire ; au-delà, on rend ce qui a été fait
#: et on le dit, plutôt que de continuer indéfiniment.
TOURS_MAX = 12

#: Les actions qu'il sait faire. Toute autre étiquette est refusée et lui est
#: renvoyée telle quelle — corriger sa faute à sa place lui apprendrait à
#: écrire n'importe quoi.
ACTIONS = ("lire", "ecrire", "lister", "deplacer", "executer", "terminer")

_ETIQUETTE = re.compile(r"^\s*ACTION\s*:\s*(\w+)", re.IGNORECASE | re.MULTILINE)
_CHAMP = re.compile(r"^\s*(CHEMIN|SOURCE|DESTINATION|COMMANDE|DOSSIER)\s*:\s*(.+)$",
                    re.IGNORECASE | re.MULTILINE)
_CONTENU = re.compile(r"^\s*CONTENU\s*:\s*\n(.*?)(?:\n\s*FIN\s*$|\Z)",
                      re.IGNORECASE | re.MULTILINE | re.DOTALL)

CONSIGNE = """Tu es Dioumtoukay. Tu travailles sur la machine du proprietaire :
ses fichiers, son terminal, ses depots git. Tu n'expliques pas ce que tu ferais,
tu le fais.

Tu reponds par UNE SEULE action, dans ce format exact, et rien d'autre :

ACTION: lister
CHEMIN: .

ACTION: lire
CHEMIN: apps/backend/config.py

ACTION: ecrire
CHEMIN: apps/backend/config.py
CONTENU:
le contenu complet du fichier
FIN

ACTION: deplacer
SOURCE: vrac/photo.jpg
DESTINATION: photos/2026/photo.jpg

ACTION: executer
COMMANDE: python -m pytest -q
DOSSIER: .

ACTION: terminer
CONTENU:
ce que tu as fait, en francais simple, pour le proprietaire
FIN

Regles :
- `ecrire` remplace TOUT le fichier : lis-le avant de le reecrire.
- Le resultat reel de chaque action t'est rendu ; travaille sur ce resultat,
  jamais sur ce que tu supposes.
- Une commande qui echoue se corrige, elle ne se contourne pas.
- Quand le travail est fait, ou quand tu es bloque, reponds `ACTION: terminer`
  et dis la verite sur ce qui a marche et ce qui n'a pas marche."""


@dataclass
class Action:
    """Une action demandée par le modèle, telle qu'elle a été lue."""

    nom: str
    champs: Dict[str, str] = field(default_factory=dict)
    contenu: str = ""


def analyser_action(texte: str) -> Optional[Action]:
    """Lit l'action dans la réponse du modèle. `None` si elle est illisible.

    Déterministe : aucun second appel au modèle pour comprendre le premier. Une
    réponse mal formée est une réponse mal formée, et le lui dire vaut mieux que
    deviner ce qu'il voulait.
    """
    etiquette = _ETIQUETTE.search(texte or "")
    if not etiquette:
        return None
    nom = etiquette.group(1).lower()
    if nom not in ACTIONS:
        return None

    champs = {cle.upper(): valeur.strip()
              for cle, valeur in _CHAMP.findall(texte)}
    bloc = _CONTENU.search(texte)
    return Action(nom=nom, champs=champs, contenu=bloc.group(1) if bloc else "")


class DioumtoukayAgent(BaseAgent):
    """Il entre dans les fichiers, le terminal et le dépôt, et il agit."""

    def __init__(self, provider: ModelProvider, memory: Optional[MemoryManager] = None,
                 atelier: Optional[Atelier] = None):
        super().__init__(
            name="DioumtoukayAgent",
            description="Agent qui travaille reellement sur les fichiers, "
                        "le terminal et les depots git du proprietaire.",
            provider=provider,
            memory=memory,
        )
        self.atelier = atelier or Atelier()

    # --- Exécution d'une action ---------------------------------------------------

    def _executer_action(self, action: Action) -> Resultat:
        """Fait ce que l'action demande, via l'atelier."""
        champs = action.champs
        if action.nom == "lire":
            return self.atelier.lire(champs.get("CHEMIN", ""))
        if action.nom == "ecrire":
            return self.atelier.ecrire(champs.get("CHEMIN", ""), action.contenu)
        if action.nom == "lister":
            return self.atelier.lister(champs.get("CHEMIN", "."))
        if action.nom == "deplacer":
            return self.atelier.deplacer(champs.get("SOURCE", ""),
                                         champs.get("DESTINATION", ""))
        # `executer` : la ligne devient une LISTE d'arguments. Ce n'est pas une
        # restriction de ce qu'il peut lancer — c'est ce qui empeche un nom de
        # fichier contenant une espace ou un `;` de devenir deux commandes.
        ligne = champs.get("COMMANDE", "")
        try:
            morceaux = shlex.split(ligne)
        except ValueError as erreur:
            return Resultat(False, f"Commande illisible ({erreur}) : {ligne}")
        return self.atelier.executer(morceaux, dossier=champs.get("DOSSIER") or None)

    # --- La boucle -------------------------------------------------------------------

    async def run(self, user_input: str, context: Optional[Dict[str, Any]] = None
                  ) -> Dict[str, Any]:
        """Travaille jusqu'à ce que ce soit fait, puis rend ce qui s'est passé."""
        if not await self.provider.is_available():
            # Sans modele, il n'y a pas de travail a rapporter. Le dire est la
            # seule reponse honnete : un compte-rendu vide se lirait comme un
            # travail termine.
            return {
                "status": "NOT_CONFIGURED",
                "agent": self.name,
                "actions": [],
                "response": (
                    "Dioumtoukay ne peut pas travailler : aucun moteur n'est "
                    "joignable. Il faut lancer Ollama sur ton PC (`ollama serve`) "
                    "ou configurer un service distant."
                ),
            }

        journal_du_travail: List[str] = []
        rendu: List[Dict[str, Any]] = []
        conclusion = ""
        arrete_par_lui_meme = False

        for tour in range(1, TOURS_MAX + 1):
            invite = self._invite(user_input, journal_du_travail)
            try:
                reponse = await self.provider.generate(prompt=invite, system_prompt=CONSIGNE)
            except Exception as erreur:  # noqa: BLE001 — l'echec se nomme
                logger.warning("Dioumtoukay : le moteur n'a pas repondu : %s", erreur)
                conclusion = f"Le moteur n'a pas repondu au tour {tour} : {erreur}"
                break

            action = analyser_action(reponse)
            if action is None:
                journal_du_travail.append(
                    "Reponse illisible : il faut UNE action au format demande.")
                continue

            if action.nom == "terminer":
                conclusion = action.contenu.strip() or reponse.strip()
                arrete_par_lui_meme = True
                break

            resultat = self._executer_action(action)
            rendu.append({"action": action.nom, "champs": action.champs,
                          **resultat.to_dict()})
            journal_du_travail.append(self._compte_rendu(action, resultat))

        if not arrete_par_lui_meme and not conclusion:
            # La borne est atteinte. Le dire : un rapport qui s'arrete sans
            # raison se lit comme un travail fini.
            conclusion = (
                f"Arrete apres {TOURS_MAX} actions sans avoir conclu. "
                "Ce qui a ete fait est ci-dessous ; la suite reste a faire."
            )

        return {
            "status": "success" if arrete_par_lui_meme else "partial",
            "agent": self.name,
            "actions": rendu,
            "response": self._rapport(conclusion, rendu),
        }

    # --- Ce qu'il voit, et ce qu'il rend ---------------------------------------------

    def _invite(self, demande: str, journal_du_travail: List[str]) -> str:
        """La demande, plus ce qui s'est réellement passé jusqu'ici."""
        blocs = [f"Racine du travail : {self.atelier.racine}",
                 f"Demande du proprietaire : {demande}"]
        if journal_du_travail:
            blocs.append("Ce qui s'est passe jusqu'ici :\n" + "\n\n".join(journal_du_travail))
        blocs.append("Action suivante :")
        return "\n\n".join(blocs)

    @staticmethod
    def _compte_rendu(action: Action, resultat: Resultat) -> str:
        """Ce que l'action a vraiment donné, tel quel — jamais résumé."""
        lignes = [f"> ACTION {action.nom} : {resultat.message}"]
        if resultat.sortie:
            lignes.append(f"SORTIE:\n{resultat.sortie}")
        if resultat.erreur:
            lignes.append(f"ERREUR:\n{resultat.erreur}")
        return "\n".join(lignes)

    @staticmethod
    def _rapport(conclusion: str, rendu: List[Dict[str, Any]]) -> str:
        """Le compte-rendu pour le propriétaire : ce qui a tourné, et son sort.

        Les echecs ne sont pas fondus dans la conclusion : ils sont comptes a
        part, parce que c'est la seule ligne qui lui dit s'il doit aller voir.
        """
        echecs = [a for a in rendu if not a["ok"]]
        entete = f"**Dioumtoukay — {len(rendu)} action(s)"
        entete += f", {len(echecs)} en echec**" if echecs else ", aucune en echec**"

        detail = "\n".join(
            f"- {'OK ' if a['ok'] else 'ECHEC'} `{a['action']}` — {a['message']}"
            for a in rendu) or "- aucune action executee"

        return f"{entete}\n\n{detail}\n\n{conclusion}".strip()
