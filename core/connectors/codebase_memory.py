"""Connecteur Codebase Memory MCP — graphe de connaissances structurel et persistant du code.

Codebase-Memory MCP (DeusData, MIT, https://github.com/DeusData/codebase-memory-mcp,
arXiv:2603.27277) est un serveur MCP autonome (binaire natif en C) qui indexe un
dépôt logiciel sous forme de graphe de connaissances SQLite persistant :
fonctions, classes, modules, hiérarchies d'appels (Hybrid LSP) et liaisons
inter-fichiers, analysés via Tree-Sitter sur plus de 158 langages.

Ce que ce connecteur DONNE à ARENA (DEC-0201) :
- Explorer l'architecture d'un projet complexe en sous-millisecondes (`architecture`)
- Tracer les dépendances et chaînes d'appels précises sans relire tout le dépôt (`tracer_chemin`)
- Rechercher des symboles typés (fonctions, classes, routes) (`rechercher_graphe`)
- Mesurer l'impact d'un changement ou diff Git sur l'ensemble du système (`impact_modifications`)
- Réduire jusqu'à 99% la consommation de jetons de contexte pour les agents de code (`RepoEngineerAgent`, `SWEAgent`)
- Interroger le graphe par des requêtes de motifs Cypher (`requete_cypher`)

Ce que ce connecteur N'EST PAS :
- Ce n'est PAS la mémoire personnelle de l'utilisateur (`core/memory/personnelle.py`).
  Les données de code appartiennent strictement au contexte projet/dépôt et ne polluent
  jamais les souvenirs de l'utilisateur.
- Ce n'est PAS un service cloud : 100% local, hors ligne, sans API payante ni envoi distant.
- Ce n'est PAS un second serveur à maintenir en tâche de fond : chaque interaction utilise
  `ClientMcpStdio` dans une session délimitée.

Trois règles fondamentales :

1. **Garde locale et sécurité des chemins** : aucun chemin sensible (.env, .ssh, .gnupg, clés privées)
   ne peut être indexé ou traversé. Les chemins sont vérifiés et résolus avant tout appel sous-processus.
2. **Frontière de confiance** : le contenu des dépôts et les sorties d'outils sont des DONNÉES
   non fiables (niveau EXTERNAL). Ils ne peuvent jamais supplanter les instructions système de l'agent.
3. **Dégradation gracieuse** : si le binaire `codebase-memory-mcp` est absent ou indisponible,
   la sonde retourne NON_CONFIGURE / EN_PANNE sans faire échouer l'agent, qui bascule
   automatiquement sur les outils de repli existants (`gitingest`, `repo_tool`, `swe_aci`).
"""
from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Any, Dict, Optional

from core.actions.resultat import ResultatAction, echec, non_configure, succes
from core.connectors.base import Capacite, Connecteur, EtatSante, Sante, _maintenant
from core.mcp.stdio_transport import ClientMcpStdio, Reponse
from core.security.trust import TrustLevel, wrap

logger = logging.getLogger("usman.connecteurs.codebase_memory")

#: Nom du binaire natif ou chemin configurable
CODEBASE_MEMORY_BIN = (
    os.getenv("USMAN_CODEBASE_MEMORY_BIN", "").strip()
    or os.getenv("CODEBASE_MEMORY_BIN", "").strip()
    or "codebase-memory-mcp"
)

CE_QUI_MANQUE = (
    "Le binaire codebase-memory-mcp est introuvable. "
    "Télécharge le binaire compilé (DeusData/codebase-memory-mcp, licence MIT) "
    "et place-le dans ton PATH (ex: ~/.local/bin/codebase-memory-mcp) "
    "ou configure la variable d'environnement USMAN_CODEBASE_MEMORY_BIN."
)

DUREE_SONDE_SECONDES = 60.0

#: Dossiers et motifs strictement interdits d'exploration pour protéger les secrets
MOTIFS_SENSIBLES = {
    ".env", ".git", ".ssh", ".gnupg", ".aws",
    "id_rsa", "id_ed25519", "id_ecdsa", "id_dsa",
    ".netrc", "credentials", "secrets.json",
}


def _binaire_disponible() -> Optional[str]:
    """Retourne le chemin absolu du binaire s'il est résoluble, sinon None."""
    if os.path.isabs(CODEBASE_MEMORY_BIN) and Path(CODEBASE_MEMORY_BIN).is_file():
        return CODEBASE_MEMORY_BIN
    return shutil.which(CODEBASE_MEMORY_BIN)


def _verifier_chemin_securise(chemin_str: str) -> tuple[bool, str, Optional[Path]]:
    """Valide l'existence et la sécurité d'un chemin de dépôt."""
    if not chemin_str or not chemin_str.strip():
        return False, "Aucun chemin de dépôt fourni.", None

    try:
        p = Path(chemin_str).resolve()
    except Exception as e:
        return False, f"Chemin invalide : {e}", None

    # Vérification des motifs sensibles
    parties = set(p.parts) | {p.name}
    for motif in MOTIFS_SENSIBLES:
        if motif in parties or any(part.startswith(motif) for part in parties):
            return False, f"Accès refusé : le chemin '{chemin_str}' vise une zone sensible protégée.", None

    if not p.exists():
        return False, f"Le chemin spécifié n'existe pas : {p}", None

    return True, "", p


def _erreur_outil(reponse: Reponse) -> Optional[str]:
    return reponse.erreur_applicative


class ConnecteurCodebaseMemory(Connecteur):
    """Connecteur vers le serveur MCP de graphe de code Codebase-Memory."""

    service = "codebase_memory"
    nom = "codebase_memory"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._sante: Optional[Sante] = None
        self._sante_mesuree_a: float = 0.0

    def capacites(self) -> Dict[str, Capacite]:
        return {
            "indexer": Capacite(
                nom="indexer", action="index",
                description="Indexe ou met à jour le graphe de connaissances d'un dépôt de code (AST Tree-Sitter + LSP).",
                ecriture=True),
            "etat_indexation": Capacite(
                nom="etat_indexation", action="read",
                description="Vérifie l'avancement ou l'état de l'indexation d'un projet dans le graphe.",
                ecriture=False),
            "lister_projets": Capacite(
                nom="lister_projets", action="read",
                description="Liste tous les projets indexés avec leurs métriques de nœuds et relations.",
                ecriture=False),
            "supprimer_projet": Capacite(
                nom="supprimer_projet", action="delete",
                description="Supprime l'index et les données de graphe d'un projet.",
                ecriture=True),
            "architecture": Capacite(
                nom="architecture", action="read",
                description="Vue d'ensemble de l'architecture du code (langages, modules, points d'entrée, routes, clusters).",
                ecriture=False),
            "rechercher_graphe": Capacite(
                nom="rechercher_graphe", action="read",
                description="Recherche structurelle de symboles (fonctions, classes, modules) par étiquette ou motif.",
                ecriture=False),
            "tracer_chemin": Capacite(
                nom="tracer_chemin", action="read",
                description="Traverse le graphe d'appels (qui appelle un symbole et ce qu'il appelle).",
                ecriture=False),
            "requete_cypher": Capacite(
                nom="requete_cypher", action="read",
                description="Exécute une requête Cypher en lecture seule sur le graphe de code.",
                ecriture=False),
            "schema_graphe": Capacite(
                nom="schema_graphe", action="read",
                description="Schéma du graphe (types de nœuds, relations, propriétés par étiquette).",
                ecriture=False),
            "extrait_code": Capacite(
                nom="extrait_code", action="read",
                description="Récupère le code source d'une fonction ou d'un symbole identifié par son nom qualifié.",
                ecriture=False),
            "plan_fichier": Capacite(
                nom="plan_fichier", action="read",
                description="Plan des déclarations d'un fichier source dans l'ordre du code.",
                ecriture=False),
            "impact_modifications": Capacite(
                nom="impact_modifications", action="read",
                description="Mappe un diff Git vers les symboles affectés avec analyse de rayon d'impact.",
                ecriture=False),
            "recherche_texte": Capacite(
                nom="recherche_texte", action="read",
                description="Recherche textuelle rapide dans les fichiers indexés du projet.",
                ecriture=False),
        }

    def authentifier(self) -> bool:
        """Vrai : processus local autonome, aucune clé d'API requise."""
        return True

    # --- Sante ------------------------------------------------------------------

    def sonder(self) -> Sante:
        import time
        maintenant = time.monotonic()
        if self._sante is not None and maintenant - self._sante_mesuree_a < DUREE_SONDE_SECONDES:
            return self._sante

        bin_path = _binaire_disponible()
        if not bin_path:
            sante = Sante(
                etat=EtatSante.NON_CONFIGURE,
                message="codebase-memory-mcp n'est pas installé ou introuvable.",
                ce_qui_manque=CE_QUI_MANQUE,
                mesure_le=_maintenant(),
            )
        else:
            try:
                with ClientMcpStdio([bin_path], dossier=".") as client:
                    reponse = client.outils()
                if reponse.ok:
                    outils_recus = {
                        str(t.get("name") or "")
                        for t in (reponse.resultat.get("tools") or [])
                    }
                    nombre = len(outils_recus)
                    sante = Sante(
                        etat=EtatSante.OPERATIONNEL,
                        message=f"codebase-memory-mcp est opérationnel ({nombre} outil(s) MCP disponibles).",
                        mesure_le=_maintenant(),
                    )
                else:
                    sante = Sante(
                        etat=EtatSante.EN_PANNE,
                        message=f"codebase-memory-mcp ne répond pas au protocole MCP : {reponse.raison}",
                        mesure_le=_maintenant(),
                    )
            except Exception as e:
                sante = Sante(
                    etat=EtatSante.EN_PANNE,
                    message=f"Échec d'exécution de codebase-memory-mcp : {e}",
                    mesure_le=_maintenant(),
                )

        self._sante = sante
        self._sante_mesuree_a = maintenant
        return sante

    # --- Execution --------------------------------------------------------------

    def _executer(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        bin_path = _binaire_disponible()
        if not bin_path:
            return non_configure(
                action=capacite.nom,
                cible=self.nom,
                ce_qui_manque=CE_QUI_MANQUE,
            )

        nom = capacite.nom
        if nom == "indexer":
            return self._indexer(bin_path, parametres)
        elif nom == "etat_indexation":
            return self._etat_indexation(bin_path, parametres)
        elif nom == "lister_projets":
            return self._lister_projets(bin_path)
        elif nom == "supprimer_projet":
            return self._supprimer_projet(bin_path, parametres)
        elif nom == "architecture":
            return self._architecture(bin_path, parametres)
        elif nom == "rechercher_graphe":
            return self._rechercher_graphe(bin_path, parametres)
        elif nom == "tracer_chemin":
            return self._tracer_chemin(bin_path, parametres)
        elif nom == "requete_cypher":
            return self._requete_cypher(bin_path, parametres)
        elif nom == "schema_graphe":
            return self._schema_graphe(bin_path, parametres)
        elif nom == "extrait_code":
            return self._extrait_code(bin_path, parametres)
        elif nom == "plan_fichier":
            return self._plan_fichier(bin_path, parametres)
        elif nom == "impact_modifications":
            return self._impact_modifications(bin_path, parametres)
        elif nom == "recherche_texte":
            return self._recherche_texte(bin_path, parametres)

        return echec(
            action=capacite.nom,
            cible=self.nom,
            message=f"Capacité '{capacite.nom}' non implémentée.",
        )

    # --- Actions spécifiques ----------------------------------------------------

    def _indexer(self, bin_path: str, params: Dict[str, Any]) -> ResultatAction:
        chemin_brut = str(params.get("chemin") or params.get("repo_path") or ".").strip()
        ok, raison, p = _verifier_chemin_securise(chemin_brut)
        if not ok or p is None:
            return echec(action="indexer", cible=self.nom, message=raison)
        if not p.is_dir():
            return echec(action="indexer", cible=self.nom, message=f"Le chemin à indexer doit être un répertoire : {p}")

        chemin_abs = str(p)
        args: Dict[str, Any] = {"repo_path": chemin_abs}
        if params.get("force"):
            args["force"] = True
        projet = str(params.get("projet") or params.get("project") or "").strip()
        if projet:
            args["project"] = projet

        with ClientMcpStdio([bin_path], dossier=chemin_abs) as client:
            reponse = client.appeler("index_repository", args)
            # Repli sur "path" si le serveur attend "path"
            if not reponse.ok and "repo_path" in reponse.raison:
                args.pop("repo_path", None)
                args["path"] = chemin_abs
                reponse = client.appeler("index_repository", args)

        err = _erreur_outil(reponse)
        if not reponse.ok or err:
            return echec(action="indexer", cible=self.nom, message=f"Indexation échouée : {err or reponse.raison}")

        donnees = reponse.donnees()
        return succes(
            action="indexer",
            cible=self.nom,
            message=f"Dépôt indexé avec succès dans le graphe de connaissances : {chemin_abs}",
            preuve=chemin_abs,
            donnees=donnees,
        )

    def _etat_indexation(self, bin_path: str, params: Dict[str, Any]) -> ResultatAction:
        chemin_brut = str(params.get("chemin") or params.get("repo_path") or "").strip()
        projet = str(params.get("projet") or params.get("project") or "").strip()
        args: Dict[str, Any] = {}
        dossier_exec = "."

        if chemin_brut:
            ok, raison, p = _verifier_chemin_securise(chemin_brut)
            if not ok or p is None:
                return echec(action="etat_indexation", cible=self.nom, message=raison)
            args["repo_path"] = str(p)
            dossier_exec = str(p)
        if projet:
            args["project"] = projet

        with ClientMcpStdio([bin_path], dossier=dossier_exec) as client:
            reponse = client.appeler("index_status", args)

        err = _erreur_outil(reponse)
        if not reponse.ok or err:
            return echec(action="etat_indexation", cible=self.nom, message=f"Statut d'indexation introuvable : {err or reponse.raison}")

        donnees = reponse.donnees()
        preuve_str = projet or chemin_brut or "index_status"
        return succes(
            action="etat_indexation",
            cible=self.nom,
            message=f"État d'indexation : {donnees}",
            preuve=preuve_str,
            donnees=donnees,
        )

    def _lister_projets(self, bin_path: str) -> ResultatAction:
        with ClientMcpStdio([bin_path], dossier=".") as client:
            reponse = client.appeler("list_projects", {})

        err = _erreur_outil(reponse)
        if not reponse.ok or err:
            return echec(action="lister_projets", cible=self.nom, message=f"Liste des projets inaccessible : {err or reponse.raison}")

        donnees = reponse.donnees()
        return succes(
            action="lister_projets",
            cible=self.nom,
            message="Projets indexés récupérés.",
            preuve="list_projects",
            projets=donnees,
            donnees=donnees,
        )

    def _supprimer_projet(self, bin_path: str, params: Dict[str, Any]) -> ResultatAction:
        projet = str(params.get("projet") or params.get("project") or "").strip()
        chemin_brut = str(params.get("chemin") or params.get("repo_path") or "").strip()
        args: Dict[str, Any] = {}

        if projet:
            args["project"] = projet
        if chemin_brut:
            ok, raison, p = _verifier_chemin_securise(chemin_brut)
            if not ok or p is None:
                return echec(action="supprimer_projet", cible=self.nom, message=raison)
            args["repo_path"] = str(p)

        if not args:
            return echec(action="supprimer_projet", cible=self.nom, message="Il faut préciser le nom du projet ou le chemin à supprimer.")

        with ClientMcpStdio([bin_path], dossier=".") as client:
            reponse = client.appeler("delete_project", args)

        err = _erreur_outil(reponse)
        if not reponse.ok or err:
            return echec(action="supprimer_projet", cible=self.nom, message=f"Suppression échouée : {err or reponse.raison}")

        cible_nom = projet or chemin_brut
        return succes(
            action="supprimer_projet",
            cible=self.nom,
            message=f"Index de projet supprimé avec succès ({cible_nom}).",
            preuve=cible_nom,
            cible_supprimee=cible_nom,
        )

    def _architecture(self, bin_path: str, params: Dict[str, Any]) -> ResultatAction:
        projet = str(params.get("projet") or params.get("project") or "").strip()
        chemin_brut = str(params.get("chemin") or params.get("repo_path") or ".").strip()
        dossier_exec = "."
        args: Dict[str, Any] = {}

        if chemin_brut:
            ok, raison, p = _verifier_chemin_securise(chemin_brut)
            if ok and p is not None:
                args["repo_path"] = str(p)
                dossier_exec = str(p)
        if projet:
            args["project"] = projet

        with ClientMcpStdio([bin_path], dossier=dossier_exec) as client:
            reponse = client.appeler("get_architecture", args)

        err = _erreur_outil(reponse)
        if not reponse.ok or err:
            return echec(action="architecture", cible=self.nom, message=f"Analyse d'architecture impossible : {err or reponse.raison}")

        donnees = reponse.donnees()
        texte_brut = reponse.contenu_texte or str(donnees)
        enveloppe = wrap(texte_brut, TrustLevel.EXTERNAL, origin="codebase_memory:architecture")
        preuve_str = projet or chemin_brut or "architecture"

        return succes(
            action="architecture",
            cible=self.nom,
            message=enveloppe.text,
            preuve=preuve_str,
            architecture=donnees,
            donnees=donnees,
        )

    def _rechercher_graphe(self, bin_path: str, params: Dict[str, Any]) -> ResultatAction:
        args: Dict[str, Any] = {}
        for cle_fr, cle_en in [
            ("motif_nom", "name_pattern"),
            ("etiquette", "label"),
            ("motif_fichier", "file_pattern"),
            ("projet", "project"),
            ("limite", "limit"),
            ("offset", "offset"),
        ]:
            val = params.get(cle_fr) if cle_fr in params else params.get(cle_en)
            if val is not None and str(val).strip() != "":
                args[cle_en] = val

        with ClientMcpStdio([bin_path], dossier=".") as client:
            reponse = client.appeler("search_graph", args)

        err = _erreur_outil(reponse)
        if not reponse.ok or err:
            return echec(action="rechercher_graphe", cible=self.nom, message=f"Recherche dans le graphe échouée : {err or reponse.raison}")

        donnees = reponse.donnees()
        texte_brut = reponse.contenu_texte or str(donnees)
        enveloppe = wrap(texte_brut, TrustLevel.EXTERNAL, origin="codebase_memory:search_graph")
        preuve_str = str(args.get("name_pattern") or args.get("label") or args.get("file_pattern") or "search_graph")

        return succes(
            action="rechercher_graphe",
            cible=self.nom,
            message=enveloppe.text,
            preuve=preuve_str,
            resultats=donnees,
            donnees=donnees,
        )

    def _tracer_chemin(self, bin_path: str, params: Dict[str, Any]) -> ResultatAction:
        fonction = str(params.get("fonction") or params.get("function_name") or "").strip()
        if not fonction:
            return echec(action="tracer_chemin", cible=self.nom, message="Il faut spécifier un nom de fonction ou symbole à tracer.")

        args: Dict[str, Any] = {"function_name": fonction}
        projet = str(params.get("projet") or params.get("project") or "").strip()
        if projet:
            args["project"] = projet
        direction = str(params.get("direction") or "both").strip().lower()
        if direction in ("inbound", "outbound", "both"):
            args["direction"] = direction
        profondeur = params.get("profondeur") or params.get("depth")
        if profondeur is not None:
            try:
                args["depth"] = max(1, min(5, int(profondeur)))
            except (ValueError, TypeError) as err:
                logger.debug("codebase_memory: profondeur ignorée (non convertible en entier) : %s", err)

        with ClientMcpStdio([bin_path], dossier=".") as client:
            # Essaye trace_path puis repli sur trace_call_path
            reponse = client.appeler("trace_path", args)
            if not reponse.ok and "trace_path" in reponse.raison:
                reponse = client.appeler("trace_call_path", args)

        err = _erreur_outil(reponse)
        if not reponse.ok or err:
            return echec(action="tracer_chemin", cible=self.nom, message=f"Tracé d'appels impossible : {err or reponse.raison}")

        donnees = reponse.donnees()
        texte_brut = reponse.contenu_texte or str(donnees)
        enveloppe = wrap(texte_brut, TrustLevel.EXTERNAL, origin=f"codebase_memory:trace_path({fonction})")

        return succes(
            action="tracer_chemin",
            cible=self.nom,
            message=enveloppe.text,
            preuve=fonction,
            trace=donnees,
            donnees=donnees,
            fonction=fonction,
        )

    def _requete_cypher(self, bin_path: str, params: Dict[str, Any]) -> ResultatAction:
        requete = str(params.get("requete") or params.get("query") or "").strip()
        if not requete:
            return echec(action="requete_cypher", cible=self.nom, message="Aucune requête Cypher fournie.")

        args: Dict[str, Any] = {"query": requete}
        projet = str(params.get("projet") or params.get("project") or "").strip()
        if projet:
            args["project"] = projet

        with ClientMcpStdio([bin_path], dossier=".") as client:
            reponse = client.appeler("query_graph", args)

        err = _erreur_outil(reponse)
        if not reponse.ok or err:
            return echec(action="requete_cypher", cible=self.nom, message=f"Exécution Cypher échouée : {err or reponse.raison}")

        donnees = reponse.donnees()
        return succes(
            action="requete_cypher",
            cible=self.nom,
            message="Requête exécutée avec succès.",
            preuve=requete,
            resultats=donnees,
            donnees=donnees,
            requete=requete,
        )

    def _schema_graphe(self, bin_path: str, params: Dict[str, Any]) -> ResultatAction:
        args: Dict[str, Any] = {}
        projet = str(params.get("projet") or params.get("project") or "").strip()
        if projet:
            args["project"] = projet

        with ClientMcpStdio([bin_path], dossier=".") as client:
            reponse = client.appeler("get_graph_schema", args)

        err = _erreur_outil(reponse)
        if not reponse.ok or err:
            return echec(action="schema_graphe", cible=self.nom, message=f"Récupération du schéma échouée : {err or reponse.raison}")

        donnees = reponse.donnees()
        return succes(
            action="schema_graphe",
            cible=self.nom,
            message="Schéma du graphe récupéré.",
            preuve=projet or "schema",
            schema=donnees,
            donnees=donnees,
        )

    def _extrait_code(self, bin_path: str, params: Dict[str, Any]) -> ResultatAction:
        symbole = str(params.get("nom_qualifie") or params.get("function_name") or params.get("name") or "").strip()
        fichier = str(params.get("chemin_fichier") or params.get("file_path") or "").strip()
        if not symbole and not fichier:
            return echec(action="extrait_code", cible=self.nom, message="Il faut spécifier un nom de symbole ou un chemin de fichier.")

        args: Dict[str, Any] = {}
        if symbole:
            args["function_name"] = symbole
        if fichier:
            args["file_path"] = fichier
        projet = str(params.get("projet") or params.get("project") or "").strip()
        if projet:
            args["project"] = projet

        with ClientMcpStdio([bin_path], dossier=".") as client:
            reponse = client.appeler("get_code_snippet", args)

        err = _erreur_outil(reponse)
        if not reponse.ok or err:
            return echec(action="extrait_code", cible=self.nom, message=f"Extrait de code introuvable : {err or reponse.raison}")

        donnees = reponse.donnees()
        texte_brut = reponse.contenu_texte or str(donnees)
        enveloppe = wrap(texte_brut, TrustLevel.EXTERNAL, origin=f"codebase_memory:snippet({symbole or fichier})")
        preuve_str = symbole or fichier

        return succes(
            action="extrait_code",
            cible=self.nom,
            message=enveloppe.text,
            preuve=preuve_str,
            extrait=donnees,
            donnees=donnees,
        )

    def _plan_fichier(self, bin_path: str, params: Dict[str, Any]) -> ResultatAction:
        fichier = str(params.get("chemin_fichier") or params.get("file_path") or "").strip()
        if not fichier:
            return echec(action="plan_fichier", cible=self.nom, message="Il faut spécifier un chemin de fichier relatif.")

        args: Dict[str, Any] = {"file_path": fichier}
        projet = str(params.get("projet") or params.get("project") or "").strip()
        if projet:
            args["project"] = projet

        with ClientMcpStdio([bin_path], dossier=".") as client:
            reponse = client.appeler("get_file_outline", args)

        err = _erreur_outil(reponse)
        if not reponse.ok or err:
            return echec(action="plan_fichier", cible=self.nom, message=f"Plan de fichier inaccessible : {err or reponse.raison}")

        donnees = reponse.donnees()
        texte_brut = reponse.contenu_texte or str(donnees)
        enveloppe = wrap(texte_brut, TrustLevel.EXTERNAL, origin=f"codebase_memory:outline({fichier})")

        return succes(
            action="plan_fichier",
            cible=self.nom,
            message=enveloppe.text,
            preuve=fichier,
            plan=donnees,
            donnees=donnees,
        )

    def _impact_modifications(self, bin_path: str, params: Dict[str, Any]) -> ResultatAction:
        chemin_brut = str(params.get("chemin") or params.get("repo_path") or ".").strip()
        diff = params.get("diff")
        projet = str(params.get("projet") or params.get("project") or "").strip()
        args: Dict[str, Any] = {}
        dossier_exec = "."

        if chemin_brut:
            ok, raison, p = _verifier_chemin_securise(chemin_brut)
            if ok and p is not None:
                args["repo_path"] = str(p)
                dossier_exec = str(p)
        if diff:
            args["diff"] = str(diff)
        if projet:
            args["project"] = projet

        with ClientMcpStdio([bin_path], dossier=dossier_exec) as client:
            reponse = client.appeler("detect_changes", args)

        err = _erreur_outil(reponse)
        if not reponse.ok or err:
            return echec(action="impact_modifications", cible=self.nom, message=f"Détection d'impact impossible : {err or reponse.raison}")

        donnees = reponse.donnees()
        texte_brut = reponse.contenu_texte or str(donnees)
        enveloppe = wrap(texte_brut, TrustLevel.EXTERNAL, origin="codebase_memory:detect_changes")
        preuve_str = projet or chemin_brut or "detect_changes"

        return succes(
            action="impact_modifications",
            cible=self.nom,
            message=enveloppe.text,
            preuve=preuve_str,
            impact=donnees,
            donnees=donnees,
        )

    def _recherche_texte(self, bin_path: str, params: Dict[str, Any]) -> ResultatAction:
        requete = str(params.get("requete") or params.get("query") or "").strip()
        if not requete:
            return echec(action="recherche_texte", cible=self.nom, message="Aucune requête de recherche fournie.")

        args: Dict[str, Any] = {"query": requete}
        projet = str(params.get("projet") or params.get("project") or "").strip()
        if projet:
            args["project"] = projet
        motif_fichier = str(params.get("motif_fichier") or params.get("file_pattern") or "").strip()
        if motif_fichier:
            args["file_pattern"] = motif_fichier

        with ClientMcpStdio([bin_path], dossier=".") as client:
            reponse = client.appeler("search_code", args)

        err = _erreur_outil(reponse)
        if not reponse.ok or err:
            return echec(action="recherche_texte", cible=self.nom, message=f"Recherche de texte échouée : {err or reponse.raison}")

        donnees = reponse.donnees()
        texte_brut = reponse.contenu_texte or str(donnees)
        enveloppe = wrap(texte_brut, TrustLevel.EXTERNAL, origin="codebase_memory:search_code")

        return succes(
            action="recherche_texte",
            cible=self.nom,
            message=enveloppe.text,
            preuve=requete,
            resultats=donnees,
            donnees=donnees,
            requete=requete,
        )
