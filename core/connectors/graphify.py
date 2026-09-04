"""Connecteur Graphify — le graphe de connaissances du code d'ARENA lui-meme.

Graphify (Graphify-Labs, Apache-2.0, https://github.com/Graphify-Labs/graphify)
construit un graphe structurel a partir du code source, via tree-sitter :
entites (fonctions, classes, fichiers) et relations (herite, appelle,
importe, contient) entre elles. Cent pour cent local et hors ligne — aucun
appel modele n'est necessaire pour l'extraction de base (`graphify update`),
seul l'etiquetage des communautes par un nom (`graphify label`, jamais
branche ici) en demanderait un.

Ce que ce connecteur N'EST PAS : un generateur de PDF — le devis garde
`core/connectors/devis.py`, inchange, et c'est LUI qui ecrit le fichier final
(DEC-0041/0046) — ni un second systeme de memoire ou de RAG. LightRAG et
Microsoft GraphRAG (`tools/rag/`) gardent leur role : eux resument des
DOCUMENTS deposes a la main dans un espace de travail ; Graphify cartographie
la STRUCTURE du code lui-meme, par lecture directe des fichiers. Deux graphes
distincts, jamais fusionnes, jamais l'un a la place de l'autre.

Ce que ca cartographie aujourd'hui : LE DEPOT LUI-MEME (agents/, core/,
apps/, tools/) — le trou reel mesure le 04/09/2026 : `PROJECT_MEMORY/
PROJECT_MAP.md` est ecrit et tenu a jour a la main, sans rien qui verifie
qu'il correspond encore au code. Le graphe repond a des questions
structurelles (« qu'est-ce qui herite de Connecteur ? », « quel fichier gere
le devis ? ») en quelques centaines de millisecondes, sans relire tout le
depot a chaque question.

**L'ingestion de documents/PDF dans le graphe (extra amont `[pdf]`) n'est PAS
branchee ici — SUGGESTION NON IMPLEMENTEE.** Rien ne l'a verifiee sur un
vrai fichier, et ARENA ne simule jamais une capacite non mesuree
(`core/actions/resultat.py`). `tools/documents/reader.py` reste le seul
chemin de lecture de PDF/DOCX/XLSX/PPTX d'ARENA, inchange.

**Trois regles :**

1. **Construire le graphe ecrit sur disque (`graphify-out/`) ; interroger,
   jamais.** `construire` passe donc par le coupe-circuit `WRITE_FILES`,
   comme toute ecriture de ce depot ; les quatre lectures (interroger,
   chemin, expliquer, hubs) n'exigent que la cle API.
2. **Aucun graphe construit n'est jamais promis a jour.** `sonder()` rend
   NON_CONFIGURE tant qu'aucun `graphify-out/graph.json` n'existe encore —
   jamais OPERATIONNEL sur un fichier qui pourrait dater de la veille sans
   le dire.
3. **Le processus ne survit jamais a l'appel**, comme OpenTakeoff
   (`core/connectors/opentakeoff.py`) : chaque capacite est un
   `subprocess.run` isole avec delai, jamais un serveur qui tourne en fond.
   Aucun processus de fond, aucune surveillance automatique de fichiers
   (`graphify watch`, jamais invoque ici) — la mise a jour reste explicite,
   sur demande.
"""
import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

from core.actions.resultat import ResultatAction, echec, non_configure, succes
from core.connectors.base import Capacite, Connecteur, EtatSante, Sante, _maintenant

logger = logging.getLogger("usman.connecteurs.graphify")

#: La racine du depot — c'est ce que le graphe cartographie par defaut.
RACINE = Path(__file__).resolve().parents[2]

#: Le binaire installe par `pip install graphifyy` (requirements.txt).
#: Reglable : un poste peut l'avoir ailleurs que sur le PATH courant.
GRAPHIFY_BIN = os.getenv("GRAPHIFY_BIN", "").strip() or "graphify"

#: Ou le graphe de CE depot est ecrit. `graphify update <chemin>` ecrit
#: toujours sous `<chemin>/graphify-out/` — non redirigeable par ce moteur ;
#: on pointe donc `<chemin>` sur la racine du depot, sans en inventer un
#: autre. `.gitignore` exclut `graphify-out/` : voir DEC-0046.
DOSSIER_GRAPHE = RACINE / "graphify-out"
GRAPH_JSON = DOSSIER_GRAPHE / "graph.json"

#: Extraction structurelle (tree-sitter, pas de modele) : rapide, mais un
#: depot entier reste plus lourd qu'un fichier. Une requete de graphe deja
#: construit est quasi instantanee ; c'est la construction qui a besoin de
#: marge.
DELAI_CONSTRUCTION_SECONDES = 300.0
DELAI_REQUETE_SECONDES = 30.0

#: Ce que `interroger` renvoie au maximum, en jetons approximatifs. Un budget
#: absent laisserait un depot de 178 modules produire une reponse illisible.
BUDGET_REQUETE_JETONS = 1200


def _binaire_present() -> bool:
    return shutil.which(GRAPHIFY_BIN) is not None


def _lire_stats_graphe() -> Optional[Dict[str, int]]:
    """Le compte reel de noeuds/liens du graphe ecrit, ou None s'il est illisible.

    Jamais devine depuis la taille du fichier ou sa date : un JSON qui ne se
    charge pas n'est pas un graphe utilisable, quelle que soit sa presence
    sur le disque.
    """
    try:
        donnees = json.loads(GRAPH_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(donnees, dict):
        return None
    return {
        "noeuds": len(donnees.get("nodes") or []),
        "liens": len(donnees.get("links") or []),
    }


class ConnecteurGraphify(Connecteur):
    """Le graphe structurel du depot — construit, interroge, jamais devine."""

    service = "graphify"
    nom = "graphify"

    def capacites(self) -> Dict[str, Capacite]:
        return {
            "construire": Capacite(
                nom="construire", action="document",
                description="(Re)construit le graphe structurel du depot (tree-sitter, hors ligne).",
                ecriture=True),
            "interroger": Capacite(
                nom="interroger", action="read",
                description="Question en langage naturel sur la structure du code (traversee BFS).",
                ecriture=False),
            "chemin": Capacite(
                nom="chemin", action="read",
                description="Le plus court chemin entre deux noeuds du graphe.",
                ecriture=False),
            "expliquer": Capacite(
                nom="expliquer", action="read",
                description="Un noeud et ses connexions directes, avec leur provenance.",
                ecriture=False),
            "hubs": Capacite(
                nom="hubs", action="read",
                description="Les noeuds les plus connectes : les points d'appui de l'architecture.",
                ecriture=False),
        }

    def sonder(self) -> Sante:
        """L'ENGIN est-il joignable — pas « un graphe existe-t-il deja ».

        La distinction compte : `_conduire()` (base.py) refuse TOUTE capacite
        tant que `sonder()` ne rend pas OPERATIONNEL — y compris « construire »
        elle-meme. Faire dependre la sante de la presence d'un graphe deja
        construit rendrait « construire » injoignable au tout premier appel :
        exactement le meme piege que mesurer la sante d'un four a sa premiere
        cuisson. OpenTakeoff suit la meme regle (`opentakeoff.py::sonder`) :
        la sante mesure le moteur, jamais son historique de sorties.

        L'absence de graphe reste dite — dans le MESSAGE, informatif — et
        chaque lecture (`interroger`, `chemin`, `expliquer`, `hubs`) la
        verifie elle-meme avant d'agir (`GRAPH_JSON.exists()`).
        """
        if not _binaire_present():
            return Sante(
                etat=EtatSante.NON_CONFIGURE,
                message="graphify n'est pas installe.",
                ce_qui_manque="pip install graphifyy (deja dans requirements.txt)",
                mesure_le=_maintenant())

        if not GRAPH_JSON.exists():
            return Sante(
                etat=EtatSante.OPERATIONNEL,
                message="graphify est installe ; aucun graphe construit pour l'instant.",
                mesure_le=_maintenant())

        stats = _lire_stats_graphe()
        if stats is None:
            return Sante(
                etat=EtatSante.OPERATIONNEL,
                message="graphify est installe ; un graph.json existe mais ne se "
                        "charge pas (reconstruis-le avec « construire »).",
                mesure_le=_maintenant())

        return Sante(
            etat=EtatSante.OPERATIONNEL,
            message=f"Graphe pret : {stats['noeuds']} noeud(s), {stats['liens']} lien(s).",
            mesure_le=_maintenant())

    def authentifier(self) -> bool:
        """Vrai : outil local, aucun identifiant a presenter."""
        return True

    def _lancer(self, arguments: list, delai: float) -> subprocess.CompletedProcess:
        return subprocess.run(
            [GRAPHIFY_BIN, *arguments],
            capture_output=True, text=True, timeout=delai, check=False,
            cwd=str(RACINE),
        )

    def _executer(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        if not _binaire_present():
            return non_configure(
                action=capacite.nom, cible=self.nom,
                ce_qui_manque="pip install graphifyy (deja dans requirements.txt)")

        if capacite.nom == "construire":
            return self._construire()
        if capacite.nom == "interroger":
            return self._interroger(str(parametres.get("question") or "").strip())
        if capacite.nom == "chemin":
            return self._chemin(
                str(parametres.get("depuis") or "").strip(),
                str(parametres.get("vers") or "").strip())
        if capacite.nom == "expliquer":
            return self._expliquer(str(parametres.get("noeud") or "").strip())
        if capacite.nom == "hubs":
            return self._hubs(int(parametres.get("top") or 10))

        return echec(action=capacite.nom, cible=self.nom,
                     message=f"Capacite « {capacite.nom} » non implementee.")

    # --- construire -------------------------------------------------------

    def _construire(self) -> ResultatAction:
        try:
            acheve = self._lancer(
                ["update", str(RACINE), "--no-cluster"], DELAI_CONSTRUCTION_SECONDES)
        except subprocess.TimeoutExpired:
            return echec(action="construire", cible=self.nom,
                         message=f"La construction a depasse {DELAI_CONSTRUCTION_SECONDES:.0f} s.")
        except OSError as erreur:
            return echec(action="construire", cible=self.nom,
                         message=f"graphify n'a pas pu etre lance : {erreur}")

        if acheve.returncode != 0:
            detail = (acheve.stderr or acheve.stdout or "").strip()[:500]
            return echec(action="construire", cible=self.nom,
                         message=f"La construction a echoue (code {acheve.returncode}) : {detail}")

        stats = _lire_stats_graphe()
        if stats is None:
            return echec(action="construire", cible=self.nom,
                         message="La commande a reussi mais graph.json reste illisible.")

        return succes(
            action="construire", cible=self.nom,
            message=f"Graphe reconstruit : {stats['noeuds']} noeud(s), {stats['liens']} lien(s).",
            preuve=str(GRAPH_JSON), **stats)

    # --- lectures -----------------------------------------------------------

    def _interroger(self, question: str) -> ResultatAction:
        if not question:
            return echec(action="interroger", cible=self.nom,
                         message="Aucune question donnee.")
        if not GRAPH_JSON.exists():
            return non_configure(action="interroger", cible=self.nom,
                                 ce_qui_manque="la capacite « construire », une premiere fois")

        try:
            acheve = self._lancer(
                ["query", question, "--budget", str(BUDGET_REQUETE_JETONS)],
                DELAI_REQUETE_SECONDES)
        except (subprocess.TimeoutExpired, OSError) as erreur:
            return echec(action="interroger", cible=self.nom, message=str(erreur))

        if acheve.returncode != 0:
            detail = (acheve.stderr or acheve.stdout or "").strip()[:500]
            return echec(action="interroger", cible=self.nom, message=detail or "Echec sans detail.")

        reponse = (acheve.stdout or "").strip()
        return succes(action="interroger", cible=self.nom,
                     message=reponse or "Aucun noeud correspondant.", preuve=str(GRAPH_JSON))

    def _chemin(self, depuis: str, vers: str) -> ResultatAction:
        if not depuis or not vers:
            return echec(action="chemin", cible=self.nom,
                         message="Il faut un noeud de depart et un noeud d'arrivee.")
        if not GRAPH_JSON.exists():
            return non_configure(action="chemin", cible=self.nom,
                                 ce_qui_manque="la capacite « construire », une premiere fois")

        try:
            acheve = self._lancer(["path", depuis, vers], DELAI_REQUETE_SECONDES)
        except (subprocess.TimeoutExpired, OSError) as erreur:
            return echec(action="chemin", cible=self.nom, message=str(erreur))

        if acheve.returncode != 0:
            detail = (acheve.stderr or acheve.stdout or "").strip()[:500]
            return echec(action="chemin", cible=self.nom, message=detail or "Echec sans detail.")

        reponse = (acheve.stdout or "").strip()
        return succes(action="chemin", cible=self.nom,
                     message=reponse or f"Aucun chemin entre « {depuis} » et « {vers} ».",
                     preuve=str(GRAPH_JSON))

    def _expliquer(self, noeud: str) -> ResultatAction:
        if not noeud:
            return echec(action="expliquer", cible=self.nom, message="Aucun noeud donne.")
        if not GRAPH_JSON.exists():
            return non_configure(action="expliquer", cible=self.nom,
                                 ce_qui_manque="la capacite « construire », une premiere fois")

        try:
            acheve = self._lancer(["explain", noeud], DELAI_REQUETE_SECONDES)
        except (subprocess.TimeoutExpired, OSError) as erreur:
            return echec(action="expliquer", cible=self.nom, message=str(erreur))

        if acheve.returncode != 0:
            detail = (acheve.stderr or acheve.stdout or "").strip()[:500]
            return echec(action="expliquer", cible=self.nom, message=detail or "Echec sans detail.")

        reponse = (acheve.stdout or "").strip()
        return succes(action="expliquer", cible=self.nom,
                     message=reponse or f"« {noeud} » est introuvable dans le graphe.",
                     preuve=str(GRAPH_JSON))

    def _hubs(self, top: int) -> ResultatAction:
        if not GRAPH_JSON.exists():
            return non_configure(action="hubs", cible=self.nom,
                                 ce_qui_manque="la capacite « construire », une premiere fois")

        try:
            acheve = self._lancer(["god-nodes", "--top", str(max(1, top)), "--json"],
                                  DELAI_REQUETE_SECONDES)
        except (subprocess.TimeoutExpired, OSError) as erreur:
            return echec(action="hubs", cible=self.nom, message=str(erreur))

        if acheve.returncode != 0:
            detail = (acheve.stderr or acheve.stdout or "").strip()[:500]
            return echec(action="hubs", cible=self.nom, message=detail or "Echec sans detail.")

        try:
            noeuds = json.loads(acheve.stdout or "[]")
        except json.JSONDecodeError:
            return echec(action="hubs", cible=self.nom,
                         message="La sortie de god-nodes n'etait pas du JSON valide.")

        resume = ", ".join(f"{n.get('label', '?')} ({n.get('degree', 0)})" for n in noeuds[:top])
        return succes(action="hubs", cible=self.nom,
                     message=resume or "Aucun noeud dans le graphe.",
                     preuve=str(GRAPH_JSON), hubs=noeuds)
