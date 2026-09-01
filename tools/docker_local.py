"""Docker est-il utilisable ici, et l'image demandee est-elle construite ?

Deux outils posent la meme question — le bac a sable
(`tools/code/sandbox_interpreter.py`) et le moteur de graphe
(`tools/rag/graphrag_tool.py`). Elle n'etait ecrite qu'a un seul endroit, et
le moteur de graphe ne la posait pas du tout.

Ce que ca donnait, mesure le 01/09/2026 sur cette machine (demon eteint) :
`query_global` rendait `status: "info"` et le texte « Espace de connaissances
pret. Ajoutez vos documents… ». Une phrase confiante, fausse, avec un remede
qui n'aurait rien change — le probleme n'etait pas les documents.

C'est exactement le defaut n° 2 de l'audit du 01/09 : **`docker run` rend un
code de sortie non nul SANS lever**, donc le chemin d'exception n'est jamais
pris et l'echec se deguise en autre chose. Le bac a sable l'avait appris ; le
moteur de graphe non.
"""
from __future__ import annotations

import logging
import subprocess

logger = logging.getLogger("usman.tools.docker")

#: `docker info` sans demon peut trainer : on ne l'attend pas plus longtemps.
DELAI_DEMON_SECONDES = 3.0
#: `docker image inspect` est local et rapide, mais pas instantane.
DELAI_IMAGE_SECONDES = 5.0


def demon_repond(delai: float = DELAI_DEMON_SECONDES) -> bool:
    """Le demon Docker repond-il ? La question est « repond-il ? », pas
    « le binaire existe-t-il ? » — un client Docker installe sans demon actif
    repond parfaitement a `--version` et ne peut rien lancer.
    """
    try:
        acheve = subprocess.run(["docker", "info"], stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=delai)
        return acheve.returncode == 0
    except Exception:  # noqa: BLE001 - binaire absent, delai depasse : meme reponse
        return False


def image_construite(image: str, delai: float = DELAI_IMAGE_SECONDES) -> bool:
    """L'image existe-t-elle localement ?

    A ne poser que si le demon repond : `docker image inspect` sans demon
    coute une seconde pour rien.
    """
    try:
        acheve = subprocess.run(["docker", "image", "inspect", image],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                timeout=delai)
        return acheve.returncode == 0
    except Exception:  # noqa: BLE001
        return False
