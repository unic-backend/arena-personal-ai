"""Contrôle au démarrage : les modèles déclarés existent-ils vraiment ?

Trois fichiers déclarent un nom de modèle — `.env.example`, `config.py`, le
constructeur d'`OllamaProvider`. Aucun ne vérifiait que ce nom correspond à
quelque chose d'installé. Un tag absent ne se voit qu'au premier message, sous
la forme d'une erreur d'Ollama que l'utilisateur ne relie pas à sa cause.

Ce module regarde, dit ce qu'il voit, et **ne bloque jamais le démarrage** :
un serveur qui refuse de démarrer parce qu'un modèle manque est moins utile
qu'un serveur qui démarre en disant lequel manque.

Trois états, jamais deux :

- `PRESENT`  — le modèle est installé, mesuré sur `/api/tags` ;
- `ABSENT`   — Ollama a répondu, et ce modèle n'est pas dans sa liste ;
- `INCONNU`  — Ollama n'a pas répondu. On ne sait pas, et on ne le suppose pas.

`INCONNU` n'est pas `ABSENT`. Confondre les deux ferait annoncer un modèle
manquant à chaque fois qu'Ollama est simplement éteint.
"""
import logging
from typing import Dict, List, Optional, Set

import httpx

logger = logging.getLogger("usman.modeles")

PRESENT = "PRESENT"
ABSENT = "ABSENT"
INCONNU = "INCONNU"

DELAI_SECONDES = 3.0


async def modeles_installes(base_url: str, delai: float = DELAI_SECONDES) -> Optional[Set[str]]:
    """Rend les tags installés, ou `None` si Ollama n'a pas répondu.

    `None` est la réponse honnête à « je n'ai pas pu regarder » ; un ensemble
    vide dirait « j'ai regardé et il n'y a rien », ce qui est une autre
    affirmation.
    """
    try:
        async with httpx.AsyncClient(timeout=delai) as client:
            reponse = await client.get(f"{base_url.rstrip('/')}/api/tags")
        if reponse.status_code != 200:
            logger.warning("Ollama repond %s sur /api/tags : modeles non verifies.", reponse.status_code)
            return None
        donnees = reponse.json()
    except Exception as erreur:
        logger.warning("Ollama injoignable (%s) : modeles non verifies.", erreur)
        return None

    return {modele.get("name", "") for modele in donnees.get("models", []) if modele.get("name")}


def _etat(nom: str, installes: Optional[Set[str]]) -> str:
    """Compare un nom déclaré à la liste installée, sans rien deviner."""
    if installes is None:
        return INCONNU
    if nom in installes:
        return PRESENT
    # Ollama accepte « qwen3.5:9b » et le liste parfois tel quel, parfois avec
    # un suffixe. Un nom sans « : » vaut le tag `latest`.
    cible = nom if ":" in nom else f"{nom}:latest"
    return PRESENT if cible in installes else ABSENT


async def verifier_modeles(declares: List[str], base_url: str, delai: float = DELAI_SECONDES) -> Dict[str, str]:
    """Vérifie chaque modèle déclaré et journalise ce qui manque.

    Rend un état par modèle. N'a aucun effet de bord au-delà des journaux : le
    démarrage continue quoi qu'il arrive.
    """
    uniques = list(dict.fromkeys(nom for nom in declares if nom))
    installes = await modeles_installes(base_url, delai)
    etats = {nom: _etat(nom, installes) for nom in uniques}

    manquants = [nom for nom, etat in etats.items() if etat == ABSENT]
    if manquants:
        logger.error(
            "Modele(s) declare(s) mais non installe(s) : %s. "
            "Installe-les avec « ollama pull <nom> », sinon toute demande qui "
            "les utilise echouera.",
            ", ".join(manquants),
        )
    elif installes is None:
        logger.warning("Presence des modeles non verifiee : Ollama n'a pas repondu.")
    else:
        logger.info("Modeles declares tous presents : %s", ", ".join(etats))

    return etats
