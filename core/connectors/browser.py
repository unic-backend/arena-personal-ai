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
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Optional

import httpx

from core.actions.resultat import ResultatAction, echec, succes
from core.connectors.base import Capacite, Connecteur, EtatSante, Sante, _maintenant
from tools.browser.browser_use_tool import BrowserUseTool

logger = logging.getLogger("usman.connecteurs.browser")

#: Une navigation autonome peut enchaîner plusieurs pages et attentes
#: réseau — plus généreux qu'un simple appel HTTP, jamais illimité.
DELAI_SECONDES = 120.0
#: La sonde Lightpanda doit répondre vite : sinon, ce n'est pas la peine
#: d'attendre avant de basculer sur le moteur existant.
DELAI_SONDE_LIGHTPANDA = 2.0

CE_QUI_MANQUE = (
    "browser-use/Playwright ne sont pas installés : "
    "pip install browser-use playwright langchain-openai, "
    "puis playwright install chromium."
)


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
                    "site web, avec le meilleur moteur disponible."),
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

        try:
            import browser_use  # noqa: F401
            import langchain_openai  # noqa: F401
        except ImportError as erreur:
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

        url_lightpanda = _lightpanda_url()
        tente_lightpanda = bool(url_lightpanda) and _lightpanda_sain(url_lightpanda)

        if tente_lightpanda:
            resultat = self._lancer(tache, cdp_url=url_lightpanda)
            if resultat.get("status") == "success":
                return succes(
                    action=capacite.nom, cible=self.nom,
                    message=self._resume(resultat), preuve=str(resultat.get("result") or "réponse vide")[:500],
                    moteur=resultat.get("moteur"), resultat=resultat.get("result"), repli=False)
            logger.warning("Lightpanda a échoué (%s) : repli sur le moteur existant.",
                          resultat.get("error"))

        resultat = self._lancer(tache, cdp_url=None)
        if resultat.get("status") != "success":
            return echec(
                action=capacite.nom, cible=self.nom,
                message=f"Navigation impossible : {resultat.get('error') or 'erreur inconnue'}",
                moteur=resultat.get("moteur"))

        return succes(
            action=capacite.nom, cible=self.nom,
            message=self._resume(resultat), preuve=str(resultat.get("result") or "réponse vide")[:500],
            moteur=resultat.get("moteur"), resultat=resultat.get("result"), repli=tente_lightpanda)

    def _lancer(self, tache: str, cdp_url: Optional[str]) -> Dict[str, Any]:
        """Exécute `BrowserUseTool.run_task` (une coroutine) depuis `_executer`,
        qui ne l'est pas — même pont par thread que GitIngest (DEC-0047) :
        `asyncio.run()` ici léverait sur une boucle déjà active (routes
        FastAPI, agents `async def`)."""
        def _dans_son_propre_fil() -> Dict[str, Any]:
            return asyncio.run(asyncio.wait_for(
                self._outil.run_task(tache, cdp_url=cdp_url), timeout=DELAI_SECONDES))

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
