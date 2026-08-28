"""Un seul identifiant Google, plusieurs services.

Le courrier (chapitre 8) et l'agenda (chapitre 9) parlent au meme compte, avec
le meme identifiant OAuth : ce qui change entre eux est la **portee** accordee,
pas le client. Ecrire deux fois l'echange de jeton aurait produit deux endroits
ou se tromper sur un secret.

**Trois regles :**

1. **Le jeton est mesure, jamais suppose.** `obtenir()` rend `None` tant que
   Google n'a pas reellement rendu un jeton. Trois variables presentes ne sont
   pas trois variables valables : elles peuvent avoir ete revoquees.

2. **Aucune valeur n'est journalisee ni rendue.** Ce module manipule des
   secrets ; il n'en affiche aucun, meme tronque.

3. **Ce qui manque se nomme.** `manquantes()` rend les noms des variables
   absentes, pour que le refus soit actionnable au lieu d'etre un « non ».

Les noms `GOOGLE_*` sont les noms attendus. Les noms `GMAIL_*` sont acceptes en
repli : le chapitre 8 les a livres en premier, et un `.env` deja rempli ne doit
pas cesser de marcher parce qu'un second service arrive.
"""
import logging
import os
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger("usman.connecteurs.google")

#: Ou s'echange un jeton de rafraichissement. Dans l'environnement, jamais en dur.
URL_JETON = os.getenv("GOOGLE_TOKEN_URL", "https://oauth2.googleapis.com/token")

#: Les trois valeurs, dans l'ordre : client, secret, rafraichissement.
SUFFIXES = ("CLIENT_ID", "CLIENT_SECRET", "REFRESH_TOKEN")

#: `GOOGLE_` est le nom attendu ; `GMAIL_` est accepte en repli.
PREFIXES = ("GOOGLE", "GMAIL")

DELAI_SECONDES = 15.0

#: Marge avant l'expiration : on renouvelle un peu avant plutot que de decouvrir
#: en plein appel que le jeton vient de perimer.
MARGE_SECONDES = 60.0


def _lire(suffixe: str) -> str:
    """La premiere valeur trouvee parmi les prefixes acceptes."""
    for prefixe in PREFIXES:
        valeur = os.getenv(f"{prefixe}_{suffixe}", "")
        if valeur.strip():
            return valeur
    return ""


def identifiants() -> Tuple[str, str, str]:
    """Les trois valeurs OAuth. Chaines vides quand elles sont absentes."""
    return tuple(_lire(suffixe) for suffixe in SUFFIXES)  # type: ignore[return-value]


def manquantes() -> List[str]:
    """Les noms des variables absentes, tels qu'il doit les ecrire dans `.env`."""
    return [f"{PREFIXES[0]}_{suffixe}"
            for suffixe, valeur in zip(SUFFIXES, identifiants(), strict=True)
            if not valeur]


def echanger(client_id: str, client_secret: str, refresh_token: str) -> Dict[str, Any]:
    """Echange le jeton de rafraichissement contre un jeton d'acces. Leve si echec.

    Sortie reseau isolee dans une fonction : les tests la remplacent, et le
    reste se verifie sans Google.
    """
    with httpx.Client(timeout=DELAI_SECONDES) as client:
        reponse = client.post(URL_JETON, data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        })
        reponse.raise_for_status()
        return reponse.json()


#: Signature de l'echange, injectable.
Echange = Callable[[str, str, str], Dict[str, Any]]


class JetonGoogle:
    """Un jeton d'acces, garde jusqu'a peu avant son expiration.

    Le redemander a chaque appel ferait deux allers-retours pour lire un
    message. Le garder eternellement ferait echouer le troisieme.
    """

    def __init__(self, echange: Optional[Echange] = None) -> None:
        self._echange = echange or echanger
        self._jeton: Optional[str] = None
        self._expire_a: float = 0.0

    def obtenir(self) -> Optional[str]:
        """Un jeton valable, ou `None` si on n'a pas pu en obtenir.

        `None` couvre les deux cas, et c'est voulu : identifiants absents ou
        identifiants refuses menent au meme resultat pratique — on ne peut pas
        appeler. Ce qui les distingue se dit dans la sonde du connecteur, qui
        nomme les variables manquantes.
        """
        if self._jeton and time.monotonic() < self._expire_a:
            return self._jeton

        client_id, client_secret, refresh = identifiants()
        if not (client_id and client_secret and refresh):
            return None

        try:
            charge = self._echange(client_id, client_secret, refresh)
        except Exception as erreur:  # noqa: BLE001 — un refus est un etat, pas un crash
            logger.info("Jeton Google refuse : %s", type(erreur).__name__)
            return None

        jeton = (charge or {}).get("access_token")
        if not jeton:
            logger.info("Google a repondu sans jeton d'acces.")
            return None

        duree = charge.get("expires_in")
        duree = float(duree) if isinstance(duree, (int, float)) else 3600.0
        self._jeton = str(jeton)
        self._expire_a = time.monotonic() + max(0.0, duree - MARGE_SECONDES)
        return self._jeton
