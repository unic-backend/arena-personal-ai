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
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional

from core.agent.base_agent import BaseAgent
from core.execution.reprise import JournalDeReprise
from core.memory.conversation import retenir_l_echange
from core.memory.memory_manager import MemoryManager
from core.memory.personnelle import MemoirePersonnelle
from core.models.base import ModelProvider
from core.specialistes.selection import bloc_de_methode, choisir
from tools.atelier.atelier import Atelier, Resultat

logger = logging.getLogger("usman.agent.dioumtoukay")

#: Combien d'actions au maximum pour une demande. Un modèle qui tourne en rond
#: consomme la machine sans rien produire ; au-delà, on rend ce qui a été fait
#: et on le dit, plutôt que de continuer indéfiniment.
TOURS_MAX = 12

#: Au-delà, le travail s'arrête même si `TOURS_MAX` n'est pas atteint. Une
#: action peut coûter jusqu'à `DELAI_PAR_DEFAUT` (`Atelier`, 120s) : sans
#: plafond de temps, douze tours sur des commandes lentes autorisent une
#: session de plusieurs dizaines de minutes. Concept vérifié dans le code
#: source de mini-SWE-agent (`AgentConfig.wall_time_limit_seconds`) — 0
#: désactiverait la limite, comme chez eux, mais rien ici n'a demandé à la
#: désactiver.
DUREE_MAX_SECONDES = 20 * 60

#: Au-delà, une réponse illisible D'AFFILÉE n'est plus une réponse à renvoyer
#: une fois de plus : c'est un moteur qui ne sait pas produire le format
#: demandé, et continuer jusqu'à `TOURS_MAX` ne ferait que consommer le budget
#: sans qu'aucune action ne parte jamais. Concept vérifié dans le code source
#: de mini-SWE-agent (`AgentConfig.max_consecutive_format_errors`, défaut 3,
#: `DefaultAgent.run` : le compteur revient à zéro dès qu'un tour est propre).
ILLISIBLES_CONSECUTIVES_MAX = 3

#: Les actions qu'il sait faire. Toute autre étiquette est refusée et lui est
#: renvoyée telle quelle — corriger sa faute à sa place lui apprendrait à
#: écrire n'importe quoi.
ACTIONS = ("lire", "chercher", "lister", "ecrire", "remplacer", "deplacer",
           "executer", "terminer")

#: Les actions qui modifient quelque chose. Elles sont comptées à part dans le
#: rapport : « j'ai lu quatre fichiers » et « j'ai modifié quatre fichiers » ne
#: se lisent pas pareil, et c'est la seconde phrase qui demande une vérification.
ACTIONS_QUI_MODIFIENT = frozenset({"ecrire", "remplacer", "deplacer"})

_ETIQUETTE = re.compile(r"^\s*ACTION\s*:\s*(\w+)", re.IGNORECASE | re.MULTILINE)
_CHAMP = re.compile(
    r"^\s*(CHEMIN|SOURCE|DESTINATION|COMMANDE|DOSSIER|TEXTE)\s*:\s*(.+)$",
    re.IGNORECASE | re.MULTILINE)

#: Les blocs multilignes, chacun fermé par une ligne `FIN`. `remplacer` en
#: demande deux — l'ancien passage et le nouveau — ce qu'un bloc unique ne
#: pouvait pas porter.
BLOCS = ("CONTENU", "ANCIEN", "NOUVEAU")

CONSIGNE = """Tu es Dioumtoukay. Tu travailles sur la machine du proprietaire :
ses fichiers, son terminal, ses depots git. Tu n'expliques pas ce que tu ferais,
tu le fais.

Tu reponds par UNE SEULE action, dans ce format exact, et rien d'autre :

ACTION: lister
CHEMIN: .

ACTION: chercher
TEXTE: def calculer_total
CHEMIN: .

ACTION: lire
CHEMIN: apps/backend/config.py

ACTION: remplacer
CHEMIN: apps/backend/config.py
ANCIEN:
le passage exact, copie du fichier que tu viens de lire
FIN
NOUVEAU:
ce qui prend sa place
FIN

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

COMMENT TRAVAILLER

1. TROUVER avant de corriger. `chercher` te dit dans quel fichier est le
   probleme ; deviner le fichier fait perdre des tours.
2. LIRE avant de modifier. Tu ne modifies jamais un fichier que tu n'as pas lu
   dans cette conversation.
3. `remplacer` est la BONNE facon de corriger : tu cites le passage exact et il
   change, le reste du fichier ne bouge pas. `ecrire` remplace TOUT le fichier
   et sert a en creer un nouveau — l'utiliser pour corriger une ligne t'oblige
   a reecrire tout le reste de memoire, et c'est ainsi qu'on casse un fichier
   qui marchait.
4. VERIFIER. Apres avoir touche du code, lance ce qui le prouve : les tests, le
   linter, ou la commande qui echouait. Un travail non verifie n'est pas fini,
   et tu ne dis jamais que ca marche sans l'avoir lance.
5. Une erreur se comprend avant de se corriger. Lis le message en entier,
   trouve la cause, corrige la cause. Ne contourne pas, ne desactive pas un
   test, n'attrape pas une exception pour la faire taire.

REGLES

- Le resultat reel de chaque action t'est rendu ; travaille sur ce resultat,
  jamais sur ce que tu supposes.
- Pour du code venu de GitHub : clone, installe, lance. Tout est permis, rien
  n'est bloque — mais lis avant de lancer, et dis-lui ce que tu as vu.
- Quand tu changes le code d'un depot, travaille sur une branche a toi.
- Quand le travail est fait, ou quand tu es bloque, reponds `ACTION: terminer`
  et dis la verite sur ce qui a marche et ce qui n'a pas marche. Un travail a
  moitie fait se dit ; il ne se presente pas comme fini."""


@dataclass
class Action:
    """Une action demandée par le modèle, telle qu'elle a été lue."""

    nom: str
    champs: Dict[str, str] = field(default_factory=dict)
    blocs: Dict[str, str] = field(default_factory=dict)

    @property
    def contenu(self) -> str:
        """Le bloc `CONTENU:`, celui qu'écrivent `ecrire` et `terminer`."""
        return self.blocs.get("CONTENU", "")


def _lire_bloc(nom: str, texte: str) -> Optional[str]:
    """Le contenu d'un bloc `NOM:` … `FIN`, tel qu'il a été écrit.

    Rien n'est nettoyé au-delà du saut de ligne d'ouverture : l'indentation
    d'un bloc de code EST le code, et la retirer casserait un fichier Python.
    """
    motif = re.compile(rf"^\s*{nom}\s*:[ \t]*\n(.*?)(?:\n[ \t]*FIN[ \t]*$|\Z)",
                       re.IGNORECASE | re.MULTILINE | re.DOTALL)
    trouve = motif.search(texte)
    return trouve.group(1) if trouve else None


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
    blocs = {}
    for bloc in BLOCS:
        lu = _lire_bloc(bloc, texte)
        if lu is not None:
            blocs[bloc] = lu
    return Action(nom=nom, champs=champs, blocs=blocs)


class DioumtoukayAgent(BaseAgent):
    """Il entre dans les fichiers, le terminal et le dépôt, et il agit."""

    def __init__(self, provider: ModelProvider, memory: Optional[MemoryManager] = None,
                 atelier: Optional[Atelier] = None,
                 memoire_longue: Optional[MemoirePersonnelle] = None,
                 reprises: Optional[JournalDeReprise] = None):
        super().__init__(
            name="DioumtoukayAgent",
            description="Agent qui travaille reellement sur les fichiers, "
                        "le terminal et les depots git du proprietaire.",
            provider=provider,
            memory=memory,
        )
        self.atelier = atelier or Atelier()
        # `memory` est le fil de la conversation ; `memoire_longue` est ce dont
        # on se souvient d'une semaine sur l'autre. Ce sont deux objets
        # differents dans ce projet, et les confondre reviendrait a n'ecrire
        # nulle part.
        self.memoire_longue = memoire_longue
        # Le journal DURABLE de ce qu'il a deja fait (DEC-0072). La memoire
        # longue garde un RESUME de chaque travail ; celui-ci garde les ETAPES,
        # pour qu'une tache arretee a la 12e action reprenne a la 13e au lieu
        # de tout refaire. Les deux ne font pas double emploi : l'une sert a se
        # souvenir, l'autre a continuer.
        self.reprises = reprises if reprises is not None else JournalDeReprise()

    # --- Exécution d'une action ---------------------------------------------------

    def _executer_action(self, action: Action) -> Resultat:
        """Fait ce que l'action demande, via l'atelier."""
        champs = action.champs
        if action.nom == "lire":
            return self.atelier.lire(champs.get("CHEMIN", ""))
        if action.nom == "ecrire":
            return self.atelier.ecrire(champs.get("CHEMIN", ""), action.contenu)
        if action.nom == "remplacer":
            # Un remplacement sans `ANCIEN:` reecrirait au hasard. L'absence du
            # bloc est dite ; elle n'est pas comblee par une supposition.
            if "ANCIEN" not in action.blocs:
                return Resultat(False, "Il manque le bloc ANCIEN: … FIN, "
                                       "le passage exact a remplacer.")
            return self.atelier.remplacer(champs.get("CHEMIN", ""),
                                          action.blocs["ANCIEN"],
                                          action.blocs.get("NOUVEAU", ""))
        if action.nom == "chercher":
            return self.atelier.chercher(champs.get("TEXTE", ""),
                                         champs.get("CHEMIN", "."))
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

        # Les reperes sont pris UNE fois : ils decrivent le point de depart, et
        # les refaire a chaque tour couterait trois commandes reelles par tour
        # pour redire ce que le journal du travail raconte deja mieux.
        reperes = self._reperes()

        # La methode d'un specialiste (`debugging`/`tests`/`architecture`...,
        # `core/specialistes/catalogue.py`) n'atteignait jamais Dioumtoukay :
        # ATELIER etait meme absent de l'audit qui verifie que chaque
        # intention utile a une methode ou une raison ecrite. Calculee une
        # fois, comme les reperes : la demande ne change pas en cours de
        # travail.
        methode = bloc_de_methode(choisir(user_input, "ATELIER"))
        consigne = f"{CONSIGNE}\n\n{methode}" if methode else CONSIGNE

        # Une tache interrompue reprend ici, avec ses etapes deja faites en
        # guise de journal de depart : le modele voit ce qui a tourne et
        # enchaine, au lieu de relire et rechercher ce qu'il avait deja lu.
        tache = self.reprises.ouvrir(user_input)
        journal_du_travail: List[str] = list(tache.deja_fait())
        reprise = bool(journal_du_travail)
        if reprise:
            logger.info("Reprise de la tache %s : %d etapes deja faites.",
                        tache.identifiant, len(journal_du_travail))
        rendu: List[Dict[str, Any]] = []
        conclusion = ""
        arrete_par_lui_meme = False
        debut = time.monotonic()
        illisibles_consecutives = 0

        for tour in range(1, TOURS_MAX + 1):
            ecoule = time.monotonic() - debut
            if ecoule >= DUREE_MAX_SECONDES:
                conclusion = (
                    f"Arrete apres {int(ecoule // 60)} minutes sans avoir conclu. "
                    "Ce qui a ete fait est ci-dessous ; la suite reste a faire.")
                break

            invite = self._invite(reperes, user_input, journal_du_travail)
            try:
                reponse = await self.provider.generate(prompt=invite, system_prompt=consigne)
            except Exception as erreur:  # noqa: BLE001 — l'echec se nomme
                logger.warning("Dioumtoukay : le moteur n'a pas repondu : %s", erreur)
                conclusion = f"Le moteur n'a pas repondu au tour {tour} : {erreur}"
                break

            action = analyser_action(reponse)
            if action is None:
                illisibles_consecutives += 1
                journal_du_travail.append(
                    "Reponse illisible : il faut UNE action au format demande.")
                if illisibles_consecutives >= ILLISIBLES_CONSECUTIVES_MAX:
                    conclusion = (
                        f"Arrete apres {illisibles_consecutives} reponses illisibles "
                        "d'affilee : le moteur ne produit pas le format demande.")
                    break
                continue
            illisibles_consecutives = 0

            if action.nom == "terminer":
                conclusion = action.contenu.strip() or reponse.strip()
                arrete_par_lui_meme = True
                break

            debut_action = time.monotonic()
            resultat = self._executer_action(action)
            duree_ms = int((time.monotonic() - debut_action) * 1000)
            rendu.append({"action": action.nom, "champs": action.champs,
                          **resultat.to_dict()})
            journal_du_travail.append(self._compte_rendu(action, resultat))
            # Ecrit MAINTENANT, pas a la fin : une tache tuee au milieu doit
            # laisser exactement ce qu'elle avait fait.
            self.reprises.noter(
                tache, action.nom,
                cible=str(action.champs.get("CHEMIN") or action.champs.get("MOTIF") or ""),
                ok=resultat.ok, resume=self._compte_rendu(action, resultat),
                duree_ms=duree_ms)

        if not arrete_par_lui_meme and not conclusion:
            # La borne est atteinte. Le dire : un rapport qui s'arrete sans
            # raison se lit comme un travail fini.
            conclusion = (
                f"Arrete apres {TOURS_MAX} actions sans avoir conclu. "
                "Ce qui a ete fait est ci-dessous ; la suite reste a faire."
            )

        self._retenir(user_input, conclusion, rendu)

        # Terminee, ou interrompue donc REPRENABLE. C'est cette distinction qui
        # fait la difference entre « la suite reste a faire » (une phrase) et
        # « la suite reprendra ici » (un etat).
        if arrete_par_lui_meme:
            self.reprises.terminer(tache, conclusion)
        else:
            self.reprises.interrompre(tache, conclusion)

        return {
            "status": "success" if arrete_par_lui_meme else "partial",
            "agent": self.name,
            "actions": rendu,
            "fichiers_modifies": self.fichiers_touches(rendu),
            "response": self._rapport(conclusion, rendu),
            "tache": tache.journal(),
            "reprise": reprise,
        }

    # --- Ce qu'il voit, et ce qu'il rend ---------------------------------------------

    def _reperes(self) -> str:
        """Où il est, et ce qu'il y a autour. Mesuré, jamais supposé.

        Sans ça, le premier tour partait à l'aveugle : le modèle dépensait deux
        ou trois actions à découvrir un dossier qu'une seule mesure lui donne.
        Sur douze tours, deux tours perdus au départ comptent.

        Rien n'est inventé ici : un dépôt git absent ne produit aucune ligne,
        et l'absence se lit comme une absence.
        """
        lignes = [f"Racine du travail : {self.atelier.racine}"]

        branche = self.atelier.executer(["git", "rev-parse", "--abbrev-ref", "HEAD"])
        if branche.ok:
            lignes.append(f"Depot git, sur la branche : {branche.sortie.strip()}")
            etat = self.atelier.executer(["git", "status", "--short"])
            if etat.ok:
                modifies = etat.sortie.strip()
                lignes.append("Fichiers modifies non commites :\n" + modifies
                              if modifies else "Aucun fichier modifie.")

        autour = self.atelier.lister(".")
        if autour.ok:
            lignes.append("Ce que contient la racine :\n" + autour.sortie)
        return "\n".join(lignes)

    @staticmethod
    def _invite(reperes: str, demande: str, journal_du_travail: List[str]) -> str:
        """La demande, plus ce qui s'est réellement passé jusqu'ici."""
        blocs = [reperes, f"Demande du proprietaire : {demande}"]
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
    def fichiers_touches(rendu: List[Dict[str, Any]]) -> List[str]:
        """Les fichiers réellement modifiés — ceux qui ont changé sur le disque.

        Une action tentée puis échouée ne compte pas : dire « fichier modifié »
        d'un fichier intact serait la pire ligne du rapport.
        """
        touches = []
        for acte in rendu:
            if not acte["ok"] or acte["action"] not in ACTIONS_QUI_MODIFIENT:
                continue
            champs = acte.get("champs") or {}
            ou = champs.get("CHEMIN") or champs.get("DESTINATION")
            if ou and ou not in touches:
                touches.append(ou)
        return touches

    @classmethod
    def _rapport(cls, conclusion: str, rendu: List[Dict[str, Any]]) -> str:
        """Le compte-rendu pour le propriétaire : ce qui a tourné, et son sort.

        Les echecs ne sont pas fondus dans la conclusion : ils sont comptes a
        part, parce que c'est la seule ligne qui lui dit s'il doit aller voir.

        Les fichiers modifies sont nommes a part pour la meme raison : « il a
        fait quelque chose » et « il a change ces trois fichiers-la » ne
        demandent pas la meme attention.
        """
        echecs = [a for a in rendu if not a["ok"]]
        entete = f"**Dioumtoukay — {len(rendu)} action(s)"
        entete += f", {len(echecs)} en echec**" if echecs else ", aucune en echec**"

        detail = "\n".join(
            f"- {'OK ' if a['ok'] else 'ECHEC'} `{a['action']}` — {a['message']}"
            for a in rendu) or "- aucune action executee"

        touches = cls.fichiers_touches(rendu)
        modifies = ("\n\n**Fichiers modifies :** "
                    + ", ".join(f"`{f}`" for f in touches)) if touches else ""

        return f"{entete}\n\n{detail}{modifies}\n\n{conclusion}".strip()

    def _retenir(self, demande: str, conclusion: str, rendu: List[Dict[str, Any]]) -> None:
        """Garde une trace de ce travail dans la mémoire longue.

        Le journal dit ce qui a tourné, action par action ; la mémoire retient
        ce qui a été fait et pourquoi, pour que « reprends ce que tu faisais
        hier sur mon site » veuille dire quelque chose. Elle ne retient un
        travail que s'il a **modifié** quelque chose : se souvenir d'une lecture
        ne sert personne.

        Ne lève jamais : une mémoire en panne ne doit pas emporter le rapport.
        """
        touches = self.fichiers_touches(rendu)
        if self.memoire_longue is None or not touches:
            return
        try:
            retenir_l_echange(
                self.memoire_longue,
                f"[Dioumtoukay] {demande}",
                f"Fichiers modifies : {', '.join(touches)}. {conclusion}".strip(),
                source=f"travail de Dioumtoukay du {date.today().isoformat()}")
        except Exception as erreur:  # noqa: BLE001 — le rapport passe avant la memoire
            logger.warning("Travail non retenu en memoire : %s", erreur)
