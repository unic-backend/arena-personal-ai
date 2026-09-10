"""Personnage -> image/video : compose des capacites EXISTANTES, n'en cree
aucune (mission ARENA x AGENT HEROES, DEC-0084).

**Le pipeline reel, et ses deux confirmations separees.** ARENA n'a nulle
part de conditionnement par image/seed/embedding pour WanGP
(`core/connectors/wan2gp.py` n'accepte qu'un `source` TEXTE) : la
"coherence" d'un personnage ne peut donc pas venir d'un parametre de
generation qui n'existe pas. Elle vient de deux etapes reelles, chacune deja
cablee et deja gardee par la file de confirmation (`core/actions/attente.py`,
verrouillee) :

1. `soumettre_generation_image` compose un prompt (identite du personnage +
   scene demandee) et le confie a `VideoAnalyzerAgent.planifier_scene` — la
   MEME voie que tout le reste d'ARENA passe par WanGP, jamais un second
   chemin de soumission.
2. Une fois le fichier reellement produit (`suivre_la_generation`, deja
   cable), `appliquer_identite` demande a Xaar Kaname (Deep-Live-Cam) de
   reposer le VISAGE de reference du personnage sur ce fichier — un vrai
   post-traitement, jamais une pretention de conditionnement amont.

**Ce que ceci n'est pas** (mission §6, "expose engine capabilities
truthfully") : ni un entrainement LoRA (aucune capacite d'entrainement
n'existe dans ARENA aujourd'hui — mission §7, etudie, non reproduit), ni une
garantie de ressemblance parfaite — seulement un remplacement de visage
mesurable, sur un plan qui a reellement ete genere.
"""
from __future__ import annotations

import inspect as _inspect
import logging
import uuid
from pathlib import Path
from typing import Any, Dict

from core.characters.registry import Personnage
from core.security.trust import inspect as inspecter_confiance

logger = logging.getLogger("usman.production.personnage_video")


def composer_prompt(personnage: Personnage, description_scene: str) -> Dict[str, Any]:
    """Le prompt WanGP : identite du personnage + scene demandee.

    Ne fabrique jamais la description de scene elle-meme (duree, camera,
    audio restent la responsabilite de l'appelant — `planifier_scene` les
    exige deja via `tools/video/prompt_audit.py`) : ce module ajoute
    seulement les traits d'identite, en prefixe, pour que le sujet decrit
    soit CELUI du personnage plutot qu'un sujet generique.

    `motifs_suspects` releve les tournures d'un profil qui s'adresseraient
    a un modele plutot que de decrire une apparence (`core/security/trust.py`,
    meme discipline que `core/skills/securite.py`) — **releve, jamais
    bloque** : un profil de personnage n'est pas un fichier executable, et
    la decision reste au proprietaire qui l'a ecrit (`TrustLevel.USER`).
    """
    description_scene = (description_scene or "").strip()
    texte_identite = " ".join(
        part for part in (personnage.profil_visuel, personnage.description) if part
    ).strip()

    motifs = list(inspecter_confiance(texte_identite))
    if personnage.negatif:
        motifs.extend(inspecter_confiance(personnage.negatif))

    morceaux = [texte_identite, description_scene]
    if personnage.negatif:
        morceaux.append(f"Eviter : {personnage.negatif}")
    prompt = "\n".join(m for m in morceaux if m)

    return {"prompt": prompt, "motifs_suspects": motifs, "personnage_id": personnage.identifiant}


async def soumettre_generation_image(
    video_agent: Any, personnage: Personnage, description_scene: str,
) -> Dict[str, Any]:
    """Soumet une scene WanGP portant l'identite du personnage.

    **Rien ne part sans confirmation** : `planifier_scene` retombe sur la
    meme file que tout le reste (DEC-0037). Cette fonction ne fait que
    composer le bon prompt avant de le lui confier — jamais un second appel
    au connecteur WanGP.
    """
    if not (description_scene or "").strip():
        return {
            "statut": "INCOMPLET", "personnage_id": personnage.identifiant,
            "message": "Aucune scene a generer : decris ce que le personnage doit faire.",
        }
    compose = composer_prompt(personnage, description_scene)

    resultat = video_agent.planifier_scene(compose["prompt"])
    if _inspect.isawaitable(resultat):
        resultat = await resultat
    resultat = dict(resultat)
    resultat["personnage_id"] = personnage.identifiant
    resultat["motifs_suspects_prompt"] = compose["motifs_suspects"]
    return resultat


async def appliquer_identite(
    registre: Any,
    personnage: Personnage,
    fichier_cible: str,
    dossier_rendu: Path,
    *,
    many_faces: bool = False,
) -> Dict[str, Any]:
    """Repose le visage de reference du personnage sur un fichier DEJA
    produit — jamais sur une tache encore en cours (`fichier_cible` doit
    deja exister sur le disque : c'est a l'appelant de l'avoir obtenu via
    `suivre_la_generation`, jamais suppose ici).

    Passe par le registre, comme `VideoProductionAgent._appeler_xaar_kaname` :
    c'est ce qui fait respecter `video_generation.generate = CONFIRMATION`
    (`config/permissions_services.yaml`). Un appel direct au connecteur
    contournerait cette protection.
    """
    if not personnage.images_reference:
        return {
            "statut": "INCOMPLET", "personnage_id": personnage.identifiant,
            "message": "Ce personnage n'a aucune image de reference : rien a reposer.",
        }
    source = personnage.images_reference[0]
    if not Path(source).is_file():
        return {
            "statut": "ECHEC", "personnage_id": personnage.identifiant,
            "message": f"Image de reference introuvable : {source}",
        }
    if not Path(fichier_cible).is_file():
        return {
            "statut": "ECHEC", "personnage_id": personnage.identifiant,
            "message": f"Fichier cible introuvable : {fichier_cible}",
        }

    dossier_rendu.mkdir(parents=True, exist_ok=True)
    sortie = dossier_rendu / f"personnage-{personnage.identifiant}-{uuid.uuid4().hex[:8]}{Path(fichier_cible).suffix or '.jpg'}"

    resultat = registre.executer(
        "xaar_kaname", "traiter",
        source=str(Path(source).resolve()),
        target=str(Path(fichier_cible).resolve()),
        output=str(sortie),
        many_faces=many_faces,
    )
    if _inspect.isawaitable(resultat):
        resultat = await resultat

    corps = resultat.to_dict() if hasattr(resultat, "to_dict") else dict(resultat or {})
    # `ResultatAction.to_dict()` rend `status` (cle anglaise, valeur anglaise) ;
    # un double de test comme les capacites qui rendent leur reponse en
    # francais directement (`planifier_scene`) rendent deja `statut`. Meme
    # normalisation que `agents/video/production_agent.py:
    # _depuis_resultat_action` — sans elle, un succes reel se lirait absent
    # sous la cle `statut` que `appliquer_identite_personnage` verifie.
    corps["statut"] = corps.get("statut", corps.get("status"))
    corps["personnage_id"] = personnage.identifiant
    return corps
