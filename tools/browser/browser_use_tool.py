import logging
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("usman.tools.browser_use")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from apps.backend.config import MODELE_RAPIDE, OLLAMA_URL
from core.models.ollama_provider import OllamaProvider

#: Plafond d'actions pour UNE tache. Audit Fuji-Web (docs/audits/
#: fuji_web_audit.md) : sa boucle (`src/state/currentTask.ts`) ne borne
#: qu'avec un compteur brut (50) code en dur dans l'interface, jamais
#: expose ni configurable. `browser_use` borne deja en interne
#: (`loop_detection_*`, cinq echecs consecutifs) ; ce plafond est la
#: garantie COTE ARENA, verifiable independamment de la bibliotheque
#: (mission §8 : jamais une boucle illimitee).
MAX_ETAPES_DEFAUT = 25

#: Action `browser_use` (vocabulaire reel, verifie dans le paquet installe
#: — `browser_use.tools.service.Tools().registry.registry.actions.keys()`)
#: -> etat operationnel ARENA (mission §23). Liste fermee : une action non
#: listee devient "EN_COURS", jamais une supposition sur ce qu'elle fait.
#: Ce que l'appelant reçoit N'EST JAMAIS le raisonnement du modele
#: (`thinking`/`evaluation_previous_goal`/`memory` d'`AgentOutput`) — un
#: statut concis seulement, comme la mission l'exige explicitement.
STATUTS_PAR_ACTION = {
    "navigate": "NAVIGATING", "go_back": "NAVIGATING", "search": "NAVIGATING",
    "switch": "NAVIGATING", "close": "NAVIGATING",
    "click": "CLICKING",
    "input": "TYPING", "send_keys": "TYPING", "select_dropdown": "TYPING",
    "upload_file": "UPLOADING",
    "wait": "WAITING",
    "scroll": "READING_PAGE", "extract": "READING_PAGE", "search_page": "READING_PAGE",
    "find_elements": "READING_PAGE", "find_text": "READING_PAGE",
    "dropdown_options": "READING_PAGE", "evaluate": "READING_PAGE",
    "screenshot": "READING_PAGE",
    "save_as_pdf": "DOWNLOADING", "write_file": "DOWNLOADING",
    "replace_file": "DOWNLOADING", "read_file": "DOWNLOADING",
    "done": "COMPLETED",
}


def _statut_pour_action(nom_action: Optional[str]) -> str:
    return STATUTS_PAR_ACTION.get(nom_action or "", "EN_COURS")


def _premiere_action(agent_output: Any) -> Optional[str]:
    """Le nom de la PREMIERE action d'un pas — `browser_use` peut en
    enchainer plusieurs par pas (`max_actions_per_step`), mais un seul
    statut est rendu par pas : le premier dit deja ce que le pas fait."""
    actions = getattr(agent_output, "action", None) or []
    if not actions:
        return None
    action = actions[0]
    corps = action.model_dump(exclude_unset=True) if hasattr(action, "model_dump") else dict(action or {})
    return next(iter(corps), None)


class BrowserUseTool:
    """Outil de navigation Web autonome basé sur Browser-Use et Playwright."""

    def __init__(self, provider: Optional[OllamaProvider] = None):
        # L'adresse et le modele viennent de la configuration, jamais du code :
        # ecrits en dur ici, un Ollama deplace ou un modele change dans `.env`
        # laissait TOUT marcher sauf la navigation, avec une erreur nommant
        # une adresse que le proprietaire n'avait pas configuree.
        self.provider = provider or OllamaProvider(
            base_url=OLLAMA_URL, model_name=MODELE_RAPIDE)

    async def run_task(
        self, task_instruction: str, cdp_url: Optional[str] = None, *,
        max_steps: int = MAX_ETAPES_DEFAUT,
        sensitive_data: Optional[Dict[str, Any]] = None,
        allowed_domains: Optional[List[str]] = None,
        available_file_paths: Optional[List[str]] = None,
        sur_etape: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """Ouvre Chromium de façon autonome, exécute la tâche et renvoie le résultat.

        `cdp_url` : quand fourni, `browser_use` se CONNECTE à un navigateur
        DÉJÀ lancé ailleurs (ex. Lightpanda, `lightpanda serve`) au lieu
        d'en démarrer un nouveau — même paramètre que `browser_use.
        BrowserSession(cdp_url=...)`, vérifié directement dans le code
        installé (`browser_use/browser/session.py`). `None` (le défaut)
        laisse `browser_use` lancer SON PROPRE Chromium local via
        Playwright, exactement le comportement d'avant ce paramètre —
        aucun changement pour un appelant qui ne le fournit pas.

        `sensitive_data` : le mecanisme REEL de `browser_use` pour des
        identifiants (mission §14) — un dict `{nom_symbolique: valeur}` que
        la bibliotheque substitue au niveau de l'interaction DOM, jamais
        visible du modele ni du journal. ARENA n'a aucun coffre-fort
        d'identifiants aujourd'hui (verifie : aucun module `core/*secret*`
        ni `core/*credential*`) — ce parametre est donc le point de
        branchement pret pour le jour ou l'un existera, jamais rempli
        depuis du texte libre.

        `allowed_domains` : **OBLIGATOIRE des que `sensitive_data` est
        fourni** — verifie directement en construisant `browser_use.Agent`
        avec des identifiants sans lui : la bibliotheque elle-meme leve
        l'avertissement "☠️ If the agent visits a malicious website [...]
        your sensitive_data may be exposed!". Sans domaines autorises, un
        site malveillant atteint par redirection ou injection de prompt
        (mission §13) pourrait recevoir l'identifiant que ce parametre
        pretend proteger — donc refuse ici plutot que de laisser passer
        une fausse promesse de securite.

        `available_file_paths` : la liste FERMEE de fichiers qu'un envoi
        peut choisir (mission §17) — jamais une recherche libre du
        systeme de fichiers du proprietaire par l'agent lui-meme.

        `sur_etape` : rappel appele a CHAQUE pas reel de `browser_use`
        (`register_new_step_callback`), avec un statut concis
        (`{"etape": int, "action": str, "statut": str, "url": str|None}`)
        — jamais le raisonnement du modele. Optionnel : sans lui, le
        comportement est inchange, seul `resultat["etapes"]` porte
        l'historique complet a la fin.
        """
        logger.info(f"🌐 BrowserUseTool entame la tâche : {task_instruction}")

        if sensitive_data and not allowed_domains:
            return {
                "status": "error", "task": task_instruction,
                "error": "sensitive_data fourni sans allowed_domains : refuse (mission §13/§14).",
                "result": ("❌ Des identifiants ont ete fournis sans restreindre les domaines "
                          "autorises — browser_use avertit lui-meme qu'un site malveillant "
                          "pourrait alors les recevoir. Rien n'a ete lance."),
                "moteur": "lightpanda" if cdp_url else "chromium", "etapes": [],
            }

        etapes: List[Dict[str, Any]] = []

        def _rappel_etape(browser_state: Any, agent_output: Any, numero: int) -> None:
            entree = {
                "etape": numero,
                "action": _premiere_action(agent_output),
                "statut": _statut_pour_action(_premiere_action(agent_output)),
                "url": getattr(browser_state, "url", None),
            }
            etapes.append(entree)
            if sur_etape is not None:
                try:
                    sur_etape(entree)
                except Exception as erreur:  # noqa: BLE001 — un rappel en panne ne doit jamais arreter la navigation
                    logger.warning("Rappel d'etape en echec (ignore) : %s", erreur)

        try:
            from browser_use import Agent
            from browser_use.browser.session import BrowserSession
            from langchain_openai import ChatOpenAI
            from pydantic import Field

            # Classe compatible Pydantic V2 avec le champ provider déclaré
            class CustomChatOpenAI(ChatOpenAI):
                provider: str = Field(default="openai")

            llm = CustomChatOpenAI(
                model=self.provider.model_name,
                base_url=f"{self.provider.base_url}/v1",
                api_key="ollama",
                temperature=0.0
            )

            browser_session = (
                BrowserSession(cdp_url=cdp_url, allowed_domains=allowed_domains)
                if (cdp_url or allowed_domains) else None
            )

            agent = Agent(
                task=task_instruction,
                llm=llm,
                browser_session=browser_session,
                sensitive_data=sensitive_data,
                available_file_paths=available_file_paths,
                register_new_step_callback=_rappel_etape,
            )

            debut = time.monotonic()
            history = await agent.run(max_steps=max_steps)
            duree = round(time.monotonic() - debut, 2)
            final_result = history.final_result() if hasattr(history, "final_result") else str(history)

            return {
                "status": "success",
                "task": task_instruction,
                "result": str(final_result),
                "moteur": "lightpanda" if cdp_url else "chromium",
                # Signaux DETERMINISTES pour la verification cote ARENA
                # (core/connectors/browser.py::classer_resultat) — jamais
                # un simple statut fait confiance sur parole (mission §7).
                "etapes": etapes,
                "nombre_etapes": history.number_of_steps() if hasattr(history, "number_of_steps") else len(etapes),
                "urls_visitees": history.urls() if hasattr(history, "urls") else [],
                "succes_declare": history.is_successful() if hasattr(history, "is_successful") else None,
                "erreurs": [e for e in (history.errors() if hasattr(history, "errors") else []) if e],
                "duree_secondes": duree,
                "max_etapes": max_steps,
            }

        except Exception as e:
            logger.error(f"Erreur d'exécution BrowserUse : {e}")
            return {
                "status": "error",
                "task": task_instruction,
                "error": str(e),
                "result": f"❌ Échec de la navigation autonome : {str(e)}",
                "moteur": "lightpanda" if cdp_url else "chromium",
                "etapes": etapes,
            }

if __name__ == "__main__":
    print("🌐 Outil BrowserUseTool prêt dans tools/browser/browser_use_tool.py !")
