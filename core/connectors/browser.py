"""Connecteur Browser — navigation Web autonome, avec Lightpanda comme
moteur optionnel plus léger derrière le moteur existant, jamais un second
agent de navigation.

**Ce qui existait déjà, vérifié avant d'écrire une ligne** (mission
« intégration Lightpanda », 06/09/2026) : `agents/browser/browser_agent.py`
(`BrowserAgent`, intention `BROWSER` de l'orchestrateur, câblée dans
`apps/backend/routers/chat.py`) pilote déjà `tools/browser/
browser_use_tool.py::BrowserUseTool` — `browser-use==0.13.10` (autonome,
pilote Playwright) + `playwright==1.62.0` (Chromium local), installés
depuis le 04/09/2026. C'est un navigateur COMPLET, avec JavaScript, clics,
formulaires — pas une absence à combler.

**Le vrai défaut trouvé pendant l'audit** : `BrowserAgent` appelait
`BrowserUseTool` en direct, **hors du registre et des permissions**
(`ControleAcces`/`config/permissions_services.yaml`) — la seule capacité
d'ARENA qui agit sur le web de façon autonome (clics, formulaires) sans
passer par le même contrôle d'accès que WanGP ou KrillinAI. Ce
connecteur corrige ce défaut : `agents/browser/browser_agent.py` appelle
désormais `registre.executer("browser", "naviguer", ...)`, comme
`VisionAgent` le fait déjà pour `securite_chantier`.

**Lightpanda (AGPLv3, `lightpanda-io/browser`), vérifié en clonant le
dépôt réel** — `LICENSE` et `LICENSING.md` lus directement : AGPL-3.0-only,
sans exception ni double licence. Écrit en Zig, moteur JS V8, jamais un
fork de Chromium — donc rien à importer même si la licence le permettait :
la bonne frontière est réseau, comme toujours pour un composant AGPL/GPL
dans ce dépôt (VoiceStudio, KrillinAI, SiteGuard, OpenViking). Son
propre serveur CDP (`lightpanda serve --port 9222`) est **exactement** ce
que Puppeteer/Playwright — et donc `browser_use` — savent déjà rejoindre :
`browser_use.browser.session.BrowserSession(cdp_url=...)`, vérifié dans le
code INSTALLÉ ici (`browser-use==0.13.10`), jamais deviné depuis sa
documentation. Statut du projet, dit par lui-même : « Beta [...] you may
still encounter errors or crashes » — d'où un **repli automatique** vers
le moteur existant sur tout échec, jamais un remplacement.

**Une seule capacité logique, un seul contrat** (mission : « PAS DE DEUX
NAVIGATEURS UTILISÉS INDIFFÉREMMENT PAR DES AGENTS DIFFÉRENTS ») : l'agent
demande `naviguer`, jamais un moteur par son nom. Le connecteur choisit :

1. **Lightpanda configuré et sain** (`LIGHTPANDA_CDP_URL` réglé, `GET
   {url}/json/version` répond — endpoint vérifié dans le code SOURCE de
   Lightpanda, `src/server/http.zig::serveJSONVersion`, avec son propre
   test unitaire `"server: get /json/version"`) : tenté en premier.
2. **Échec Lightpanda, à tout moment** (non sain, ou l'appel lève) :
   repli silencieux sur le moteur existant (Chromium local via
   Playwright) — jamais un échec transmis à l'appelant tant que le moteur
   existant peut répondre.
3. **Lightpanda non configuré** : le moteur existant est utilisé
   directement, comportement IDENTIQUE à avant ce connecteur.

Aucune URL par défaut pour Lightpanda (DEC-0002) : `LIGHTPANDA_CDP_URL`
absent, aucune tentative de s'y connecter n'a jamais lieu.

**Sécurité** (mission §« sécurité ») : `naviguer` est déclarée `ecriture=
True` (des clics/formulaires modifient un état externe) et passe par le
même contrôle de permission que toute autre capacité — `ALLOWED` sous
l'interrupteur `SEARCH_WEB` par défaut (voir `config/permissions_services.
yaml` pour le raisonnement), jamais un second système. Le propriétaire
peut la resserrer en `CONFIRMATION` par simple configuration, sans toucher
au code — comme toute règle de ce fichier.
"""
import asyncio
import logging
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from enum import Enum
from typing import Any, Dict, List, Optional

import httpx

from core.actions.resultat import ResultatAction, echec, partiel, succes
from core.connectors.base import Capacite, Connecteur, EtatSante, Sante, _maintenant
from tools.browser.browser_use_tool import MAX_ETAPES_DEFAUT, BrowserUseTool

logger = logging.getLogger("usman.connecteurs.browser")


class ResultatNavigation(str, Enum):
    """Classification DETERMINISTE d'une tâche de navigation — jamais un
    simple `status: success` pris sur parole (mission Fuji-Web §7 : « must
    not be considered successful merely because the click API returned
    success »). Quatre issues, jamais deux :

    - `succes_declare` vient de `browser_use` lui-même (l'agent a appelé
      son action `done` avec `success=True/False`) — c'est encore un
      AUTO-rapport, pas une vérification indépendante d'ARENA.
    - `a_des_erreurs` et `nombre_etapes`/`max_etapes` viennent de
      l'historique réel de la bibliothèque — des faits, pas une opinion.

    Un succès déclaré MALGRÉ des erreurs rencontrées en route devient
    `NON_VERIFIE`, jamais un succès plein : les deux signaux se
    contredisent, et masquer la contradiction serait exactement l'erreur
    que ce module corrige.
    """

    VERIFIE = "VERIFIED_SUCCESS"
    NON_VERIFIE = "UNVERIFIED_SUCCESS"
    ECHEC = "FAILED"
    INCOMPLET = "INCOMPLETE"


def classer_resultat(
    succes_declare: Optional[bool], a_des_erreurs: bool, nombre_etapes: int, max_etapes: int,
) -> ResultatNavigation:
    """Le seul endroit qui décide si une navigation a « réussi ». Pure,
    testable sans navigateur : voir `tests/core/test_connecteur_browser.py`."""
    if succes_declare is True:
        return ResultatNavigation.NON_VERIFIE if a_des_erreurs else ResultatNavigation.VERIFIE
    if succes_declare is False:
        return ResultatNavigation.ECHEC
    # `None` : l'agent n'a jamais appelé `done` — soit le plafond de pas a
    # été atteint (mission §8, MAX_STEPS), soit un arrêt anormal que
    # l'appelant a déjà filtré avant d'arriver ici.
    return ResultatNavigation.INCOMPLET

#: Une navigation autonome peut enchaîner plusieurs pages et attentes
#: réseau — plus généreux qu'un simple appel HTTP, jamais illimité.
DELAI_SECONDES = 120.0
#: La sonde Lightpanda doit répondre vite : sinon, ce n'est pas la peine
#: d'attendre avant de basculer sur le moteur existant.
DELAI_SONDE_LIGHTPANDA = 2.0
#: `playwright install --dry-run` ne télécharge rien et ne lance aucun
#: navigateur : mesuré à 0,4 s. La borne protège d'un environnement Python
#: cassé, elle n'est pas un budget d'attente normal.
DELAI_SONDE_NAVIGATEUR = 15.0

CE_QUI_MANQUE = (
    "browser-use/Playwright ne sont pas installés : "
    "pip install browser-use playwright langchain-openai, "
    "puis playwright install chromium."
)


def _verifier_moteur_de_base() -> Optional[str]:
    """`None` si browser-use + langchain-openai sont importables **et** qu'un
    navigateur est réellement installé, sinon le message d'erreur.

    Séparée de `sonder()` pour que les tests substituent la disponibilité du
    moteur sans installer le vrai paquet : la CI hors ligne
    (`.github/workflows/ci.yml`) n'installe jamais browser-use/Playwright —
    volontairement, comme tout paquet lourd testé par un connecteur plutôt que
    par lui-même — donc seul le ROUTAGE de ce connecteur doit dépendre de sa
    présence, jamais ses propres tests."""
    try:
        import browser_use  # noqa: F401
        import langchain_openai  # noqa: F401
    except ImportError as erreur:
        return str(erreur)
    return _verifier_navigateur_installe()


def _verifier_navigateur_installe() -> Optional[str]:
    """`None` si un navigateur existe là où Playwright le cherche.

    **Défaut mesuré le 07/09/2026**, sur demande de vérification du
    propriétaire. La sonde ne testait que l'import de deux paquets Python et
    annonçait « Navigation autonome disponible (Chromium local) » — prouvé en
    pointant `PLAYWRIGHT_BROWSERS_PATH` sur un dossier vide : la sonde disait
    encore `OPERATIONAL`. Or `pip install playwright` **n'installe aucun
    navigateur** : `playwright install chromium` est une seconde étape, et
    c'est précisément celle qu'on oublie. La capacité s'annonçait donc
    disponible pour échouer au premier usage réel.

    L'emplacement n'est jamais DEVINÉ : il est demandé à Playwright
    (`playwright install --dry-run`), qui applique ses propres règles
    (`PLAYWRIGHT_BROWSERS_PATH`, défauts par système d'exploitation).
    Réimplémenter cette résolution ici reviendrait à supposer — et elle
    diffère entre Linux, macOS et le Windows du propriétaire.
    """
    try:
        sortie = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "--dry-run", "chromium"],
            capture_output=True, text=True, timeout=DELAI_SONDE_NAVIGATEUR)
    except (OSError, subprocess.SubprocessError) as erreur:
        return f"playwright n'a pas répondu : {erreur}"

    if sortie.returncode != 0:
        detail = (sortie.stderr or sortie.stdout or "").strip()
        return f"playwright install --dry-run a échoué : {detail[:200]}"

    emplacements = re.findall(r"Install location:\s*(.+)", sortie.stdout)
    if not emplacements:
        return "playwright n'annonce aucun emplacement d'installation."

    # La PREMIÈRE ligne est celle du navigateur demandé ; les suivantes sont
    # ses compagnons (ffmpeg, headless shell), dont l'absence n'empêche pas
    # de naviguer.
    navigateur = emplacements[0].strip()
    if not os.path.isdir(navigateur):
        return (f"aucun navigateur dans {navigateur} : "
                "« playwright install chromium » n'a jamais été lancé.")
    return None


def _lightpanda_url() -> str:
    """Aucune adresse par défaut (DEC-0002) : lu à l'appel, jamais au
    chargement du module, pour que les tests le fixent par variable
    d'environnement."""
    return os.getenv("LIGHTPANDA_CDP_URL", "").strip()


def _lightpanda_sain(url: str) -> bool:
    """Vrai si Lightpanda répond RÉELLEMENT — jamais supposé d'une simple
    présence de configuration. `/json/version` est un vrai endpoint HTTP
    de son serveur CDP, vérifié dans son code source
    (`src/server/http.zig::serveJSONVersion`), pas deviné depuis sa doc."""
    base_http = url.replace("wss://", "https://").replace("ws://", "http://").rstrip("/")
    try:
        with httpx.Client(timeout=DELAI_SONDE_LIGHTPANDA) as client:
            reponse = client.get(f"{base_http}/json/version")
        return reponse.status_code == 200
    except httpx.HTTPError as erreur:
        logger.info("Lightpanda injoignable (%s) : %s", url, erreur)
        return False


class ConnecteurBrowser(Connecteur):
    """Navigation Web autonome — un seul contrat, deux moteurs possibles."""

    service = "browser"
    nom = "browser"

    def __init__(self, outil: Optional[BrowserUseTool] = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._outil = outil or BrowserUseTool()
        self._sante: Optional[Sante] = None
        self._sante_mesuree_a: float = 0.0

    def capacites(self) -> Dict[str, Capacite]:
        return {
            "naviguer": Capacite(
                nom="naviguer", action="browse",
                description=(
                    "Navigue de façon autonome (clics, formulaires, extraction) sur un "
                    "site web, avec le meilleur moteur disponible. Parametres optionnels : "
                    "max_steps (plafond de pas, defaut 25), fichiers_autorises (envoi de "
                    "fichier — liste fermee, jamais une recherche libre), sensitive_data + "
                    "allowed_domains (identifiants — les deux ensemble ou aucun des deux)."),
                ecriture=True),
        }

    def authentifier(self) -> bool:
        """Vrai : un processus/navigateur local, aucun identifiant à présenter."""
        return True

    def sonder(self) -> Sante:
        """Mesure le moteur DE BASE (browser-use + Playwright) — jamais
        Lightpanda, optionnel et vérifié fraîchement à chaque appel
        (`_lightpanda_sain`) : son absence ne rend jamais cette capacité
        indisponible, seulement moins rapide."""
        maintenant = time.monotonic()
        if self._sante is not None and maintenant - self._sante_mesuree_a < 60.0:
            return self._sante

        erreur = _verifier_moteur_de_base()
        if erreur is not None:
            sante = Sante(etat=EtatSante.NON_CONFIGURE,
                         message=f"browser-use non installé : {erreur}",
                         ce_qui_manque=CE_QUI_MANQUE, mesure_le=_maintenant())
        else:
            sante = Sante(etat=EtatSante.OPERATIONNEL,
                         message="Navigation autonome disponible (Chromium local, Lightpanda si configuré).",
                         mesure_le=_maintenant())

        self._sante = sante
        self._sante_mesuree_a = maintenant
        return sante

    # --- Execution --------------------------------------------------------------

    def _executer(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        tache = str(parametres.get("tache") or "").strip()
        if not tache:
            return echec(action=capacite.nom, cible=self.nom,
                         message="Aucune tâche fournie : rien à faire.")

        max_steps = parametres.get("max_steps") or MAX_ETAPES_DEFAUT
        sensitive_data = parametres.get("sensitive_data")
        allowed_domains = parametres.get("allowed_domains")
        fichiers_autorises = parametres.get("fichiers_autorises")

        url_lightpanda = _lightpanda_url()
        tente_lightpanda = bool(url_lightpanda) and _lightpanda_sain(url_lightpanda)

        if tente_lightpanda:
            resultat = self._lancer(tache, cdp_url=url_lightpanda, max_steps=max_steps,
                                    sensitive_data=sensitive_data, allowed_domains=allowed_domains,
                                    fichiers_autorises=fichiers_autorises)
            if resultat.get("status") == "success":
                return self._resultat_action(capacite, resultat, repli=False)
            logger.warning("Lightpanda a échoué (%s) : repli sur le moteur existant.",
                          resultat.get("error"))

        resultat = self._lancer(tache, cdp_url=None, max_steps=max_steps,
                                sensitive_data=sensitive_data, allowed_domains=allowed_domains,
                                fichiers_autorises=fichiers_autorises)
        if resultat.get("status") != "success":
            return echec(
                action=capacite.nom, cible=self.nom,
                message=f"Navigation impossible : {resultat.get('error') or 'erreur inconnue'}",
                moteur=resultat.get("moteur"), etapes=resultat.get("etapes") or [])

        return self._resultat_action(capacite, resultat, repli=tente_lightpanda)

    def _resultat_action(
        self, capacite: Capacite, resultat: Dict[str, Any], repli: bool,
    ) -> ResultatAction:
        """Classe le resultat (`classer_resultat`) et le transpose en
        `ResultatAction` — jamais un succes qui ne fait que reprendre le
        statut auto-declare de `browser_use`."""
        classification = classer_resultat(
            succes_declare=resultat.get("succes_declare"),
            a_des_erreurs=bool(resultat.get("erreurs")),
            nombre_etapes=resultat.get("nombre_etapes") or 0,
            max_etapes=resultat.get("max_etapes") or MAX_ETAPES_DEFAUT,
        )
        preuve = str(resultat.get("result") or "réponse vide")[:500]
        detail: Dict[str, Any] = dict(
            moteur=resultat.get("moteur"), resultat=resultat.get("result"), repli=repli,
            verification=classification.value, nombre_etapes=resultat.get("nombre_etapes"),
            urls_visitees=resultat.get("urls_visitees") or [],
            erreurs=resultat.get("erreurs") or [], etapes=resultat.get("etapes") or [],
            duree_secondes=resultat.get("duree_secondes"),
        )

        if classification is ResultatNavigation.VERIFIE:
            return succes(action=capacite.nom, cible=self.nom,
                         message=self._resume(resultat), preuve=preuve, **detail)
        if classification is ResultatNavigation.NON_VERIFIE:
            return partiel(
                action=capacite.nom, cible=self.nom,
                message=f"{self._resume(resultat)} (succès déclaré, mais des erreurs sont survenues en route — "
                        f"non vérifié).",
                preuve=preuve, **detail)
        # ECHEC ou INCOMPLET : rien n'est prouvé, jamais deguise en succes.
        return echec(
            action=capacite.nom, cible=self.nom,
            message=(f"Navigation non aboutie ({classification.value}) : "
                    f"{resultat.get('result') or 'aucun résultat'}"),
            **detail)

    def _lancer(
        self, tache: str, cdp_url: Optional[str], *, max_steps: int,
        sensitive_data: Optional[Dict[str, Any]], allowed_domains: Optional[List[str]],
        fichiers_autorises: Optional[List[str]],
    ) -> Dict[str, Any]:
        """Exécute `BrowserUseTool.run_task` (une coroutine) depuis `_executer`,
        qui ne l'est pas — même pont par thread que GitIngest (DEC-0047) :
        `asyncio.run()` ici léverait sur une boucle déjà active (routes
        FastAPI, agents `async def`)."""
        def _dans_son_propre_fil() -> Dict[str, Any]:
            return asyncio.run(asyncio.wait_for(
                self._outil.run_task(
                    tache, cdp_url=cdp_url, max_steps=max_steps, sensitive_data=sensitive_data,
                    allowed_domains=allowed_domains, available_file_paths=fichiers_autorises,
                ), timeout=DELAI_SECONDES))

        try:
            with ThreadPoolExecutor(max_workers=1) as bassin:
                return bassin.submit(_dans_son_propre_fil).result(timeout=DELAI_SECONDES + 5)
        except (asyncio.TimeoutError, TimeoutError):
            return {"status": "error", "error": f"délai de {DELAI_SECONDES:.0f}s dépassé",
                    "moteur": "lightpanda" if cdp_url else "chromium"}

    @staticmethod
    def _resume(resultat: Dict[str, Any]) -> str:
        nom_moteur = {"lightpanda": "Lightpanda", "chromium": "Chromium (Playwright)"}.get(
            resultat.get("moteur"), str(resultat.get("moteur")))
        return f"Navigation terminée ({nom_moteur}) : {resultat.get('result') or ''}"
