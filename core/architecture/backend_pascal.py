"""Pascal derrière `architecture_3d` — un backend, jamais la capacité.

Pascal Editor (pascalorg/editor, **MIT**) publie `@pascal-app/mcp`, un serveur
MCP qui pilote son graphe de scène **sans navigateur, sans WebGPU, sans React
et sans base de données** — vérifié dans son propre README et mesuré ici :
46 outils exposés, un projet créé en 10 ms.

**Aucune ligne de Pascal n'entre dans ce dépôt.** Il est installé comme
paquet npm dans `tools/architecture/pascal/`, hors du dépôt
(`.gitignore`), et ARENA lui parle par le transport MCP qu'elle possède
déjà (`core/mcp/stdio_transport.py`, DEC-0012). Un modèle n'atteint jamais ce
serveur : il demande une capacité, ARENA décide.

---

## Deux mesures qui ont changé l'intégration

**1. Le paquet publié ne tourne PAS sous Node, malgré son README.**
`@pascal-app/mcp@1.0.0-beta.6` importe ses modules sans extension
(`from '../server'`), ce que le résolveur ESM de Node refuse
(`ERR_MODULE_NOT_FOUND`) et que Bun accepte. Mesuré le 07/09/2026 sous
Node v22.22.2, au-dessus du minimum annoncé. **Le moteur d'exécution est donc
Bun**, et la sonde le dit au lieu de le supposer.

**2. `zod` 4.5.4 casse toutes les écritures.** Pascal demande `zod ^4.3.5` ;
npm installe 4.5.4, dont `discriminatedUnion` refuse désormais une option au
discriminant `undefined`. Résultat mesuré : lecture parfaite, et **chaque
mutation** (`create_wall`, `create_room`, `add_door`…) rendait
`Duplicate discriminator value "undefined"`. Le démarrage du serveur, lui,
réussissait — c'est exactement le genre de panne qu'une sonde « le processus
répond » déclare opérationnelle à tort. `zod` est donc **épinglé à 4.3.5**
dans l'installation, et un test crée un vrai mur plutôt que de se contenter
d'un serveur qui démarre.

---

## Ce que ce fichier traduit, et pourquoi lui seul

`OUTILS` est la seule table qui connaisse les noms de Pascal. Le jour où un
autre moteur prend sa place, c'est ce fichier qu'on remplace — le vocabulaire
d'ARENA (`capacite.py`) et tout ce qui l'appelle ne bougent pas.

Deux écarts réels entre le schéma annoncé par Pascal et son exécution sont
absorbés ici, jamais renvoyés bruts à l'appelant :

- `add_door` / `add_window` déclarent `wallId` seul comme requis, mais
  **exigent à l'exécution** `t` ou `position`. ARENA pose donc un milieu de
  mur par défaut (`t=0.5`), qui est le geste attendu quand personne ne
  précise.
- `create_level` échoue sur un bâtiment neuf : `create_projet` a déjà créé
  un premier niveau. ARENA ne le contourne pas — elle le documente, et
  `lister_niveaux` donne l'identifiant à utiliser.
"""
from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from core.mcp.stdio_transport import ClientMcpStdio

logger = logging.getLogger("usman.architecture.pascal")

#: Où le paquet npm est installé. Hors du dépôt, comme Lean et les moteurs
#: vidéo : ce n'est pas du source d'ARENA, c'est un moteur qu'elle pilote.
DOSSIER_PAR_DEFAUT = Path("tools") / "architecture" / "pascal"

#: Le point d'entrée du serveur, tel que son `package.json` le déclare
#: (`bin.pascal-mcp`). Chemin en dur plutôt que `npx`/`bunx` : ces deux-là
#: peuvent aller chercher sur le réseau et écrivent sur la sortie standard,
#: qui EST le fil MCP.
ENTREE = "node_modules/@pascal-app/mcp/dist/bin/pascal-mcp.js"

#: Bun, pas Node : voir la mesure 1 de l'en-tête de ce fichier.
MOTEUR_JS = "bun"

#: Une opération d'architecture est locale et rapide (mesuré : 1 à 14 ms).
#: Le délai protège d'un moteur bloqué, il ne sert pas de marge de confort.
DELAI_SECONDES = 60.0

#: Le vocabulaire d'ARENA -> l'outil réel de Pascal. **La seule table qui
#: connaisse les noms de Pascal dans tout le dépôt.**
OUTILS: Dict[str, str] = {
    "creer_projet": "create_project",
    "creer_niveau": "create_level",
    "creer_mur": "create_wall",
    "creer_coque": "create_story_shell",
    "poser_porte": "add_door",
    "poser_fenetre": "add_window",
    "creer_piece": "create_room",
    "poser_objet": "place_item",
    "supprimer": "delete_node",
    "annuler": "undo",
    "refaire": "redo",
    "enregistrer": "save_scene",
    "charger": "load_scene",
    "inspecter": "get_scene",
    "lister_murs": "get_walls",
    "lister_zones": "get_zones",
    "lister_niveaux": "list_levels",
    "lister_scenes": "list_scenes",
    "mesurer": "measure",
    "valider": "validate_scene",
    "exporter_json": "export_json",
    "exporter_glb": "export_glb",
}

#: Les paramètres qu'ARENA nomme en français -> ceux de Pascal. Traduire ici
#: évite que le vocabulaire du moteur remonte jusqu'à l'appelant.
CHAMPS: Dict[str, str] = {
    # `titre` et pas `nom` : le registre des connecteurs prend deja `nom`
    # comme PREMIER argument positionnel (le connecteur vise). Un parametre
    # metier appele `nom` entrait en collision avec lui — mesure du
    # 07/09/2026, `TypeError: got multiple values for argument 'nom'` sur la
    # toute premiere execution bout en bout. Renommer valait mieux que
    # contourner : la collision serait revenue au prochain appelant.
    "titre": "name", "niveau": "levelId", "batiment": "buildingId",
    "mur": "wallId", "debut": "start", "fin": "end",
    "hauteur": "height", "epaisseur": "thickness", "largeur": "width",
    "polygone": "polygon", # `id` et non `nodeId` : mesure du 07/09/2026, `delete_node` rend
    # « expected string, received undefined at id ». Le nom du champ vient de
    # l'execution reelle, jamais d'une devinette sur le nom de l'outil.
    "element": "id", "de": "fromId", "a": "toId",
    "emprise": "footprint", "hauteur_murs": "wallHeight",
    "position": "t", "etiquette": "label",
}

#: Ce que Pascal exige à l'exécution mais ne déclare pas requis dans son
#: schéma. Voir l'en-tête : sans `t`, percer une ouverture échoue.
DEFAUTS: Dict[str, Dict[str, Any]] = {
    "poser_porte": {"t": 0.5},
    "poser_fenetre": {"t": 0.5},
}


def _traduire(parametres: Dict[str, Any]) -> Dict[str, Any]:
    """Les noms français d'ARENA vers ceux de Pascal, sans rien perdre.

    Un paramètre déjà écrit dans la langue du moteur passe tel quel : un
    appelant averti (un test, un plan structuré) peut viser précis sans que
    la traduction lui barre la route.
    """
    return {CHAMPS.get(cle, cle): valeur for cle, valeur in parametres.items()
            if valeur is not None}


class BackendPascal:
    """Le moteur Pascal, un processus par session, ouvert au premier besoin."""

    nom = "pascal"

    def __init__(self, dossier: Optional[Path] = None,
                 moteur_js: str = MOTEUR_JS) -> None:
        self.dossier = Path(dossier) if dossier else DOSSIER_PAR_DEFAUT
        self.moteur_js = moteur_js
        #: Une session = un processus. Rien d'autre ne les tient : c'est ce
        #: qui garantit que deux chantiers ne partagent jamais une scène.
        self._sessions: Dict[str, ClientMcpStdio] = {}

    # --- Santé ---------------------------------------------------------------

    def sonder(self) -> Tuple[bool, str]:
        """Ce qui manque pour que Pascal tourne — mesuré, pas deviné.

        Trois choses peuvent manquer, et chacune a sa phrase : le moteur
        JavaScript, le dossier d'installation, le paquet lui-même. Une sonde
        qui dirait « prêt » parce qu'un dossier existe referait le défaut du
        connecteur de navigation (DEC-0066).
        """
        if shutil.which(self.moteur_js) is None:
            return False, (
                f"« {self.moteur_js} » n'est pas installe. Pascal ne tourne PAS "
                "sous Node : son paquet publie importe ses modules sans "
                "extension, ce que Node refuse et que Bun accepte "
                "(mesure du 07/09/2026). Installe Bun : curl -fsSL "
                "https://bun.sh/install | bash")
        if not self.dossier.is_dir():
            return False, (f"le dossier {self.dossier} n'existe pas : "
                           "l'installation de Pascal n'a jamais ete faite.")
        if not (self.dossier / ENTREE).is_file():
            return False, (f"{ENTREE} est absent de {self.dossier} : lance "
                           "« npm install » dans ce dossier.")
        return True, ""

    # --- Sessions ------------------------------------------------------------

    def _client(self, session: str) -> ClientMcpStdio:
        """Le moteur de CETTE session, démarré au premier appel.

        Raises:
            RuntimeError: le moteur ne peut pas démarrer, avec la raison.
        """
        existant = self._sessions.get(session)
        if existant is not None:
            return existant

        pret, manque = self.sonder()
        if not pret:
            raise RuntimeError(manque)

        client = ClientMcpStdio(
            commande=[self.moteur_js, ENTREE, "--stdio"],
            dossier=str(self.dossier), delai=DELAI_SECONDES,
            # Le serveur ecrit sa banniere sur stderr (verifie), donc le fil
            # MCP reste propre. `NO_COLOR` evite des sequences ANSI dans les
            # messages d'erreur qu'ARENA relaie ensuite au proprietaire.
            environnement={**os.environ, "NO_COLOR": "1"})
        reponse = client.ouvrir()
        if not reponse.ok:
            client.fermer()
            raise RuntimeError(f"Pascal n'a pas demarre : {reponse.raison}")

        self._sessions[session] = client
        logger.info("Pascal ouvert pour la session %s", session)
        return client

    def fermer(self, session: str) -> None:
        client = self._sessions.pop(session, None)
        if client is not None:
            client.fermer()
            logger.info("Pascal ferme pour la session %s", session)

    def fermer_tout(self) -> None:
        """Aucun processus ne survit a l'arret. Appelé par le connecteur."""
        for session in list(self._sessions):
            self.fermer(session)

    # --- Exécution -----------------------------------------------------------

    def executer(self, session: str, operation: str,
                 parametres: Dict[str, Any]) -> Tuple[bool, Dict[str, Any], str]:
        outil = OUTILS.get(operation)
        if outil is None:
            return False, {}, (
                f"le backend Pascal ne sait pas faire « {operation} ». "
                "Cette operation existe dans le vocabulaire d'ARENA mais "
                "aucun outil de ce moteur ne la rend.")

        try:
            client = self._client(session)
        except RuntimeError as erreur:
            return False, {}, str(erreur)

        arguments = {**DEFAUTS.get(operation, {}), **_traduire(parametres)}
        reponse = client.appeler(outil, arguments)
        if not reponse.ok:
            return False, {}, f"le moteur n'a pas repondu : {reponse.raison}"

        # MCP distingue deux echecs : le transport (`ok`) et l'applicatif
        # (`isError`). Confondre les deux ferait passer « ce mur est invalide »
        # pour une reussite — le contrat `Reponse` d'ARENA les separe deja.
        applicative = reponse.erreur_applicative
        if applicative:
            return False, {}, applicative

        return True, _charge_utile(reponse.contenu_texte), ""


def _charge_utile(texte: str) -> Dict[str, Any]:
    """Le JSON rendu par le moteur, ou le texte brut sous `texte`.

    Pascal rend du JSON pour tout ce qu'ARENA lui demande (mesuré), mais un
    outil qui renverrait de la prose ne doit pas faire tomber l'appel : ce
    qu'on ne sait pas structurer est rendu tel quel, pas jeté.
    """
    import json
    propre = (texte or "").strip()
    if not propre:
        return {}
    try:
        charge = json.loads(propre)
    except (ValueError, TypeError):
        return {"texte": propre}
    return charge if isinstance(charge, dict) else {"resultat": charge}
