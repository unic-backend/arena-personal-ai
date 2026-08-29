"""Groq et DeepInfra : deux services, un seul protocole.

Les deux exposent l'API d'OpenAI. Ecrire deux classes qui se recopieraient
serait deux endroits ou se tromper sur un en-tete d'authentification — ce qui
est exactement le genre d'erreur qui envoie une cle au mauvais serveur.

Une implementation, deux configurations.

**Six regles :**

1. **La cle ne sort jamais d'ici.** Elle part dans l'en-tete, elle n'entre dans
   aucun journal, aucun message d'erreur, aucun compte-rendu. Les erreurs sont
   nettoyees avant d'etre rapportees.

2. **Un delai de connexion court.** Sans reseau, ARENA doit basculer sur Ollama
   sans faire attendre une reponse de chat. Trois secondes pour se connecter,
   pas trois minutes.

3. **La latence est mesuree, pas estimee.** Le temps jusqu'au premier jeton et
   le temps total sont relevés a chaque appel. Aucun chiffre de vitesse n'est
   annonce ailleurs sans etre passe par la.

4. **Sans cle, le fournisseur est ABSENT, pas en panne.** `is_available()` rend
   `False` sans rien tenter : interroger un service pour lequel on n'a pas de
   cle est une requete perdue.

5. **Ce que le service dit de sa consommation est repris tel quel.** Les jetons
   comptes viennent de sa reponse ; quand il n'en donne pas, ils restent `None`.
   Une estimation maison deviendrait une facture imaginaire.

6. **Le streaming d'abord.** Une reponse qui arrive mot a mot est utilisable
   avant d'etre finie. Quand le flux casse en cours de route, ce qui est deja
   arrive reste arrive — on ne rejoue pas la reponse depuis le debut.
"""
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx

from core.models.base import ModelProvider

logger = logging.getLogger("usman.modeles.distant")

#: Ce qu'on retire d'un message d'erreur avant de le rapporter. Un service qui
#: refuse une cle la reprend parfois dans sa reponse.
LONGUEUR_ERREUR_MAX = 160


@dataclass
class Mesure:
    """Ce qu'un appel a reellement coute en temps, et en jetons quand on le sait."""

    fournisseur: str
    modele: str
    debut: float = field(default_factory=time.perf_counter)
    premier_jeton: Optional[float] = None
    fin: Optional[float] = None
    jetons_entree: Optional[int] = None
    jetons_sortie: Optional[int] = None
    erreur: str = ""

    @property
    def secondes_premier_jeton(self) -> Optional[float]:
        """Le temps jusqu'au premier mot. `None` si aucun n'est arrive."""
        return None if self.premier_jeton is None else self.premier_jeton - self.debut

    @property
    def secondes_total(self) -> Optional[float]:
        return None if self.fin is None else self.fin - self.debut

    @property
    def jetons_par_seconde(self) -> Optional[float]:
        """Mesure, jamais annoncee sans les deux chiffres qui la composent."""
        duree = self.secondes_total
        if not duree or not self.jetons_sortie:
            return None
        return self.jetons_sortie / duree

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fournisseur": self.fournisseur, "modele": self.modele,
            "premier_jeton_s": self.secondes_premier_jeton,
            "total_s": self.secondes_total,
            "jetons_entree": self.jetons_entree, "jetons_sortie": self.jetons_sortie,
            "jetons_par_seconde": self.jetons_par_seconde,
            "erreur": self.erreur,
        }


def nettoyer_erreur(erreur: BaseException, cle: str) -> str:
    """Le type et le message d'une erreur, **sans la cle**.

    Un service qui refuse une authentification renvoie parfois ce qu'il a recu.
    Ce nettoyage est la derniere barriere avant un journal.
    """
    texte = f"{type(erreur).__name__}: {erreur}".replace("\n", " ")
    if cle:
        texte = texte.replace(cle, "[cle retiree]")
    return texte[:LONGUEUR_ERREUR_MAX]


class FournisseurOpenAICompatible(ModelProvider):
    """Un service distant qui parle le protocole d'OpenAI."""

    def __init__(self, nom: str, base_url: str, api_key: str, model_name: str,
                 delai_connexion: float = 3.0, delai_total: float = 60.0,
                 client: Optional[Any] = None) -> None:
        self.nom = nom
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self._cle = api_key
        self._delai = httpx.Timeout(delai_total, connect=delai_connexion)
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

        Interroger un service pour lequel on n'a pas de cle est une requete
        perdue, et une seconde d'attente de plus avant de basculer sur Ollama.
        """
        if not self.configure:
            return False
        try:
            charge = await self._appeler("models", methode="GET")
        except Exception as erreur:  # noqa: BLE001 — une panne est un etat
            logger.info("%s indisponible : %s", self.nom, nettoyer_erreur(erreur, self._cle))
            return False
        return isinstance(charge, dict)

    async def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Une reponse complete. La mesure est relevee, la cle ne sort pas."""
        mesure = Mesure(fournisseur=self.nom, modele=self.model_name)
        try:
            charge = await self._appeler(
                "chat/completions", corps=self._corps(prompt, system_prompt, flux=False))
        except Exception as erreur:  # noqa: BLE001
            mesure.erreur = nettoyer_erreur(erreur, self._cle)
            mesure.fin = time.perf_counter()
            self.derniere_mesure = mesure
            raise

        mesure.fin = time.perf_counter()
        mesure.premier_jeton = mesure.fin  # sans flux, le premier mot arrive a la fin
        self._relever_usage(mesure, charge)
        self.derniere_mesure = mesure
        return self._texte_de(charge)

    async def generate_stream(self, prompt: str, system_prompt: Optional[str] = None
                              ) -> AsyncGenerator[str, None]:
        """La reponse mot a mot. Ce qui est deja arrive reste arrive."""
        mesure = Mesure(fournisseur=self.nom, modele=self.model_name)
        client = self._client or httpx.AsyncClient(timeout=self._delai)
        ferme = self._client is None
        try:
            async with client.stream(
                "POST", f"{self.base_url}/chat/completions",
                headers=self._entetes(),
                json=self._corps(prompt, system_prompt, flux=True),
            ) as reponse:
                reponse.raise_for_status()
                async for ligne in reponse.aiter_lines():
                    morceau = self._jeton_de(ligne)
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
        return {"Authorization": f"Bearer {self._cle}", "Content-Type": "application/json"}

    def _corps(self, prompt: str, system_prompt: Optional[str], flux: bool) -> Dict[str, Any]:
        messages: List[Dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return {"model": self.model_name, "messages": messages, "stream": flux}

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
        """Le texte de la reponse. Une charge illisible rend une chaine vide."""
        if not isinstance(charge, dict):
            return ""
        choix = charge.get("choices")
        if not isinstance(choix, list) or not choix:
            return ""
        message = (choix[0] or {}).get("message") or {}
        return str(message.get("content") or "").strip()

    @staticmethod
    def _jeton_de(ligne: str) -> Optional[str]:
        """Le morceau de texte porte par une ligne de flux, ou `None`.

        Le protocole envoie des lignes `data: {...}` et une ligne `data: [DONE]`.
        Une ligne qu'on ne sait pas lire est ignoree : elle ne doit pas casser
        une reponse deja commencee.
        """
        if not ligne or not ligne.startswith("data:"):
            return None
        charge = ligne[len("data:"):].strip()
        if not charge or charge == "[DONE]":
            return None
        try:
            morceau = json.loads(charge)
        except Exception:  # noqa: BLE001
            return None
        choix = morceau.get("choices")
        if not isinstance(choix, list) or not choix:
            return None
        delta = (choix[0] or {}).get("delta") or {}
        contenu = delta.get("content")
        return str(contenu) if contenu else None

    @staticmethod
    def _relever_usage(mesure: Mesure, charge: Any) -> None:
        """Reprend les jetons annonces par le service. Absents, ils restent `None`.

        Une estimation maison deviendrait une facture imaginaire.
        """
        usage = (charge or {}).get("usage") if isinstance(charge, dict) else None
        if not isinstance(usage, dict):
            return
        entree = usage.get("prompt_tokens")
        sortie = usage.get("completion_tokens")
        if isinstance(entree, int):
            mesure.jetons_entree = entree
        if isinstance(sortie, int):
            mesure.jetons_sortie = sortie
