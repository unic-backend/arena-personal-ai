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

from core.actions.resultat import Statut
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
#:
#: `analyser` et `diagnostiquer` datent de DEC-0073 : avant, `RepoEngineerAgent`
#: et `SWEAgent` étaient deux portes séparées que le propriétaire devait choisir
#: à la place de Dioumtoukay — leur analyse ne lui servait jamais. Elles
#: deviennent ici des outils qu'il consulte lui-même, en cours de tâche.
#: `ouvrir_pr` et `etat_ci` : le connecteur GitHub (core/connectors/github.py,
#: DEC-0073), le premier acces de Dioumtoukay a l'API GitHub — jusqu'ici,
#: seul `git` en shell nu, sans PR ni CI. `ouvrir_pr` passe par la meme
#: confirmation que toute autre ecriture externe (config/permissions_
#: services.yaml) : Dioumtoukay ne peut pas la contourner en l'appelant.
#: `convertir` : le connecteur `file_conversion` (DEC-0074, mission
#: « File_Converter_Pro »). Chemin d'entree GENERIQUE de cette capacite —
#: n'importe quel modele qui pilote Dioumtoukay peut demander une conversion
#: sans savoir que LibreOffice/Pillow/ffmpeg existent derriere.
#: `organiser_*` : le connecteur `file_organization` (DEC-0075, mission
#: « AI File Sorter »). Quatre actions, jamais une mutation directe : un
#: plan se propose (`organiser_planifier`), puis s'applique seulement sur
#: son identifiant deja valide (`organiser_appliquer`) — jamais une liste
#: d'operations fournie une deuxieme fois, non revue.
ACTIONS = ("lire", "chercher", "lister", "ecrire", "remplacer", "deplacer",
           "executer", "analyser", "diagnostiquer", "ouvrir_pr", "etat_ci",
           "convertir", "organiser_inspecter", "organiser_planifier",
           "organiser_appliquer", "organiser_annuler",
           "pdf_fusionner", "pdf_demonter", "pdf_pages", "pdf_extraire_texte",
           "terminer")

#: Les actions qui modifient quelque chose. Elles sont comptées à part dans le
#: rapport : « j'ai lu quatre fichiers » et « j'ai modifié quatre fichiers » ne
#: se lisent pas pareil, et c'est la seconde phrase qui demande une vérification.
ACTIONS_QUI_MODIFIENT = frozenset({"ecrire", "remplacer", "deplacer"})

#: Les actions dont la SORTIE est le résultat qui compte, pas seulement le
#: message. `_rapport()` ne montre le détail complet que de celles-ci : pour
#: `lire` ou `chercher`, le message suffit et la sortie serait du bruit.
#: `convertir` y entre pour la même raison qu'`etat_ci` : le détail (moteur
#: utilisé, URL du fichier écrit, tailles avant/après) est ce que le
#: propriétaire veut voir, pas seulement « converti ». `organiser_inspecter`/
#: `organiser_planifier` de même : l'inventaire et le plan JSON complet sont
#: ce qu'il doit lire pour décider — jamais `organiser_appliquer`/`_annuler`,
#: dont le message résume déjà les comptages (même choix qu'`ouvrir_pr`).
#: `pdf_fusionner`/`_demonter`/`_pages`/`_extraire_texte` de même : URL du
#: fichier écrit, liste des documents (manifeste), ou texte lui-même sont
#: ce que le propriétaire lit pour vérifier, pas un simple « fait ».
ACTIONS_QUI_ANALYSENT = frozenset({
    "analyser", "diagnostiquer", "etat_ci", "convertir",
    "organiser_inspecter", "organiser_planifier",
    "pdf_fusionner", "pdf_demonter", "pdf_pages", "pdf_extraire_texte",
})

_ETIQUETTE = re.compile(r"^\s*ACTION\s*:\s*(\w+)", re.IGNORECASE | re.MULTILINE)
_CHAMP = re.compile(
    r"^\s*(CHEMIN|SOURCE|DESTINATION|COMMANDE|DOSSIER|TEXTE|DEPOT|TITRE|TETE|BASE|REF|FORMAT"
    r"|PLAN_ID|CONFIRMER_SUPPRESSION|OPERATION|PAGES|DEGRES|FORMAT_PDFX)"
    r"\s*:\s*(.+)$",
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

ACTION: analyser
TEXTE: comment est organisee la gestion des connecteurs dans ce depot ?

ACTION: diagnostiquer
TEXTE: la route /machine/adresse rend 500 au lieu de 401 sans cle

ACTION: ouvrir_pr
DEPOT: owner/repo
TETE: ta-branche
BASE: main
TITRE: Corrige la route /machine/adresse
CONTENU:
ce que le correctif change, pour qui va relire
FIN

ACTION: etat_ci
DEPOT: owner/repo
REF: ta-branche

ACTION: convertir
CHEMIN: documents/devis.pdf
FORMAT: docx

ACTION: organiser_inspecter
DOSSIER: vrac

ACTION: organiser_planifier
DOSSIER: vrac
CONTENU:
creer_dossier|Images||photos a trier
deplacer|IMG_2048.jpg|Images/clouds_over_lake.jpg|photo de nuages
FIN

ACTION: organiser_appliquer
PLAN_ID: identifiant rendu par organiser_planifier

ACTION: organiser_annuler
PLAN_ID: identifiant d'un plan deja applique

ACTION: pdf_fusionner
TITRE: Dossier client
FORMAT_PDFX: oui
CONTENU:
contrat.pdf
devis.pdf
facture.pdf
FIN

ACTION: pdf_demonter
CHEMIN: dossier-client.pdfx

ACTION: pdf_pages
CHEMIN: rapport.pdf
OPERATION: extraire_pages
PAGES: 3,4,5,6,7

ACTION: pdf_extraire_texte
CHEMIN: facture.pdf

ACTION: terminer
CONTENU:
ce que tu as fait, en francais simple, pour le proprietaire
FIN

COMMENT TRAVAILLER

1. TROUVER avant de corriger. `chercher` te dit dans quel fichier est le
   probleme ; deviner le fichier fait perdre des tours. Sur une tache large ou
   floue (« comment est fait ce depot », « ou est le bug »), `analyser` et
   `diagnostiquer` peuvent trouver plus vite qu'une suite de `chercher` a
   l'aveugle — ce sont deux specialistes, consulte-les, ne les remplace pas.
2. LIRE avant de modifier. Tu ne modifies jamais un fichier que tu n'as pas lu
   dans cette conversation. `analyser` et `diagnostiquer` NE MODIFIENT RIEN
   eux-memes : ils proposent, c'est toujours toi qui appliques par `remplacer`
   ou `ecrire`, apres avoir lu le fichier concerne.
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
6. `ouvrir_pr` s'ouvre TOUJOURS en brouillon, meme si tu ne l'as pas demande —
   ce n'est pas un defaut a contourner. Elle demande une confirmation au
   proprietaire avant de partir : elle peut donc rendre « en attente » au lieu
   d'un lien tout de suite. Ne la retente pas plusieurs fois pour la meme
   branche en esperant un autre resultat.
7. `convertir` choisit elle-meme le moteur (LibreOffice, Pillow, ffmpeg...) —
   tu donnes juste CHEMIN et FORMAT (l'extension cible, sans le point). Un
   couple de formats que rien ne convertit encore te le dit clairement ;
   n'invente jamais un fichier converti que tu n'as pas reellement obtenu.
8. Pour ranger des fichiers : `organiser_inspecter` d'abord (regarde ce qu'il
   y a vraiment avant de proposer quoi que ce soit), PUIS `organiser_
   planifier` — un plan par ligne `type|source|destination|raison`
   (`destination` vide pour `supprimer`). `organiser_planifier` NE DEPLACE
   RIEN : il rend un identifiant de plan valide. Seul `organiser_appliquer`
   avec cet identifiant deplace reellement — et une suppression dans le plan
   exige en plus `CONFIRMER_SUPPRESSION: oui`, sans quoi elle est refusee.
   `organiser_annuler` defait un plan applique, sauf ses suppressions
   (jamais reversibles). N'invente jamais un identifiant de plan.
9. `pdf_fusionner` prend un fichier par ligne dans CONTENU, DANS L'ORDRE
   demande — c'est cet ordre qui range les documents dans le resultat.
   `FORMAT_PDFX: oui` ajoute le manifeste (recuperable ensuite par
   `pdf_demonter`) ; sans lui, c'est une simple concatenation de PDF.
   `pdf_pages` : PAGES est une liste d'index a partir de 0 (page 1 du
   document = index 0) — jamais a partir de 1. OPERATION choisit entre
   `reordonner` (PAGES devient le nouvel ordre complet), `supprimer_pages`,
   `extraire_pages`, ou `pivoter_pages` (ajoute DEGRES, multiple de 90).

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
                 analyste: Optional[Any] = None, chercheur_de_bug: Optional[Any] = None,
                 connecteur_github: Optional[Any] = None,
                 connecteur_file_conversion: Optional[Any] = None,
                 connecteur_file_organization: Optional[Any] = None,
                 connecteur_pdf: Optional[Any] = None,
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
        # DEC-0073 : deux specialistes en lecture seule, consultes en cours de
        # tache plutot que d'etre deux portes separees. Optionnels — sans eux,
        # `analyser`/`diagnostiquer` repondent qu'ils manquent, comme toute
        # capacite non branchee ailleurs dans ARENA.
        self.analyste = analyste
        self.chercheur_de_bug = chercheur_de_bug
        # Le connecteur GitHub (core/connectors/github.py) : la creation de PR
        # y passe par la meme confirmation que toute autre ecriture externe —
        # Dioumtoukay ne contourne rien en l'appelant, il herite de la garde.
        self.connecteur_github = connecteur_github
        # Le connecteur de conversion de fichiers (DEC-0074) : meme discipline
        # que le connecteur GitHub — Dioumtoukay ne sait pas quel moteur
        # tourne derriere, il herite juste de la garde (confirmation, coupe-
        # circuit WRITE_FILES) deja portee par le connecteur lui-meme.
        self.connecteur_file_conversion = connecteur_file_conversion
        # Le connecteur de classement de fichiers (DEC-0075, mission « AI
        # File Sorter ») : meme discipline encore — un plan se propose,
        # SE VALIDE (le connecteur, jamais Dioumtoukay), et ne s'applique
        # que sur son identifiant deja valide, sous confirmation.
        self.connecteur_file_organization = connecteur_file_organization
        # Le connecteur PDF (DEC-0076, mission « PDFx ») : fusionner/
        # scinder/pages/manifeste. Chaque operation ecrit un fichier NEUF,
        # jamais la source — aucune ne demande de confirmation pour cette
        # raison meme.
        self.connecteur_pdf = connecteur_pdf
        # Le journal DURABLE de ce qu'il a deja fait (DEC-0072). La memoire
        # longue garde un RESUME de chaque travail ; celui-ci garde les ETAPES,
        # pour qu'une tache arretee a la 12e action reprenne a la 13e au lieu
        # de tout refaire. Les deux ne font pas double emploi : l'une sert a se
        # souvenir, l'autre a continuer.
        self.reprises = reprises if reprises is not None else JournalDeReprise()

    # --- Exécution d'une action ---------------------------------------------------

    async def _consulter(self, specialiste: Optional[Any], nom_specialiste: str,
                         question: str) -> Resultat:
        """Interroge un specialiste en lecture seule (RepoEngineerAgent ou
        SWEAgent) et rend ce qu'il a repondu comme un `Resultat` ordinaire.

        DEC-0041 : ces deux agents ne modifient jamais rien eux-memes — c'est
        pour ca qu'ils sont surs a appeler en cours de boucle, sans passer par
        les autres actions de l'atelier. Un appel qui leve (le modele n'a pas
        repondu, par exemple) devient un echec rapporte, jamais une exception
        qui casserait la tache entiere de Dioumtoukay pour la faute d'un
        outil consulte en chemin.
        """
        if not question:
            return Resultat(False, "Le champ TEXTE (la question) est vide.")
        if specialiste is None:
            return Resultat(False, f"{nom_specialiste} n'est pas branche sur cette machine.")
        try:
            reponse = await specialiste.run(question)
        except Exception as erreur:  # noqa: BLE001 — un outil consulte ne casse pas la tache
            return Resultat(False, f"{nom_specialiste} n'a pas repondu : "
                                   f"{type(erreur).__name__}: {erreur}")
        if reponse.get("status") not in ("success", None):
            return Resultat(False, reponse.get("response") or
                            f"{nom_specialiste} a echoue sans detail.")
        return Resultat(True, f"{nom_specialiste} a repondu.",
                        sortie=reponse.get("response", ""))

    def _via_github(self, capacite: str, **parametres: Any) -> Resultat:
        """Appelle le connecteur GitHub et rend son `ResultatAction` comme un
        `Resultat` ordinaire — Dioumtoukay ne voit qu'un seul type de resultat,
        quelle que soit la source.

        **La confirmation n'est pas contournee ici.** `connecteur.executer()`
        est le meme point d'entree que `/connectors/github/...` : une capacite
        `CONFIRMATION` (creer_pull_request) rend `A_CONFIRMER` sans avoir
        touche le reseau, exactement comme si le propriétaire l'avait demande
        depuis l'interface. `A_CONFIRMER` est rapporte comme un succes
        PARTIEL — l'action a bien ete deposee, mais rien n'est encore parti.
        """
        if self.connecteur_github is None:
            return Resultat(False, "Le connecteur GitHub n'est pas branche sur cette machine.")
        try:
            resultat = self.connecteur_github.executer(capacite, **parametres)
        except Exception as erreur:  # noqa: BLE001 — un connecteur qui leve ne casse pas la tache
            return Resultat(False, f"GitHub n'a pas repondu : {type(erreur).__name__}: {erreur}")

        if resultat.statut in (Statut.SUCCES, Statut.PARTIEL, Statut.A_CONFIRMER):
            detail = "\n".join(f"{cle}: {valeur}" for cle, valeur in resultat.detail.items())
            return Resultat(True, resultat.message, sortie=detail)
        return Resultat(False, resultat.message)

    def _via_file_conversion(self, capacite: str, **parametres: Any) -> Resultat:
        """Meme pont que `_via_github`, vers le connecteur `file_conversion`
        (DEC-0074) — un seul type de resultat pour Dioumtoukay, quelle que
        soit la source."""
        if self.connecteur_file_conversion is None:
            return Resultat(False, "Le connecteur de conversion n'est pas branche sur cette machine.")
        try:
            resultat = self.connecteur_file_conversion.executer(capacite, **parametres)
        except Exception as erreur:  # noqa: BLE001 — un connecteur qui leve ne casse pas la tache
            return Resultat(False, f"Conversion impossible : {type(erreur).__name__}: {erreur}")

        if resultat.statut in (Statut.SUCCES, Statut.PARTIEL, Statut.A_CONFIRMER):
            detail = "\n".join(f"{cle}: {valeur}" for cle, valeur in resultat.detail.items())
            return Resultat(True, resultat.message, sortie=detail)
        return Resultat(False, resultat.message)

    def _via_file_organization(self, capacite: str, **parametres: Any) -> Resultat:
        """Meme pont, vers le connecteur `file_organization` (DEC-0075)."""
        if self.connecteur_file_organization is None:
            return Resultat(False, "Le connecteur de classement n'est pas branche sur cette machine.")
        try:
            resultat = self.connecteur_file_organization.executer(capacite, **parametres)
        except Exception as erreur:  # noqa: BLE001 — un connecteur qui leve ne casse pas la tache
            return Resultat(False, f"Classement impossible : {type(erreur).__name__}: {erreur}")

        if resultat.statut in (Statut.SUCCES, Statut.PARTIEL, Statut.A_CONFIRMER):
            detail = "\n".join(f"{cle}: {valeur}" for cle, valeur in resultat.detail.items())
            return Resultat(True, resultat.message, sortie=detail)
        return Resultat(False, resultat.message)

    @staticmethod
    def _lire_operations(contenu: str) -> Optional[List[Dict[str, str]]]:
        """`type|source|destination|raison` par ligne, `destination` vide
        pour `supprimer`. `None` si une ligne est illisible — jamais une
        supposition sur ce qu'elle voulait dire."""
        operations = []
        for ligne in (contenu or "").splitlines():
            ligne = ligne.strip()
            if not ligne:
                continue
            morceaux = ligne.split("|")
            if len(morceaux) < 2:
                return None
            morceaux += [""] * (4 - len(morceaux))
            type_op, source, destination, raison = (m.strip() for m in morceaux[:4])
            if not type_op or not source:
                return None
            operations.append({"type": type_op, "source": source,
                              "destination": destination, "raison": raison})
        return operations or None

    def _via_pdf(self, capacite: str, **parametres: Any) -> Resultat:
        """Meme pont, vers le connecteur `pdf` (DEC-0076)."""
        if self.connecteur_pdf is None:
            return Resultat(False, "Le connecteur PDF n'est pas branche sur cette machine.")
        try:
            resultat = self.connecteur_pdf.executer(capacite, **parametres)
        except Exception as erreur:  # noqa: BLE001 — un connecteur qui leve ne casse pas la tache
            return Resultat(False, f"Operation PDF impossible : {type(erreur).__name__}: {erreur}")

        if resultat.statut in (Statut.SUCCES, Statut.PARTIEL, Statut.A_CONFIRMER):
            detail = "\n".join(f"{cle}: {valeur}" for cle, valeur in resultat.detail.items())
            return Resultat(True, resultat.message, sortie=detail)
        return Resultat(False, resultat.message)

    @staticmethod
    def _lire_fichiers(contenu: str) -> Optional[List[str]]:
        """Un chemin de fichier par ligne, tel quel — `None` si vide."""
        fichiers = [ligne.strip() for ligne in (contenu or "").splitlines() if ligne.strip()]
        return fichiers or None

    @staticmethod
    def _lire_pages(texte: str) -> Optional[List[int]]:
        """`"3,4,5"` -> `[3, 4, 5]`. `None` si un seul element n'est pas un entier."""
        if not (texte or "").strip():
            return None
        try:
            return [int(p.strip()) for p in texte.split(",") if p.strip()]
        except ValueError:
            return None

    async def _executer_action(self, action: Action) -> Resultat:
        """Fait ce que l'action demande, via l'atelier — ou un specialiste."""
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
        if action.nom == "analyser":
            return await self._consulter(self.analyste, "RepoEngineerAgent",
                                         champs.get("TEXTE", ""))
        if action.nom == "diagnostiquer":
            return await self._consulter(self.chercheur_de_bug, "SWEAgent",
                                         champs.get("TEXTE", ""))
        if action.nom == "ouvrir_pr":
            depot, tete = champs.get("DEPOT", ""), champs.get("TETE", "")
            if not depot or not tete:
                return Resultat(False, "Il manque DEPOT (owner/repo) ou TETE (la branche source).")
            return self._via_github(
                "creer_pull_request", depot=depot, titre=champs.get("TITRE", "Sans titre"),
                tete=tete, base=champs.get("BASE") or "main", corps=action.contenu)
        if action.nom == "etat_ci":
            depot, ref = champs.get("DEPOT", ""), champs.get("REF", "")
            if not depot or not ref:
                return Resultat(False, "Il manque DEPOT (owner/repo) ou REF (SHA ou branche).")
            return self._via_github("etat_ci", depot=depot, ref=ref)
        if action.nom == "convertir":
            chemin, format_cible = champs.get("CHEMIN", ""), champs.get("FORMAT", "")
            if not chemin or not format_cible:
                return Resultat(False, "Il manque CHEMIN (le fichier a convertir) ou "
                                       "FORMAT (l'extension cible, sans le point).")
            return self._via_file_conversion(
                "convertir", entree=chemin, format_cible=format_cible)
        if action.nom == "organiser_inspecter":
            return self._via_file_organization(
                "inspecter", dossier=champs.get("DOSSIER", "."), avec_contenu=True)
        if action.nom == "organiser_planifier":
            operations = self._lire_operations(action.contenu)
            if operations is None:
                return Resultat(False, "Il manque le bloc CONTENU: … FIN avec au moins une "
                                       "ligne `type|source|destination|raison`.")
            return self._via_file_organization(
                "planifier", dossier=champs.get("DOSSIER", "."), operations=operations)
        if action.nom == "organiser_appliquer":
            plan_id = champs.get("PLAN_ID", "")
            if not plan_id:
                return Resultat(False, "Il manque PLAN_ID — l'identifiant rendu par organiser_planifier.")
            confirmer_suppression = champs.get("CONFIRMER_SUPPRESSION", "").strip().lower() in (
                "oui", "true", "yes")
            return self._via_file_organization(
                "appliquer", plan_id=plan_id, confirmer_suppression=confirmer_suppression)
        if action.nom == "organiser_annuler":
            plan_id = champs.get("PLAN_ID", "")
            if not plan_id:
                return Resultat(False, "Il manque PLAN_ID — l'identifiant d'un plan deja applique.")
            return self._via_file_organization("annuler", plan_id=plan_id)
        if action.nom == "pdf_fusionner":
            fichiers = self._lire_fichiers(action.contenu)
            if fichiers is None:
                return Resultat(False, "Il manque le bloc CONTENU: … FIN avec un chemin de fichier par ligne.")
            format_pdfx = champs.get("FORMAT_PDFX", "").strip().lower() in ("oui", "true", "yes")
            return self._via_pdf("fusionner", fichiers=fichiers, titre=champs.get("TITRE", ""),
                                 format_pdfx=format_pdfx)
        if action.nom == "pdf_demonter":
            chemin = champs.get("CHEMIN", "")
            if not chemin:
                return Resultat(False, "Il manque CHEMIN — le fichier PDF/PDFx à démonter.")
            return self._via_pdf("demonter", fichier=chemin)
        if action.nom == "pdf_pages":
            chemin, operation = champs.get("CHEMIN", ""), champs.get("OPERATION", "")
            pages = self._lire_pages(champs.get("PAGES", ""))
            if not chemin or operation not in (
                    "reordonner", "supprimer_pages", "extraire_pages", "pivoter_pages"):
                return Resultat(False, "Il manque CHEMIN, ou OPERATION n'est pas l'une de : "
                                       "reordonner, supprimer_pages, extraire_pages, pivoter_pages.")
            if pages is None:
                return Resultat(False, "Il manque PAGES — une liste d'index séparés par des virgules, à partir de 0.")
            champ_pages = "ordre" if operation == "reordonner" else "pages"
            parametres_pdf = {"fichier": chemin, champ_pages: pages}
            if operation == "pivoter_pages":
                try:
                    parametres_pdf["degres"] = int(champs.get("DEGRES", "90"))
                except ValueError:
                    return Resultat(False, "DEGRES doit être un nombre (multiple de 90).")
            return self._via_pdf(operation, **parametres_pdf)
        if action.nom == "pdf_extraire_texte":
            chemin = champs.get("CHEMIN", "")
            if not chemin:
                return Resultat(False, "Il manque CHEMIN — le fichier PDF à lire.")
            return self._via_pdf("extraire_texte", fichier=chemin)
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
            resultat = await self._executer_action(action)
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

        # La sortie d'un `analyser`/`diagnostiquer` REUSSI est le resultat
        # lui-meme — la cacher derriere « RepoEngineerAgent a repondu » serait
        # exactement le defaut que ces deux actions existent pour corriger :
        # une analyse produite et jamais lue par le proprietaire.
        analyses = "\n\n".join(
            f"**{a['action']} :**\n{a['sortie']}"
            for a in rendu if a["ok"] and a["action"] in ACTIONS_QUI_ANALYSENT and a.get("sortie"))
        analyses = f"\n\n{analyses}" if analyses else ""

        return f"{entete}\n\n{detail}{modifies}{analyses}\n\n{conclusion}".strip()

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
