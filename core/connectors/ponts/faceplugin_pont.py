"""Pont vers le SDK Faceplugin — execute par l'interpreteur du SDK.

**Ce fichier est du code ARENA.** Il n'emprunte rien au SDK : il l'importe au
moment de tourner et rend du JSON sur la sortie standard. Le SDK, lui, reste
hors du depot (`tools/vision/faceplugin/`), parce qu'il **ne porte aucune
licence** — pas de fichier LICENSE, seulement un badge « Open Source » dans son
README, ce qui ne concede rien en droit. Sans licence, tous droits reserves :
copier son source dans un depot public le rendrait indefendable.

L'API reelle du SDK, relevee dans son `run.py` (03/09/2026) :

    GetImageInfo(image, faceMaxCount)
        -> count, bboxes, bscores, landmarks, alignimgs, features
    get_similarity(feat1, feat2) -> (sum(f1 * f2) + 1) * 50

Rien d'autre n'est appele, et aucune fonction n'est inventee.

**Ce pont ne reconnait personne.** Il mesure une image et rend des nombres. Il
n'a pas de base de visages, il n'en constitue pas, et il n'ecrit aucun gabarit
biometrique sur le disque. Comparer exige deux images fournies dans le meme
appel : il n'y a rien a interroger.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List

# Le SDK s'importe depuis le dossier ou ce pont est LANCE, pas depuis celui ou
# il est ecrit. Python ajoute a `sys.path` le repertoire du SCRIPT — donc
# `core/connectors/ponts/`, ou `run.py` n'existe pas : le premier essai a
# rendu `ModuleNotFoundError: No module named 'run'` (mesure du 03/09/2026).
# Le connecteur lance ce pont avec `cwd` a la racine du SDK ; on ajoute donc
# ce dossier-la, et lui seul.
sys.path.insert(0, os.getcwd())

#: Ce qui distingue la reponse du pont du bavardage du moteur.
MARQUEUR = "@@ARENA@@"


def _charger(chemin: str):
    """Lit une image, ou echoue en le disant. Jamais une image vide inventee."""
    import cv2  # importe ici : absent, c'est le SDK qui manque, pas ce pont

    image = cv2.imread(chemin, cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(f"image illisible : {chemin}")
    return image


def _mesurer(chemin: str, maximum: int) -> Dict[str, Any]:
    """Une passe du moteur sur une image, rendue en types JSON."""
    from run import GetImageInfo  # le SDK, importe depuis SON dossier

    count, boxes, scores, landmarks, _alignimgs, features = GetImageInfo(
        _charger(chemin), maximum)

    return {
        "nombre": int(count),
        "boites": [[float(v) for v in b] for b in boxes],
        "scores": [float(s) for s in (s.reshape(-1)[0] for s in scores)],
        "reperes": [[float(v) for v in points.reshape(-1)] for points in landmarks],
        "caracteristiques": [[float(v) for v in f.reshape(-1)] for f in features],
    }


def _sans_caracteristiques(mesure: Dict[str, Any]) -> Dict[str, Any]:
    """La meme mesure, sans les gabarits biometriques.

    `detecter` et `reperes` n'ont aucun besoin des vecteurs de caracteristiques,
    et ce sont eux qui identifient. Les rendre quand meme, « au cas ou », ferait
    voyager de la biometrie a chaque appel de detection — le contraire de ce que
    demande une capacite explicitement declenchee.
    """
    return {cle: valeur for cle, valeur in mesure.items() if cle != "caracteristiques"}


def main(argv: List[str]) -> int:
    parseur = argparse.ArgumentParser(description="Pont ARENA vers le SDK Faceplugin")
    parseur.add_argument("operation", choices=("sante", "detecter", "reperes",
                                               "caracteristiques", "comparer"))
    parseur.add_argument("--image")
    parseur.add_argument("--image2")
    parseur.add_argument("--max", type=int, default=5)
    args = parseur.parse_args(argv)

    try:
        if args.operation == "sante":
            # Importer suffit : c'est ce qui echoue quand torch, opencv ou les
            # poids manquent. On ne declare pas « operationnel » sur la seule
            # presence d'un dossier.
            from run import GetImageInfo  # noqa: F401
            sortie: Dict[str, Any] = {"ok": True}

        elif args.operation in ("detecter", "reperes"):
            sortie = {"ok": True, **_sans_caracteristiques(_mesurer(args.image, args.max))}

        elif args.operation == "caracteristiques":
            sortie = {"ok": True, **_mesurer(args.image, args.max)}

        else:  # comparer
            from run import get_similarity

            a = _mesurer(args.image, 1)
            b = _mesurer(args.image2, 1)
            if a["nombre"] == 0 or b["nombre"] == 0:
                # **Aucun score invente.** Sans visage des deux cotes il n'y a
                # rien a comparer : on le dit, on ne rend pas 0 — un 0 se lirait
                # comme « comparees, tres differentes ».
                sortie = {
                    "ok": False,
                    "erreur": "aucun visage detecte dans "
                              + ("la premiere image" if a["nombre"] == 0 else "la seconde image"),
                    "nombre_image1": a["nombre"],
                    "nombre_image2": b["nombre"],
                }
            else:
                import numpy as np

                score = float(get_similarity(
                    np.array(a["caracteristiques"][0]), np.array(b["caracteristiques"][0])))
                sortie = {
                    "ok": True,
                    "score": score,
                    "echelle": "0-100, mesuree par get_similarity du SDK",
                    "nombre_image1": a["nombre"],
                    "nombre_image2": b["nombre"],
                }
    except Exception as erreur:  # noqa: BLE001 — une panne se rapporte, elle ne se simule pas
        sortie = {"ok": False, "erreur": f"{type(erreur).__name__}: {erreur}"}

    # **Marqueur, parce que le moteur parle sur la meme sortie.** Le SDK
    # imprime « priors nums:4420 » avant de rendre la main (mesure du
    # 03/09/2026), et le connecteur lisait ce melange comme du JSON casse. Un
    # prefixe rend la ligne du pont reconnaissable quoi que le moteur ecrive,
    # avant comme apres.
    sys.stdout.write(MARQUEUR + json.dumps(sortie) + "\n")
    return 0 if sortie.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
