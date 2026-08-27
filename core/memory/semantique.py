"""Retrouver un souvenir sur le sens, pas seulement sur les mots.

La recuperation lexicale (`core/memory/recuperation.py`) compare des mots. Elle
rate ce qui est dit autrement : « combien de plaques » ne partage aucun mot
utile avec « BA13 commandees pour le chantier ». Ce module ajoute un cinquieme
signal, mesure par des embeddings **locaux**, servis par Ollama sur la machine
du proprietaire. Rien ne sort.

**Quatre regles, et la premiere commande les autres :**

1. **Une capacite se mesure, elle ne se suppose pas.** L'etat des embeddings
   vient d'un vecteur reellement obtenu du serveur, jamais du fait qu'un port
   reponde ou qu'un nom de modele soit ecrit dans une variable.

2. **Indisponible se dit, ne se contourne pas en silence.** Sans embeddings, la
   recuperation reste lexicale et le resultat porte `mode="LEXICAL"` avec la
   raison mesuree. Un classement semantique n'est jamais simule.

3. **Le budget reste une limite dure.** Comme en lexical : un souvenir qui
   ferait deborder n'est pas tronque, il n'est pas pris.

4. **Un vecteur de mauvaise forme est refuse.** Dimension differente, valeurs
   illisibles, liste vide : le souvenir n'est pas note semantiquement plutot
   que de l'etre sur un vecteur douteux.
"""
import hashlib
import logging
import math
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Awaitable, Callable, Dict, List, Optional, Sequence

import httpx

from core.memory.personnelle import MemoirePersonnelle, TypeSouvenir
from core.memory.recuperation import (
    BUDGET_PAR_DEFAUT,
    SEUIL,
    Resultat,
    fenetre_evoquee,
    mots_utiles,
    noter,
    rendre_ligne,
)

logger = logging.getLogger("usman.memoire.semantique")

#: Ou tourne Ollama, et avec quel modele d'embeddings. Meme convention que
#: `apps/backend/config.py` : la valeur vit dans l'environnement, pas dans le code.
OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
MODELE_EMBEDDINGS = os.getenv("EMBEDDINGS_LOCAL_MODEL", "bge-m3")

#: Poids du classement quand le sens est disponible. Ils somment a 1, et sont
#: ecrits ici plutot que d'ecraser ceux de la recuperation lexicale : les deux
#: classements coexistent, celui qui s'applique est dit dans le resultat.
POIDS_SEMANTIQUE = {
    "correspondance": 0.30,
    "semantique": 0.30,
    "importance": 0.15,
    "recence": 0.10,
    "temporel": 0.15,
}

#: Seuil mesure, pas choisi. Sur la machine du proprietaire, le 2026-08-27,
#: avec bge-m3 : les souvenirs pertinents sortent entre 0,515 et 0,747, les
#: souvenirs sans rapport plafonnent a 0,392. La valeur tient entre les deux.
#: Elle appartient au modele : nomic-embed-text melangeait les deux paquets
#: autour de 0,55, et n avait donc aucun seuil utilisable.
SEUIL_SEMANTIQUE = 0.45

#: Texte envoye pour mesurer la capacite. Court : la mesure ne doit rien couter.
SONDE = "test"

ETAT_DISPONIBLE = "DISPONIBLE"
ETAT_SERVEUR_ABSENT = "SERVEUR_ABSENT"
ETAT_MODELE_ABSENT = "MODELE_ABSENT"
ETAT_REPONSE_INVALIDE = "REPONSE_INVALIDE"


# --- L'etat mesure -------------------------------------------------------------

@dataclass(frozen=True)
class EtatEmbeddings:
    """Ce que la machine sait vraiment faire, constate et non declare."""

    disponible: bool
    etat: str
    detail: str
    modele: str
    dimension: Optional[int] = None

    def __str__(self) -> str:
        if self.disponible:
            return f"{self.etat} ({self.modele}, dimension {self.dimension})"
        return f"{self.etat} — {self.detail}"


def _vecteurs_de(charge: object) -> List[List[float]]:
    """Extrait les vecteurs d'une reponse Ollama, quelle que soit sa forme.

    `/api/embed` rend `embeddings` (une liste de vecteurs), `/api/embeddings`
    rend `embedding` (un seul). Une reponse sans vecteur exploitable rend une
    liste vide : c'est un refus, pas un zero.
    """
    if not isinstance(charge, dict):
        return []
    brut = charge.get("embeddings")
    if brut is None:
        unique = charge.get("embedding")
        brut = [unique] if unique is not None else None
    if not isinstance(brut, list) or not brut:
        return []
    vecteurs: List[List[float]] = []
    for element in brut:
        if not isinstance(element, list) or not element:
            return []
        try:
            vecteurs.append([float(valeur) for valeur in element])
        except (TypeError, ValueError):
            return []
    return vecteurs


async def embeddings_ollama(
    textes: Sequence[str],
    base_url: str = OLLAMA_URL,
    modele: str = MODELE_EMBEDDINGS,
    timeout: float = 30.0,
) -> List[List[float]]:
    """Demande les vecteurs a Ollama. Rend une liste vide si rien d'exploitable.

    Aucune exception ne remonte : l'absence de capacite est un etat rapporte,
    pas une panne propagee au chemin de reponse.
    """
    if not textes:
        return []
    url = f"{base_url.rstrip('/')}/api/embed"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            reponse = await client.post(url, json={"model": modele, "input": list(textes)})
            if reponse.status_code == 404:
                # Ollama ancien : un texte par appel, sur l'autre route.
                anciens: List[List[float]] = []
                for texte in textes:
                    seule = await client.post(
                        f"{base_url.rstrip('/')}/api/embeddings",
                        json={"model": modele, "prompt": texte},
                    )
                    seule.raise_for_status()
                    vecteur = _vecteurs_de(seule.json())
                    if not vecteur:
                        return []
                    anciens.append(vecteur[0])
                return anciens
            reponse.raise_for_status()
            return _vecteurs_de(reponse.json())
    except Exception as erreur:  # noqa: BLE001 — toute panne est un etat, pas un crash
        logger.debug("Embeddings indisponibles : %s", erreur)
        return []


#: Signature d'un fournisseur de vecteurs. Injectable, pour que les tests
#: mesurent le classement sans dependre d'un serveur.
Fournisseur = Callable[[Sequence[str]], Awaitable[List[List[float]]]]


async def mesurer(fournisseur: Optional[Fournisseur] = None, modele: str = MODELE_EMBEDDINGS) -> EtatEmbeddings:
    """Interroge le fournisseur et rapporte ce qu'il a reellement rendu."""
    fournisseur = fournisseur or embeddings_ollama
    vecteurs = await fournisseur([SONDE])
    if not vecteurs:
        return EtatEmbeddings(
            disponible=False,
            etat=ETAT_SERVEUR_ABSENT,
            detail=f"aucun vecteur rendu par {modele} — serveur arrete ou modele non installe",
            modele=modele,
        )
    dimension = len(vecteurs[0])
    if dimension < 2:
        return EtatEmbeddings(
            disponible=False,
            etat=ETAT_REPONSE_INVALIDE,
            detail=f"vecteur de dimension {dimension}, inexploitable",
            modele=modele,
        )
    return EtatEmbeddings(
        disponible=True,
        etat=ETAT_DISPONIBLE,
        detail="vecteur obtenu",
        modele=modele,
        dimension=dimension,
    )


# --- L'index, et son cache -----------------------------------------------------

def _empreinte(texte: str) -> str:
    return hashlib.sha256(texte.strip().lower().encode("utf-8")).hexdigest()


def cosinus(a: Sequence[float], b: Sequence[float]) -> float:
    """Proximite de deux vecteurs, ramenee dans [0, 1].

    Deux vecteurs de dimensions differentes ne se comparent pas : le resultat
    est 0, jamais une valeur obtenue en tronquant l'un des deux.
    """
    if len(a) != len(b) or not a:
        return 0.0
    produit = sum(x * y for x, y in zip(a, b, strict=True))
    norme_a = math.sqrt(sum(x * x for x in a))
    norme_b = math.sqrt(sum(y * y for y in b))
    if norme_a == 0.0 or norme_b == 0.0:
        return 0.0
    return max(0.0, produit / (norme_a * norme_b))


@dataclass
class IndexSemantique:
    """Garde les vecteurs deja calcules, pour ne pas les redemander.

    Le cache vit en memoire et suit l'empreinte du texte : un souvenir modifie
    est re-vectorise, un souvenir inchange ne coute rien la seconde fois.
    """

    fournisseur: Optional[Fournisseur] = None
    cache: Dict[str, List[float]] = field(default_factory=dict)
    appels: int = 0

    async def vecteurs(self, textes: Sequence[str]) -> Dict[str, List[float]]:
        """Rend les vecteurs des textes demandes, en n'appelant que les inconnus."""
        fournisseur = self.fournisseur or embeddings_ollama
        manquants = []
        for texte in textes:
            empreinte = _empreinte(texte)
            if empreinte not in self.cache and texte not in manquants:
                manquants.append(texte)
        if manquants:
            self.appels += 1
            obtenus = await fournisseur(manquants)
            if len(obtenus) == len(manquants):
                for texte, vecteur in zip(manquants, obtenus, strict=True):
                    self.cache[_empreinte(texte)] = vecteur
            else:
                logger.debug("Vecteurs incomplets : %s demandes, %s rendus.",
                             len(manquants), len(obtenus))
        return {
            texte: self.cache[_empreinte(texte)]
            for texte in textes
            if _empreinte(texte) in self.cache
        }


# --- Le classement --------------------------------------------------------------

MODE_SEMANTIQUE = "SEMANTIQUE"
MODE_LEXICAL = "LEXICAL"


@dataclass(frozen=True)
class Recuperation:
    """Les souvenirs retenus, et sous quel regime ils ont ete classes."""

    mode: str
    etat: EtatEmbeddings
    resultats: List[Resultat]

    def pourquoi(self) -> str:
        return f"{self.mode} — {self.etat}"


async def recuperer_semantique(
    memoire: MemoirePersonnelle,
    question: str,
    index: Optional[IndexSemantique] = None,
    budget_caracteres: int = BUDGET_PAR_DEFAUT,
    projet: Optional[str] = None,
    type: Optional[TypeSouvenir] = None,
    limite_lecture: int = 500,
    maintenant: Optional[datetime] = None,
) -> Recuperation:
    """Classe les souvenirs sur cinq signaux quand le sens est mesurable.

    Quand il ne l'est pas, rend exactement ce que rend la recuperation lexicale,
    avec `mode="LEXICAL"` et la raison mesuree. Aucun classement semantique n'est
    approche, devine ou simule.
    """
    from core.memory.recuperation import recuperer  # import local : evite un cycle

    index = index or IndexSemantique()
    maintenant = maintenant or datetime.now(timezone.utc)

    etat = await mesurer(index.fournisseur)
    if not etat.disponible:
        lexical = recuperer(
            memoire, question, budget_caracteres=budget_caracteres, projet=projet,
            type=type, limite_lecture=limite_lecture, maintenant=maintenant,
        )
        return Recuperation(mode=MODE_LEXICAL, etat=etat, resultats=lexical)

    candidats = memoire.souvenirs(projet=projet, type=type, limite=limite_lecture)
    if not candidats:
        return Recuperation(mode=MODE_SEMANTIQUE, etat=etat, resultats=[])

    mots_question = mots_utiles(question)
    fenetre = fenetre_evoquee(question, maintenant)

    textes = [question] + [souvenir.contenu for souvenir in candidats]
    connus = await index.vecteurs(textes)
    vecteur_question = connus.get(question, [])

    notes: List[Resultat] = []
    for souvenir in candidats:
        lexicale = noter(souvenir, mots_question, fenetre, maintenant)
        vecteur = connus.get(souvenir.contenu, [])
        proximite = cosinus(vecteur_question, vecteur) if vecteur_question else 0.0
        signaux = dict(lexicale.signaux)
        signaux["semantique"] = proximite
        score = sum(POIDS_SEMANTIQUE[nom] * valeur for nom, valeur in signaux.items())
        notes.append(Resultat(souvenir=souvenir, score=score, signaux=signaux))

    notes = [resultat for resultat in notes if resultat.score >= SEUIL]

    # Meme regle qu'en lexical : sans lien avec la question, un souvenir reste ou
    # il est. Le sens est un lien de plus, pas une porte ouverte a la recence.
    if not projet:
        notes = [
            resultat for resultat in notes
            if resultat.signaux["correspondance"] > 0
            or resultat.signaux["temporel"] > 0
            or resultat.signaux["semantique"] >= SEUIL_SEMANTIQUE
        ]

    notes.sort(key=lambda resultat: resultat.score, reverse=True)

    retenus: List[Resultat] = []
    total = 0
    for resultat in notes:
        cout = len(rendre_ligne(resultat.souvenir)) + 1
        if total + cout > budget_caracteres:
            continue  # jamais tronque : pas pris
        retenus.append(resultat)
        total += cout

    logger.debug("Recuperation semantique : %s candidat(s), %s retenu(s), %s caracteres.",
                 len(candidats), len(retenus), total)
    return Recuperation(mode=MODE_SEMANTIQUE, etat=etat, resultats=retenus)
