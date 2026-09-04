"""L'adresse courante de la machine du proprietaire, annoncee par elle.

**Le probleme, en une phrase.** Son PC publie ARENA par un tunnel
`trycloudflare`, qui tire un nom au hasard **a chaque demarrage**. Il devait
donc recopier une nouvelle adresse dans son telephone chaque fois qu'il
allumait sa machine — plusieurs fois par semaine, pour un PC qui tourne
environ quatre heures par jour.

Le montage qui regle ca : le telephone ne connait qu'**une seule adresse**,
celle de son serveur permanent. Au demarrage, le PC vient y deposer l'adresse
du jour ; le telephone la demande et parle **directement** au PC. Rien ne
transite par le serveur permanent quand la machine repond : c'est ce qui
distingue cette solution d'un simple relais.

Deux protections, et la seconde est la moins evidente :

- **Ecrire demande la cle.** Sans elle, n'importe qui pourrait faire pointer
  son telephone vers une machine choisie par un autre.
- **Une annonce perime.** `trycloudflare` **recycle ses noms** : une adresse
  vieille de plusieurs jours peut appartenir a un inconnu. Le telephone y
  presenterait sa cle. On refuse donc de servir une annonce trop vieille —
  mieux vaut retomber sur le serveur permanent que parler a une machine dont
  on ne sait plus rien.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

logger = logging.getLogger("usman.reseau")

#: Au-dela, l'annonce n'est plus servie. Douze heures couvrent une journee de
#: travail sans laisser une adresse trainer une semaine. Le PC re-annonce a
#: chaque demarrage, donc la fenetre se renouvelle d'elle-meme.
DUREE_DE_VIE = timedelta(hours=12)


class AdresseMachine:
    """Retient la derniere adresse annoncee, et refuse de servir la vieille."""

    def __init__(self, fichier: Path) -> None:
        self._fichier = fichier

    def annoncer(self, adresse: str, nom: str = "") -> Dict[str, Any]:
        """Enregistre l'adresse courante de la machine.

        Raises:
            ValueError: si l'adresse n'est pas une URL `http(s)` complete.
                Une valeur douteuse est refusee **a l'ecriture** : servie plus
                tard, elle enverrait le telephone n'importe ou.
        """
        propre = (adresse or "").strip().rstrip("/")
        analysee = urlparse(propre)
        if analysee.scheme not in ("http", "https") or not analysee.netloc:
            raise ValueError(f"adresse invalide : {adresse!r}")

        annonce = {
            "adresse": propre,
            "machine": (nom or "").strip()[:80],
            "annonce_le": datetime.now(timezone.utc).isoformat(),
        }
        self._fichier.parent.mkdir(parents=True, exist_ok=True)
        self._fichier.write_text(json.dumps(annonce), encoding="utf-8")
        logger.info("Machine annoncee : %s", propre)
        return annonce

    def derniere(self) -> Optional[Dict[str, Any]]:
        """L'annonce en cours, ou `None`.

        `None` couvre trois cas differents, et c'est voulu qu'ils se
        ressemblent pour l'appelant : jamais annoncee, fichier illisible, ou
        trop vieille. Dans les trois, la seule reponse honnete est « je ne
        sais pas ou est la machine ».
        """
        try:
            annonce = json.loads(self._fichier.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

        try:
            depuis = datetime.fromisoformat(annonce["annonce_le"])
        except (KeyError, TypeError, ValueError):
            return None

        age = datetime.now(timezone.utc) - depuis
        if age > DUREE_DE_VIE:
            # Perimee : `trycloudflare` recycle ses noms, et cette adresse
            # peut appartenir a quelqu'un d'autre aujourd'hui.
            return None

        return {**annonce, "age_secondes": int(age.total_seconds())}

    def oublier(self) -> None:
        """Efface l'annonce. Le telephone retombe sur le serveur permanent."""
        self._fichier.unlink(missing_ok=True)
