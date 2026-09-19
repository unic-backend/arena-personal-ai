"""Anthropic — Claude Sonnet 5, quand c'est le raisonnement qui compte.

Groq sert le **temps jusqu'au premier mot** ; ce fournisseur-ci sert la qualite
du raisonnement. Les deux coexistent, et l'aiguilleur
(`core/models/routeur.py`) choisit.

**Pourquoi ce fichier parle HTTP au lieu d'utiliser le SDK d'Anthropic.** Ce
n'est pas une preference de style, c'est une contrainte mesuree le 19/09/2026 :
`browser-use==0.13.10` epingle `anthropic==0.76.0` **exactement**, et
`pip install -r requirements.txt` refuse de se resoudre des qu'on demande une
autre version. Or 0.76.0 ne connait ni la reflexion adaptative, ni
`output_config`, ni `stop_details` — verifie dans la roue elle-meme, pas
suppose — donc elle ne peut pas servir Sonnet 5. Restait a choisir entre
sacrifier la navigation web pour gagner un fournisseur, ou ecrire les quatre
appels HTTP qui manquent. `httpx` est deja une dependance directe et ce depot
lit deja un flux SSE a la main pour Groq : le protocole d'Anthropic ne coute
pas une dependance de plus.

**Pourquoi il n'herite pas de `FournisseurOpenAICompatible`.** Groq et
DeepInfra parlent le protocole d'OpenAI, donc une seule implementation les sert
tous les deux. Anthropic a le sien : `system` est un parametre a part et non un
message, `max_tokens` est obligatoire, la reponse est une liste de blocs typés,
et l'authentification passe par `x-api-key` et non `Authorization: Bearer`.
Forcer ce protocole dans la classe OpenAI aurait produit une troisieme
configuration qui ment sur ce qu'elle fait.

**Cinq regles, les memes que pour les autres fournisseurs :**

1. **La cle ne sort jamais d'ici.** Les erreurs passent par `nettoyer_erreur`
   avant tout journal — un service qui refuse une authentification reprend
   parfois ce qu'il a recu.

2. **Sans `ANTHROPIC_API_KEY`, ce fournisseur est ABSENT**, pas en panne. Il ne
   tente rien et l'aiguilleur passe au suivant. **Tant que la cle n'est pas
   posee, ce fichier ne change donc rien au comportement d'ARENA.**

3. **La latence est mesuree, pas estimee.** Meme objet `Mesure` que les autres,
   donc les memes chiffres comparables dans le meme rapport.

4. **Les jetons viennent de la reponse, jamais d'une estimation.** Absents, ils
   restent `None` — une estimation maison deviendrait une facture imaginaire.

5. **Un refus se dit.** Claude peut decliner une demande (HTTP 200,
   `stop_reason == "refusal"`). Rendre le texte vide ferait passer un refus
   pour une panne, et l'aiguilleur irait demander la meme chose a un autre.

**Ce que l'API de Sonnet 5 n'accepte pas**, et qu'on n'envoie donc pas :
`temperature`, `top_p`, `top_k` (retires — 400), `budget_tokens` (retire — 400,
c'est `thinking: {"type": "adaptive"}` qui le remplace), et le prefill de la
derniere reponse assistant.
"""
import json
import logging
import time
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx

from core.models.base import ModelProvider
from core.models.openai_compatible import Mesure, nettoyer_erreur

logger = logging.getLogger("usman.modeles.anthropic")

NOM = "anthropic"

#: La version de l'API, envoyee a chaque requete. Anthropic la rend obligatoire
#: et s'en sert pour ne jamais casser un client existant.
VERSION_API = "2023-06-01"

#: Les niveaux d'effort que l'API accepte. Un reglage hors liste est refuse
#: **ici**, avec sa raison, plutot que d'aller chercher un 400 sur le reseau.
EFFORTS = ("low", "medium", "high", "xhigh", "max")


class AnthropicProvider(ModelProvider):
    """Claude, par l'API d'Anthropic. Configure par l'environnement."""

    def __init__(self, api_key: str = "", model_name: str = "",
                 max_tokens: int = 0, effort: str = "", base_url: str = "",
                 delai_connexion: float = 0.0, delai_total: float = 0.0,
                 client: Optional[Any] = None) -> None:
        from apps.backend.config import (
            ANTHROPIC_API_KEY,
            ANTHROPIC_EFFORT,
            ANTHROPIC_MAX_TOKENS,
            ANTHROPIC_MODELE,
            ANTHROPIC_URL,
            CLOUD_DELAI_CONNEXION,
            CLOUD_DELAI_TOTAL,
        )
        self.nom = NOM
        self.base_url = (base_url or ANTHROPIC_URL).rstrip("/")
        self.model_name = model_name or ANTHROPIC_MODELE
        self.max_tokens = max_tokens or ANTHROPIC_MAX_TOKENS
        self._cle = api_key or ANTHROPIC_API_KEY
        self._delai = httpx.Timeout(delai_total or CLOUD_DELAI_TOTAL,
                                    connect=delai_connexion or CLOUD_DELAI_CONNEXION)

        demande = (effort or ANTHROPIC_EFFORT or "high").strip().lower()
        if demande not in EFFORTS:
            logger.warning(
                "ANTHROPIC_EFFORT=%r inconnu (attendu : %s) : 'high' est applique.",
                demande, ", ".join(EFFORTS))
            demande = "high"
        self.effort = demande

        # Injectable : les tests n'ont besoin d'aucune cle ni d'aucun reseau.
        self._client = client
        #: La derniere mesure, lisible par l'aiguilleur.
        self.derniere_mesure: Optional[Mesure] = None

    # --- Ce que la classe de base exige ------------------------------------------

    @property
    def configure(self) -> bool:
        """Une cle est-elle presente ? La question n'est pas « est-elle bonne ? »."""
        return bool(self._cle and self.model_name)

    async def is_available(self) -> bool:
        """Sans cle : `False`, sans rien tenter.

        Avec une cle : on demande la fiche du modele configure
        (`GET /v1/models/{modele}`). C'est la sonde la moins chere qui prouve a
        la fois que la cle est acceptee **et** que ce modele-la existe pour ce
        compte — un modele retire du catalogue rend un 404 lisible plutot qu'un
        echec a chaque phrase.
        """
        if not self.configure:
            return False
        try:
            charge = await self._appeler(f"models/{self.model_name}", methode="GET")
        except Exception as erreur:  # noqa: BLE001 — une panne est un etat
            logger.info("%s indisponible : %s", self.nom,
                        nettoyer_erreur(erreur, self._cle))
            return False
        return isinstance(charge, dict) and bool(charge.get("id"))

    async def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Une reponse complete. La mesure est relevee, la cle ne sort pas."""
        mesure = Mesure(fournisseur=self.nom, modele=self.model_name)
        try:
            charge = await self._appeler(
                "messages", corps=self._corps(prompt, system_prompt, flux=False))
        except Exception as erreur:  # noqa: BLE001
            mesure.erreur = nettoyer_erreur(erreur, self._cle)
            mesure.fin = time.perf_counter()
            self.derniere_mesure = mesure
            raise

        mesure.fin = time.perf_counter()
        mesure.premier_jeton = mesure.fin  # sans flux, le premier mot arrive a la fin
        self._relever_usage(
            mesure, charge.get("usage") if isinstance(charge, dict) else None)
        self.derniere_mesure = mesure
        return self._texte_de(charge)

    async def generate_stream(self, prompt: str, system_prompt: Optional[str] = None
                              ) -> AsyncGenerator[str, None]:
        """La reponse mot a mot. Ce qui est deja arrive reste arrive.

        Seuls les `text_delta` sortent d'ici : les blocs de reflexion ont lieu
        et sont factures — c'est ce qui rend la reponse meilleure — mais ils ne
        sont pas la reponse et ne partent pas vers son ecran.
        """
        mesure = Mesure(fournisseur=self.nom, modele=self.model_name)
        client = self._client or httpx.AsyncClient(timeout=self._delai)
        ferme = self._client is None
        try:
            async with client.stream(
                "POST", f"{self.base_url}/messages",
                headers=self._entetes(),
                json=self._corps(prompt, system_prompt, flux=True),
            ) as reponse:
                reponse.raise_for_status()
                async for ligne in reponse.aiter_lines():
                    evenement = self._evenement_de(ligne)
                    if evenement is None:
                        continue
                    # Les jetons arrivent AVANT et APRES le texte : l'entree au
                    # `message_start`, la sortie au `message_delta`. Les relever
                    # au fil de l'eau est la seule facon de les avoir aussi
                    # quand le flux se termine normalement.
                    self._relever_evenement(mesure, evenement)
                    morceau = self._texte_du_delta(evenement)
                    if morceau is None:
                        continue
                    if mesure.premier_jeton is None:
                        mesure.premier_jeton = time.perf_counter()
                    yield morceau
        except Exception as erreur:  # noqa: BLE001 — le flux casse se rapporte
            mesure.erreur = nettoyer_erreur(erreur, self._cle)
            raise
        finally:
            mesure.fin = time.perf_counter()
            self.derniere_mesure = mesure
            if ferme:
                await client.aclose()

    # --- La couche reseau -----------------------------------------------------------

    def _entetes(self) -> Dict[str, str]:
        """`x-api-key`, pas `Authorization: Bearer` — c'est Anthropic, pas OpenAI."""
        return {"x-api-key": self._cle,
                "anthropic-version": VERSION_API,
                "Content-Type": "application/json"}

    def _corps(self, prompt: str, system_prompt: Optional[str],
               flux: bool) -> Dict[str, Any]:
        """Ce qu'on envoie, et **rien de plus**.

        `system` est un parametre a part, pas un message : c'est la difference
        de protocole qui justifie ce fichier. `temperature`, `top_p`, `top_k` et
        `budget_tokens` sont absents parce que Sonnet 5 les refuse par un 400 —
        les omettre n'est pas une simplification, c'est la seule forme valide.
        """
        corps: Dict[str, Any] = {
            "model": self.model_name,
            "max_tokens": self.max_tokens,
            "messages": [{"role": "user", "content": prompt}],
            # La reflexion adaptative : le modele decide lui-meme quand et
            # combien reflechir. C'est ce qui remplace l'ancien budget fixe.
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": self.effort},
            "stream": flux,
        }
        if system_prompt:
            corps["system"] = system_prompt
        return corps

    async def _appeler(self, chemin: str, corps: Optional[Dict[str, Any]] = None,
                       methode: str = "POST") -> Dict[str, Any]:
        client = self._client or httpx.AsyncClient(timeout=self._delai)
        try:
            url = f"{self.base_url}/{chemin}"
            if methode == "GET":
                reponse = await client.get(url, headers=self._entetes())
            else:
                reponse = await client.post(url, headers=self._entetes(), json=corps)
            reponse.raise_for_status()
            return reponse.json()
        finally:
            if self._client is None:
                await client.aclose()

    # --- Lecture de la reponse --------------------------------------------------------

    @staticmethod
    def _texte_de(charge: Any) -> str:
        """Le texte des blocs `text`, et seulement eux.

        Une reponse Claude est une LISTE de blocs typés — du texte, de la
        reflexion, un appel d'outil. Prendre `content[0]` marcherait jusqu'au
        jour ou le premier bloc serait une reflexion.

        Un refus n'est pas une reponse vide : il est rendu tel quel, avec sa
        categorie, pour que l'appelant sache la difference entre « il a refuse »
        et « le service n'a rien renvoye ».
        """
        if not isinstance(charge, dict):
            return ""
        if charge.get("stop_reason") == "refusal":
            details = charge.get("stop_details") or {}
            categorie = (details.get("category") if isinstance(details, dict)
                         else None) or "non precisee"
            return (f"Claude a refuse cette demande (categorie : {categorie}). "
                    "Rien n'a ete produit.")
        blocs = charge.get("content")
        if not isinstance(blocs, list):
            return ""
        morceaux: List[str] = [
            str(bloc.get("text")) for bloc in blocs
            if isinstance(bloc, dict) and bloc.get("type") == "text" and bloc.get("text")
        ]
        return "".join(morceaux)

    @staticmethod
    def _evenement_de(ligne: str) -> Optional[Dict[str, Any]]:
        """L'evenement porte par une ligne de flux, ou `None`.

        Le flux est du SSE : des lignes `event: <nom>` et des lignes
        `data: {...}`. Seules les secondes portent quelque chose. Une ligne
        illisible est ignoree — elle ne doit pas casser une reponse deja
        commencee.
        """
        if not ligne or not ligne.startswith("data:"):
            return None
        charge = ligne[len("data:"):].strip()
        if not charge:
            return None
        try:
            evenement = json.loads(charge)
        except Exception:  # noqa: BLE001
            return None
        return evenement if isinstance(evenement, dict) else None

    @staticmethod
    def _texte_du_delta(evenement: Dict[str, Any]) -> Optional[str]:
        """Le texte d'un `content_block_delta`, et rien d'autre.

        Un `thinking_delta` porte lui aussi du texte. Le laisser passer ferait
        lire le raisonnement a la place de la reponse.
        """
        if evenement.get("type") != "content_block_delta":
            return None
        delta = evenement.get("delta")
        if not isinstance(delta, dict) or delta.get("type") != "text_delta":
            return None
        texte = delta.get("text")
        return str(texte) if texte else None

    @classmethod
    def _relever_evenement(cls, mesure: Mesure, evenement: Dict[str, Any]) -> None:
        """Les jetons annonces par le flux, la ou ils arrivent reellement.

        `message_start` porte les jetons d'ENTREE ; `message_delta` porte le
        total courant de SORTIE. Les chiffres de sortie ecrasent, ceux d'entree
        ne sont repris que s'ils existent — sinon le total d'entree du debut
        serait efface par un evenement qui ne le reporte pas.
        """
        type_ = evenement.get("type")
        if type_ == "message_start":
            message = evenement.get("message")
            if isinstance(message, dict):
                cls._relever_usage(mesure, message.get("usage"))
        elif type_ == "message_delta":
            cls._relever_usage(mesure, evenement.get("usage"))

    @staticmethod
    def _relever_usage(mesure: Mesure, usage: Any) -> None:
        """Reprend les jetons annonces par le service. Absents, ils restent `None`."""
        if not isinstance(usage, dict):
            return
        entree = usage.get("input_tokens")
        sortie = usage.get("output_tokens")
        if isinstance(entree, int):
            mesure.jetons_entree = entree
        if isinstance(sortie, int):
            mesure.jetons_sortie = sortie
