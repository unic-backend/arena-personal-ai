"""Connecteur de donnees de marche — prix et historique, en lecture seule.

Fournit à ARENA une source de données financières réelles, sans clé et sans
aucune action à effet externe : ce connecteur ne peut ni acheter, ni vendre,
ni signer quoi que ce soit. Il répond à deux questions, « combien ça vaut » et
« comment ça a évolué », rien de plus.

**Pourquoi CoinGecko et pas un fournisseur générique.** L'API publique
`/simple/price` et `/coins/{id}/market_chart` ne demande aucune clé — exactement
ce dont a besoin une lecture seule, sans mettre le propriétaire devant un
compte à créer avant de pouvoir demander « analyse le bitcoin ». D'autres
fournisseurs (actions, ETF, forex) peuvent être ajoutés plus tard derrière la
même interface (`MarketDataProvider`, plus bas) : c'est pour ça qu'elle existe
séparément de `ConnecteurMarketData`.

**Ce que ce connecteur ne fait jamais** (audit AutoHedge, DEC — voir
docs/DECISIONS.md) :

- aucun portefeuille, aucune clé privée, aucune signature de transaction ;
- aucun ordre, aucun échange ; `capacites()` ne déclare que des lectures ;
- aucun calcul quantitatif ici — il rend des prix bruts, jamais un indicateur.
  Le calcul déterministe vit dans `core/finance/quant.py`, qui ne fait jamais
  d'appel réseau lui-même. La séparation est volontaire : un connecteur qui
  calcule ET récupère mélange ce qui peut échouer (le réseau) avec ce qui ne
  peut pas (l'arithmétique).
"""
import logging
import time
from typing import Any, Dict, List, Optional

import httpx

from core.actions.resultat import ResultatAction, echec, succes
from core.connectors.base import Capacite, Connecteur, EtatSante, Sante, _maintenant

logger = logging.getLogger("usman.connecteurs.market_data")

#: Aucune URL a deviner : l API publique de CoinGecko, fixe. Pas de cle requise
#: pour les endpoints utilises ici (DEC-0002 : rien ne part chez un tiers a son
#: insu, et cette API ne demande ni compte ni secret pour un usage normal).
BASE_URL = "https://api.coingecko.com/api/v3"

DELAI_SECONDES = 10.0
DUREE_SONDE_SECONDES = 60.0

#: Tickers usuels vers l'identifiant CoinGecko. Liste volontairement courte :
#: elle couvre ce qu'une phrase ordinaire nomme ("bitcoin", "BTC", "ethereum"),
#: pas un annuaire complet. `rechercher_identifiant` retombe sur le texte tel
#: quel quand le ticker n'y figure pas — CoinGecko accepte aussi l'id complet
#: directement ("solana", "chainlink"...).
TICKERS_CONNUS: Dict[str, str] = {
    "btc": "bitcoin", "bitcoin": "bitcoin",
    "eth": "ethereum", "ethereum": "ethereum",
    "sol": "solana", "solana": "solana",
    "bnb": "binancecoin",
    "xrp": "ripple", "ripple": "ripple",
    "doge": "dogecoin", "dogecoin": "dogecoin",
    "ada": "cardano", "cardano": "cardano",
    "ltc": "litecoin", "litecoin": "litecoin",
    "dot": "polkadot", "polkadot": "polkadot",
    "avax": "avalanche-2",
    "link": "chainlink", "chainlink": "chainlink",
    "matic": "polygon-ecosystem-token",
    "usdc": "usd-coin",
    "usdt": "tether",
}


def identifiant_coingecko(ticker: str) -> str:
    """Traduit un ticker usuel en identifiant CoinGecko. Passe-plat sinon."""
    return TICKERS_CONNUS.get(ticker.strip().lower(), ticker.strip().lower())


CE_QUI_MANQUE = "aucune connexion sortante vers api.coingecko.com (reseau bloque ou API en panne)."


class ConnecteurMarketData(Connecteur):
    """Prix et historique de marché — crypto aujourd'hui, actions/FX plus tard
    derrière la même interface (section 13 de la mission : agnostique à
    l'actif, honnête sur ce qui n'a pas de fournisseur)."""

    service = "market_data"
    nom = "market_data"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._sante: Optional[Sante] = None
        self._sante_mesuree_a: float = 0.0

    def capacites(self) -> Dict[str, Capacite]:
        return {
            "prix": Capacite(
                nom="prix", action="read",
                description="Prix actuel (USD), variation 24h, capitalisation et volume d'un ou plusieurs actifs.",
                ecriture=False, quota_par_minute=30),
            "historique": Capacite(
                nom="historique", action="read",
                description="Historique de prix (jusqu'a 365 jours) d'un actif, pour le calcul quantitatif.",
                ecriture=False, quota_par_minute=30),
        }

    def authentifier(self) -> bool:
        """Vrai : API publique, aucun identifiant a presenter."""
        return True

    def sonder(self) -> Sante:
        maintenant = time.monotonic()
        if self._sante is not None and maintenant - self._sante_mesuree_a < DUREE_SONDE_SECONDES:
            return self._sante

        try:
            with httpx.Client(timeout=5.0, trust_env=False) as client:
                reponse = client.get(f"{BASE_URL}/ping")
            if reponse.status_code == 200:
                sante = Sante(etat=EtatSante.OPERATIONNEL,
                             message="CoinGecko repond.", mesure_le=_maintenant())
            else:
                sante = Sante(etat=EtatSante.EN_PANNE,
                             message=f"CoinGecko repond {reponse.status_code}.",
                             mesure_le=_maintenant())
        except httpx.HTTPError as erreur:
            sante = Sante(etat=EtatSante.NON_CONFIGURE,
                         message=f"CoinGecko injoignable : {erreur}",
                         ce_qui_manque=CE_QUI_MANQUE, mesure_le=_maintenant())

        self._sante = sante
        self._sante_mesuree_a = maintenant
        return sante

    def _executer(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        if capacite.nom == "prix":
            return self._prix(capacite, **parametres)
        return self._historique(capacite, **parametres)

    def _prix(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        actifs_bruts = parametres.get("actifs") or parametres.get("actif")
        if isinstance(actifs_bruts, str):
            actifs_bruts = [actifs_bruts]
        actifs_bruts = [str(a) for a in (actifs_bruts or []) if str(a).strip()]
        if not actifs_bruts:
            return echec(action=capacite.nom, cible=self.nom, message="Aucun actif demande.")

        ids = {identifiant_coingecko(a): a for a in actifs_bruts}

        try:
            with httpx.Client(timeout=DELAI_SECONDES, trust_env=False) as client:
                reponse = client.get(f"{BASE_URL}/simple/price", params={
                    "ids": ",".join(ids.keys()),
                    "vs_currencies": "usd",
                    "include_24hr_change": "true",
                    "include_market_cap": "true",
                    "include_24hr_vol": "true",
                })
        except httpx.HTTPError as erreur:
            return echec(action=capacite.nom, cible=self.nom,
                         message=f"CoinGecko injoignable : {erreur}")

        if reponse.status_code != 200:
            return echec(action=capacite.nom, cible=self.nom,
                         message=f"CoinGecko a refuse la requete ({reponse.status_code}) : {reponse.text[:200]}")

        donnees = reponse.json()
        trouves = {ids[cg_id]: v for cg_id, v in donnees.items() if cg_id in ids}
        manquants = [original for cg_id, original in ids.items() if cg_id not in donnees]

        if not trouves:
            return echec(action=capacite.nom, cible=self.nom,
                         message=f"Aucun des actifs demandes n'a ete reconnu par CoinGecko : {actifs_bruts}.")

        return succes(
            action=capacite.nom, cible=self.nom,
            message=f"Prix recupere pour {len(trouves)} actif(s).",
            preuve=f"coingecko:simple/price:{','.join(ids.keys())}",
            prix=trouves, manquants=manquants, source="coingecko",
            mesure_le=_maintenant(),
        )

    def _historique(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        actif = str(parametres.get("actif") or "").strip()
        if not actif:
            return echec(action=capacite.nom, cible=self.nom, message="Aucun actif demande.")

        jours = parametres.get("jours", 30)
        try:
            jours = max(1, min(365, int(jours)))
        except (TypeError, ValueError):
            jours = 30

        cg_id = identifiant_coingecko(actif)
        try:
            with httpx.Client(timeout=DELAI_SECONDES, trust_env=False) as client:
                reponse = client.get(f"{BASE_URL}/coins/{cg_id}/market_chart", params={
                    "vs_currency": "usd", "days": jours,
                })
        except httpx.HTTPError as erreur:
            return echec(action=capacite.nom, cible=self.nom,
                         message=f"CoinGecko injoignable : {erreur}")

        if reponse.status_code == 404:
            return echec(action=capacite.nom, cible=self.nom,
                         message=f"Actif inconnu de CoinGecko : {actif} (id essaye : {cg_id}).")
        if reponse.status_code != 200:
            return echec(action=capacite.nom, cible=self.nom,
                         message=f"CoinGecko a refuse la requete ({reponse.status_code}) : {reponse.text[:200]}")

        donnees = reponse.json()
        prix: List[List[float]] = donnees.get("prices") or []
        if not prix:
            return echec(action=capacite.nom, cible=self.nom,
                         message=f"Aucun historique renvoye pour {actif}.")

        return succes(
            action=capacite.nom, cible=self.nom,
            message=f"Historique recupere pour {actif} ({len(prix)} points, {jours} jours).",
            preuve=f"coingecko:market_chart:{cg_id}:{jours}j",
            actif=actif, jours=jours, points=prix, source="coingecko",
            mesure_le=_maintenant(),
        )
