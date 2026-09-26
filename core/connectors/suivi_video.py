"""Suivre une generation video jusqu'au fichier, sans faire attendre le chat.

`wangp_generate` rend un identifiant de tache et rend la main. Sans personne
pour le suivre, le proprietaire devrait redemander « ou en est ma video ? » —
et c'est exactement ce qu'un assistant est cense eviter.

Ce module fait le pont entre le connecteur WanGP et la file de travaux de fond
(`core/execution/travaux.py`). C'est le premier usage reel de cette file.

**Quatre regles :**

1. **Le chat n'attend jamais.** Le suivi tourne dans la file de fond ; la
   conversation continue pendant que la carte graphique travaille.

2. **La progression vient de WanGP, pas d'une estimation.** `total_tasks` et
   `successful_tasks` quand ils existent, `None` tant qu'ils n'existent pas.
   Une barre qui avance toute seule serait une invention.

3. **Un suivi qui n'aboutit pas le dit.** Plafond de duree, plafond d'erreurs
   consecutives : au-dela, le travail echoue avec sa raison plutot que de
   tourner indefiniment.

4. **Aucune confirmation n'est contournee ici.** Ce module ne lance pas de
   generation : il suit une tache **deja acceptee** par WanGP, donc deja passee
   par la confirmation du proprietaire.
"""
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from core.execution.travaux import FileDeTravaux, Travail

logger = logging.getLogger("usman.connecteurs.suivi_video")

#: Le type de ce travail dans le journal durable de la file
#: (`core/execution/travaux.py`). Une constante, parce que la fabrique de
#: reprise et le descripteur doivent employer EXACTEMENT le meme mot : deux
#: chaines ecrites a deux endroits finiraient par diverger, et la reprise
#: echouerait en silence sur un type « inconnu ».
TYPE_REPRISE = "suivi_generation_video"

#: Entre deux interrogations. Une generation dure des minutes : sonder plus vite
#: ne la rend pas plus rapide, ca ajoute seulement du bruit.
INTERVALLE_SECONDES = 5.0

#: Au-dela, on cesse de suivre et on le dit. Une generation longue reste
#: possible chez WanGP ; c'est le SUIVI qui s'arrete, pas elle.
PLAFOND_SECONDES = 3600.0

#: Erreurs d'affilee tolerees avant d'abandonner le suivi. Une reponse ratee
#: arrive ; dix d'affilee veut dire que WanGP n'est plus la.
ERREURS_TOLEREES = 5


@dataclass
class Suivi:
    """Ce qu'une generation a produit, ou pourquoi elle n'a rien produit."""

    job_id: str
    termine: bool = False
    reussi: bool = False
    annule: bool = False
    fichiers: List[str] = field(default_factory=list)
    raison: str = ""
    interrogations: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id, "termine": self.termine, "reussi": self.reussi,
            "annule": self.annule, "fichiers": self.fichiers, "raison": self.raison,
        }


def _avancer(travail: Optional[Travail], instantane: Dict[str, Any]) -> None:
    """Reporte la progression annoncee par WanGP sur le travail de fond.

    Tant que WanGP ne donne pas de compte, `total` reste `None` : un total
    inconnu ne devient jamais zero.
    """
    if travail is None:
        return
    resultat = instantane.get("result")
    if not isinstance(resultat, dict):
        return
    total = resultat.get("total_tasks")
    faits = resultat.get("successful_tasks")
    if isinstance(total, int) and total > 0:
        travail.total = total
    if isinstance(faits, int) and faits >= 0:
        travail.faits = faits


async def suivre_generation(
    connecteur: Any,
    job_id: str,
    travail: Optional[Travail] = None,
    intervalle: float = INTERVALLE_SECONDES,
    plafond: float = PLAFOND_SECONDES,
) -> Suivi:
    """Interroge WanGP jusqu'a ce que la tache soit finie, ou que le plafond tombe.

    Args:
        connecteur: le `Wan2GPConnector`.
        job_id: la tache rendue par `generer`.
        travail: le travail de fond a faire avancer, s'il y en a un.
        intervalle: secondes entre deux interrogations.
        plafond: duree maximale du suivi.

    Returns:
        Le `Suivi`. `reussi` n'est vrai que si WanGP l'a dit lui-meme.
    """
    if not job_id:
        return Suivi(job_id="", termine=True, raison="aucun identifiant de tache a suivre")

    suivi = Suivi(job_id=job_id)
    ecoule = 0.0
    erreurs = 0

    while ecoule <= plafond:
        resultat = connecteur.executer("etat_travail", job_id=job_id)
        suivi.interrogations += 1
        instantane = (resultat.detail or {}).get("donnees")

        # Un instantane exploitable porte au moins l'un des deux : `done` (ou
        # en est la tache) ou `result` (ce qu'elle a produit). Un dictionnaire
        # qui n'a ni l'un ni l'autre n'est pas « pas encore fini » : il est
        # illisible, et le compter comme une attente ferait tourner le suivi
        # jusqu'au plafond pour rien.
        lisible = isinstance(instantane, dict) and (
            "done" in instantane or "result" in instantane)
        if not lisible:
            erreurs += 1
            if erreurs >= ERREURS_TOLEREES:
                suivi.termine = True
                suivi.raison = f"WanGP n'a rien rendu d'exploitable apres {erreurs} essais"
                return suivi
        else:
            erreurs = 0
            _avancer(travail, instantane)
            if instantane.get("done"):
                fin = instantane.get("result")
                fin = fin if isinstance(fin, dict) else {}
                suivi.termine = True
                suivi.annule = bool(fin.get("cancelled") or instantane.get("cancel_requested"))
                suivi.reussi = bool(fin.get("success")) and not suivi.annule
                suivi.fichiers = [str(chemin) for chemin in (fin.get("generated_files") or [])]
                if not suivi.reussi and not suivi.raison:
                    erreurs_wangp = fin.get("errors") or []
                    suivi.raison = ("generation annulee" if suivi.annule
                                    else f"WanGP rapporte {len(erreurs_wangp)} erreur(s)")
                logger.info("Generation %s terminee : %s fichier(s).", job_id, len(suivi.fichiers))
                return suivi

        await asyncio.sleep(intervalle)
        ecoule += intervalle

    suivi.termine = True
    suivi.raison = f"suivi abandonne apres {plafond:.0f} s — la generation continue peut-etre chez WanGP"
    return suivi


def suivre_en_fond(
    connecteur: Any,
    file: FileDeTravaux,
    job_id: str,
    nom: str = "generation video",
    intervalle: float = INTERVALLE_SECONDES,
) -> Travail:
    """Met le suivi dans la file de fond et rend la main **immediatement**.

    C'est ici que la file de travaux de fond sert enfin a quelque chose de reel.
    """
    return file.soumettre(
        nom,
        lambda travail: suivre_generation(connecteur, job_id, travail, intervalle),
        passer_le_travail=True,
        # La cle, c'est la tache WanGP : deux suivis de la MEME generation ne
        # sont pas deux travaux, c'est le meme demande deux fois.
        cle=f"{TYPE_REPRISE}:{job_id}",
        # Ce travail est le seul du depot qui se reprend REELLEMENT apres un
        # redemarrage : son etat ne vit pas ici, il vit chez WanGP. Reprendre,
        # c'est simplement redemander « ou en est la tache job_id ? ».
        # Le GENERATEUR est retenu avec la tache : un `job_id` MoneyPrinter
        # redemande a WanGP ne rend rien. Sans son nom, la reprise ne saurait
        # pas a qui reposer la question.
        descripteur={
            "type": TYPE_REPRISE,
            "parametres": {"job_id": job_id, "nom": nom, "intervalle": intervalle,
                           "connecteur": str(getattr(connecteur, "nom", "") or "")},
            "passer_le_travail": True,
        },
    )


def fabrique_de_reprise(trouver_connecteur: Callable[[str], Any]):
    """Reconstruit un suivi a partir de son descripteur, pour le demarrage.

    Rendue a `FileDeTravaux.reprendre_les_interrompus` : le journal porte
    `job_id`, l'intervalle et le NOM du generateur ; le connecteur, lui, est
    retrouve ici par ce nom, au moment de la reprise. C'est ce qui permet de
    reprendre sans avoir jamais serialise une closure.

    **Mesure du 26/09/2026.** Cette fabrique recevait un connecteur fige au
    demarrage, `registre.obtenir("video_generation")` — un nom de SERVICE,
    pas de connecteur : `None`. Le seul travail de ce depot qui se reprend
    reellement echouait donc sur `None.executer` a chaque redemarrage. Et
    meme le bon connecteur n'aurait pas suffi : un suivi MoneyPrinter repris
    chez WanGP ne rend rien.

    Args:
        trouver_connecteur: `nom -> connecteur` (le `obtenir` du registre),
            `None` quand le nom est inconnu ou le connecteur hors service.
    """

    def fabriquer(parametres: Dict[str, Any]):
        job_id = str(parametres.get("job_id", ""))
        intervalle = float(parametres.get("intervalle", INTERVALLE_SECONDES))
        if not job_id:
            raise ValueError("un suivi sans job_id ne se reprend pas")
        nom = str(parametres.get("connecteur", "") or "")
        connecteur = trouver_connecteur(nom)
        if connecteur is None:
            # Mieux vaut rester INTERROMPU, visible, que tourner sur un
            # connecteur absent jusqu'au plafond d'erreurs.
            raise ValueError(f"generateur {nom!r} introuvable : le suivi {job_id} "
                             "ne se reprend pas")
        return lambda travail: suivre_generation(
            connecteur, job_id, travail, intervalle)

    return fabriquer
