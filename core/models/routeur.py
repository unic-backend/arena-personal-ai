"""Choisir qui repond : sa machine, ou le reseau.

C'est la piece qui rend ARENA hybride. Le reste du projet continue de parler a
un `ModelProvider` et **ne sait pas** s'il s'adresse a Ollama, a Groq ou a
DeepInfra. C'est voulu : le jour ou un fournisseur change, rien d'autre ne bouge.

L'ordre des questions n'est pas negociable, et il commence par la seule qui ne
se rattrape pas :

1. **Ce texte a-t-il le droit de sortir ?** (`core/models/confidentialite.py`)
   Non → Ollama, et la question est close.
2. **Le proprietaire a-t-il impose un fournisseur ?** AUTO laisse decider.
3. **Reste-t-il du budget ?** Non → Ollama. Un plafond ne casse rien, il fait
   redescendre.
4. **Le service repond-il ?** Sante gardee en memoire quelques secondes : la
   mesurer avant chaque phrase couterait plus cher que ce qu'elle economise.

Puis le repli, dans cet ordre : **Groq → DeepInfra → Ollama**. Il s'arrete au
premier qui repond, et il ne boucle jamais : chaque fournisseur est essaye **une
fois**. Un service qui echoue est mis au frais quelques minutes plutot que
d'etre redemande a chaque phrase.

**Sans reseau, sans cle, budget atteint, ou texte sensible : Ollama.** Dans les
quatre cas ARENA repond. C'est la seule promesse que ce module doit tenir.
"""
import logging
import time
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Dict, List, Optional, Sequence

from core.models.base import ModelProvider
from core.models.confidentialite import Classement, classer, cloud_autorise
from core.models.usage import Appel, CompteurUsage

logger = logging.getLogger("usman.modeles.routeur")

#: Combien de temps une mesure de sante reste valable. La refaire avant chaque
#: phrase couterait plus cher que ce qu'elle economise.
SANTE_VALIDE_SECONDES = 30.0

#: Combien de temps un fournisseur reste au frais apres un echec. Assez pour ne
#: pas le redemander a chaque phrase, assez peu pour qu'il revienne tout seul.
REPOS_APRES_ECHEC_SECONDES = 120.0

#: L'ordre du repli, du plus rapide au plus sur. Ollama est toujours dernier :
#: c'est celui qui repond quand plus rien d'autre ne repond.
ORDRE_CLOUD = ("groq", "deepinfra")
LOCAL = "local"


@dataclass
class EtatFournisseur:
    """Ce qu'on sait d'un fournisseur, sans le redemander a chaque phrase."""

    nom: str
    disponible: Optional[bool] = None
    mesure_le: float = 0.0
    au_frais_jusqu_a: float = 0.0
    dernieres_erreurs: int = 0

    def frais(self, maintenant: float) -> bool:
        """Vrai quand la mesure est encore valable."""
        return (self.disponible is not None
                and maintenant - self.mesure_le < SANTE_VALIDE_SECONDES)

    def au_repos(self, maintenant: float) -> bool:
        return maintenant < self.au_frais_jusqu_a

    def to_dict(self) -> Dict[str, Any]:
        return {"nom": self.nom, "disponible": self.disponible,
                "erreurs_recentes": self.dernieres_erreurs,
                "au_repos": self.au_repos(time.monotonic())}


@dataclass(frozen=True)
class Choix:
    """Le fournisseur retenu, et ce qui l'a designe. Verifiable, pas a croire."""

    fournisseur: str
    raison: str
    classement: Classement
    replis: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {"fournisseur": self.fournisseur, "raison": self.raison,
                "confidentialite": self.classement.niveau.value,
                "replis": list(self.replis)}


class RouteurModeles(ModelProvider):
    """Un `ModelProvider` qui en choisit un autre. Le reste d'ARENA ne voit que lui."""

    def __init__(self, local: ModelProvider,
                 distants: Optional[Dict[str, ModelProvider]] = None,
                 mode: str = "HYBRIDE", fournisseur_demande: str = "AUTO",
                 compteur: Optional[CompteurUsage] = None) -> None:
        self.local = local
        # Seuls les fournisseurs REELLEMENT configures entrent : un service sans
        # cle n'est pas une option a essayer, c'est une option qui n'existe pas.
        self.distants = {
            nom: fournisseur for nom, fournisseur in (distants or {}).items()
            if getattr(fournisseur, "configure", True)
        }
        self.mode = mode
        self.fournisseur_demande = (fournisseur_demande or "AUTO").upper()
        self.compteur = compteur or CompteurUsage()
        self.etats: Dict[str, EtatFournisseur] = {
            nom: EtatFournisseur(nom=nom) for nom in list(self.distants) + [LOCAL]
        }
        #: Le dernier choix, lisible par l'interface et la telemetrie.
        self.dernier_choix: Optional[Choix] = None

    @property
    def model_name(self) -> str:
        """Le modele reellement en service, pour que l'interface dise la verite."""
        choix = self.dernier_choix
        if choix is None or choix.fournisseur == LOCAL:
            return getattr(self.local, "model_name", "local")
        fournisseur = self.distants.get(choix.fournisseur)
        return getattr(fournisseur, "model_name", choix.fournisseur)

    # --- Choisir -------------------------------------------------------------------

    def _candidats(self, classement: Classement) -> tuple:
        """Les fournisseurs a essayer, dans l'ordre, et la raison du premier.

        Rend toujours au moins Ollama : ARENA repond, quoi qu'il arrive.
        """
        autorisation = cloud_autorise(classement, self.mode)
        if not autorisation.autorise:
            return [LOCAL], autorisation.raison

        if self.fournisseur_demande == "LOCAL":
            return [LOCAL], "le proprietaire a demande sa machine"
        if self.fournisseur_demande in ("GROQ", "DEEPINFRA"):
            nom = self.fournisseur_demande.lower()
            if nom in self.distants:
                return [nom, LOCAL], f"le proprietaire a demande {nom}"
            return [LOCAL], f"{nom} n'est pas configure : sa machine repond"

        verdict = self.compteur.verdict()
        if not verdict.autorise:
            return [LOCAL], verdict.raison

        disponibles = [nom for nom in ORDRE_CLOUD if nom in self.distants]
        if not disponibles:
            return [LOCAL], "aucun service distant n'est configure"
        return disponibles + [LOCAL], f"{autorisation.raison}, {disponibles[0]} d'abord"

    async def _joignable(self, nom: str) -> bool:
        """Le fournisseur repond-il ? Mesure gardee, et repos apres un echec."""
        maintenant = time.monotonic()
        etat = self.etats.setdefault(nom, EtatFournisseur(nom=nom))
        if etat.au_repos(maintenant):
            return False
        if etat.frais(maintenant):
            return bool(etat.disponible)

        fournisseur = self.local if nom == LOCAL else self.distants.get(nom)
        if fournisseur is None:
            return False
        try:
            etat.disponible = bool(await fournisseur.is_available())
        except Exception:  # noqa: BLE001 — une sonde qui leve est une indisponibilite
            etat.disponible = False
        etat.mesure_le = maintenant
        if not etat.disponible:
            etat.dernieres_erreurs += 1
            etat.au_frais_jusqu_a = maintenant + REPOS_APRES_ECHEC_SECONDES
        return bool(etat.disponible)

    def _echec(self, nom: str) -> None:
        """Met un fournisseur au frais. Il reviendra tout seul."""
        maintenant = time.monotonic()
        etat = self.etats.setdefault(nom, EtatFournisseur(nom=nom))
        etat.disponible = False
        etat.mesure_le = maintenant
        etat.dernieres_erreurs += 1
        etat.au_frais_jusqu_a = maintenant + REPOS_APRES_ECHEC_SECONDES

    def _fournisseur(self, nom: str) -> ModelProvider:
        return self.local if nom == LOCAL else self.distants[nom]

    def _noter(self, nom: str, classement: Classement, repli: bool, succes: bool) -> None:
        """Compte l'appel distant. Le local ne coute rien : il n'est pas compte."""
        if nom == LOCAL:
            return
        fournisseur = self.distants.get(nom)
        mesure = getattr(fournisseur, "derniere_mesure", None)
        self.compteur.enregistrer(Appel(
            fournisseur=nom,
            modele=getattr(fournisseur, "model_name", nom),
            classement=classement.niveau.value,
            jetons_entree=getattr(mesure, "jetons_entree", None),
            jetons_sortie=getattr(mesure, "jetons_sortie", None),
            secondes=getattr(mesure, "secondes_total", None),
            repli=repli, succes=succes,
        ))

    # --- Repondre --------------------------------------------------------------------

    def _pourquoi_personne(self, classement: Classement, candidats: Sequence[str],
                           essayes: Sequence[str]) -> str:
        """La phrase d'echec : sa cause, et ce qui la leverait.

        Un `RuntimeError` nu — « Aucun fournisseur n'a pu repondre. » — ne
        distingue pas **« ce modele n'existe pas sur cette machine »** de
        **« tout est tombe une minute »**. La difference est celle entre une
        panne qu'on attend et une panne qu'on ne verra jamais passer.

        Mesure du 30/08/2026 (`scripts/mesurer_sans_ollama.py`) : sur un
        serveur sans Ollama, une demande classee `SENSIBLE` est routee vers la
        machine du proprietaire **et vers elle seule**, qui n'existe pas la.
        L'echec est alors permanent, et l'ancien message aurait envoye le
        proprietaire chercher une coupure reseau.
        """
        phrases = ["Aucun fournisseur n'a pu repondre."]
        if essayes:
            phrases.append(f"Essayes : {', '.join(essayes)}.")

        if list(candidats) == [LOCAL]:
            # Le cloud n'a meme pas ete tente : c'est le classement qui a
            # ferme la porte, pas une panne. Le dire, sinon on cherche ailleurs.
            _, raison = self._candidats(classement)
            adresse = getattr(self.local, "base_url", "") or "sa machine"
            phrases.append(f"Seule sa machine etait autorisee ({raison}), "
                           f"et {adresse} ne repond pas.")
            if cloud_autorise(classement, "CLOUD_PREFERRED").autorise:
                phrases.append("En mode CLOUD_PREFERRED, cette demande aurait pu "
                               "partir chez un service distant.")
        elif LOCAL in essayes:
            adresse = getattr(self.local, "base_url", "") or "sa machine"
            phrases.append(f"Sa machine ({adresse}) ne repond pas non plus.")
        return " ".join(phrases)

    async def generate(self, prompt: str, system_prompt: Optional[str] = None,
                       contexte: Optional[Sequence[str]] = None) -> str:
        """Repond, en essayant chaque fournisseur **une fois**.

        Args:
            contexte: ce qui part AVEC la demande — souvenirs, pieces jointes.
                Il compte dans le classement : une question anodine posee sur un
                document de client ne l'est pas.
        """
        classement = classer(prompt, contexte)
        candidats, raison = self._candidats(classement)
        essayes: List[str] = []

        for index, nom in enumerate(candidats):
            if nom != LOCAL and not await self._joignable(nom):
                essayes.append(nom)
                continue
            try:
                reponse = await self._fournisseur(nom).generate(prompt, system_prompt)
            except Exception as erreur:  # noqa: BLE001 — on replie, on ne remonte pas
                logger.info("%s a echoue (%s), repli.", nom, type(erreur).__name__)
                self._echec(nom)
                self._noter(nom, classement, repli=index > 0, succes=False)
                essayes.append(nom)
                continue
            if not (reponse or "").strip():
                # Meme regle que pour le flux : une reponse vide laisse son
                # ecran vide. On replie, sans mettre le fournisseur au frais.
                logger.info("%s a rendu une reponse vide, repli.", nom)
                self._noter(nom, classement, repli=index > 0, succes=False)
                essayes.append(nom)
                continue
            self.dernier_choix = Choix(nom, raison, classement, essayes)
            self._noter(nom, classement, repli=index > 0, succes=True)
            return reponse

        # Tous ont echoue, Ollama compris : on le dit, on n'invente pas de reponse.
        self.dernier_choix = Choix(LOCAL, "tous les fournisseurs ont echoue",
                                   classement, essayes)
        raise RuntimeError(self._pourquoi_personne(classement, candidats, essayes))

    async def generate_stream(self, prompt: str, system_prompt: Optional[str] = None,
                              contexte: Optional[Sequence[str]] = None
                              ) -> AsyncGenerator[str, None]:
        """Le flux du fournisseur retenu.

        **Le repli n'a lieu qu'avant le premier mot.** Une fois qu'un morceau est
        parti vers son ecran, recommencer chez un autre lui ferait lire deux
        debuts de reponse.
        """
        classement = classer(prompt, contexte)
        candidats, raison = self._candidats(classement)
        essayes: List[str] = []

        for index, nom in enumerate(candidats):
            if nom != LOCAL and not await self._joignable(nom):
                essayes.append(nom)
                continue
            fournisseur = self._fournisseur(nom)
            flux = getattr(fournisseur, "generate_stream", None)
            commence = False
            try:
                if flux is None:
                    # Un fournisseur sans streaming rend sa reponse d'un bloc :
                    # c'est degrade, ce n'est pas une panne.
                    texte = await fournisseur.generate(prompt, system_prompt)
                    self.dernier_choix = Choix(nom, raison, classement, essayes)
                    self._noter(nom, classement, repli=index > 0, succes=True)
                    yield texte
                    return
                async for morceau in flux(prompt, system_prompt):
                    if not commence:
                        commence = True
                        self.dernier_choix = Choix(nom, raison, classement, essayes)
                    yield morceau
            except Exception as erreur:  # noqa: BLE001
                if commence:
                    # Trop tard pour replier : la reponse a commence.
                    self._echec(nom)
                    self._noter(nom, classement, repli=index > 0, succes=False)
                    raise
                logger.info("%s a echoue avant le premier mot (%s), repli.",
                            nom, type(erreur).__name__)
                self._echec(nom)
                self._noter(nom, classement, repli=index > 0, succes=False)
                essayes.append(nom)
                continue
            if not commence:
                # Un flux qui se termine sans un seul morceau n'est pas une
                # reponse : l'ecran reste vide, et `dernier_choix` gardait la
                # valeur du TOUR PRECEDENT — l'interface nommait alors le
                # mauvais moteur. Rien n'etant parti vers son ecran, le repli
                # est encore permis, et c'est exactement le moment ou il l'est.
                #
                # Sans `_echec` toutefois : un flux vide est une mauvaise
                # reponse, pas une indisponibilite prouvee. Mettre LOCAL au
                # frais ferait dire a `is_available()` « Ollama hors-ligne »
                # pendant deux minutes alors qu'Ollama repond — ARENA dirait
                # quelque chose de faux sur sa propre machine.
                logger.info("%s a rendu un flux vide, repli.", nom)
                self._noter(nom, classement, repli=index > 0, succes=False)
                essayes.append(nom)
                continue
            self._noter(nom, classement, repli=index > 0, succes=True)
            return

        self.dernier_choix = Choix(LOCAL, "tous les fournisseurs ont echoue",
                                   classement, essayes)
        raise RuntimeError(self._pourquoi_personne(classement, candidats, essayes))

    async def is_available(self) -> bool:
        """ARENA peut-il repondre ? Vrai des qu'un seul fournisseur repond."""
        for nom in list(self.distants) + [LOCAL]:
            if await self._joignable(nom):
                return True
        return False

    # --- Ce que l'interface peut montrer -----------------------------------------------

    def etat(self) -> Dict[str, Any]:
        """L'etat lisible : qui a repondu, avec quoi, et ce que le cloud a coute."""
        return {
            "mode": self.mode,
            "fournisseur_demande": self.fournisseur_demande,
            "dernier_choix": self.dernier_choix.to_dict() if self.dernier_choix else None,
            "modele": self.model_name,
            "fournisseurs": [etat.to_dict() for etat in self.etats.values()],
            "usage": self.compteur.resume(),
        }
