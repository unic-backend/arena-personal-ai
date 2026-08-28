"""Connecteur agenda — savoir quand il est libre, et ne rien poser sans son accord.

Chapitre 9.1. Le proprietaire pose des cloisons : ce qu'il demande a un agenda,
ce n'est pas une jolie grille, c'est **« quand puis-je caser ce chantier ? »** et
**« est-ce que ca tombe sur autre chose ? »**. Ce module repond a ces deux
questions-la, et sait poser un rendez-vous — derriere confirmation.

L'identifiant Google est le meme que celui du courrier : un seul client OAuth,
deux portees (`core/connectors/google_oauth.py`).

**Cinq regles :**

1. **Un creneau n'est libre que si RIEN ne le chevauche.** Pas « rien de
   marque » : un evenement sans heure de fin, ou etale sur la journee entiere,
   bloque ce qu'il recouvre. Un agenda qui annonce libre un jour occupe envoie
   quelqu'un sur un chantier ou il est deja attendu ailleurs.

2. **Les heures ouvrees sont declarees, pas supposees.** Elles vivent en haut de
   ce fichier, lisibles et modifiables. Proposer 3 h du matin parce que
   « c'est libre » serait exact et inutilisable.

3. **Une date qu'on ne sait pas lire est ignoree, et l'ignorance se compte.**
   Elle ne devient jamais « maintenant » ni « toute la journee » : le rapport
   dit combien d'evenements n'ont pas pu etre lus.

4. **Ecrire est une confirmation.** `creer` porte `action="create"`, que la
   politique classe en CONFIRMATION. Modifier et supprimer ne sont pas
   declares : ils n'existent pas.

5. **Sans identifiants, `NOT_CONFIGURED`.** Jamais un agenda vide, qui se
   lirait « ta semaine est libre ».
"""
import logging
import os
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from datetime import time as heure_du_jour
from typing import Any, Callable, Dict, List, Optional, Tuple

import httpx

from core.actions.resultat import ResultatAction, echec, non_configure, succes
from core.connectors.base import Capacite, Connecteur, EtatSante, Sante
from core.connectors.google_oauth import JetonGoogle, manquantes

logger = logging.getLogger("usman.connecteurs.calendrier")

BASE_URL = os.getenv("CALENDAR_API_URL", "https://www.googleapis.com/calendar/v3")

#: L'agenda interroge. `primary` est celui du compte, celui qu'il regarde.
AGENDA = os.getenv("CALENDAR_ID", "primary")

CE_QUI_MANQUE = (
    "trois valeurs dans .env, obtenues sur console.cloud.google.com (API "
    "Google Calendar activee, identifiant OAuth « application de bureau ») : "
    "GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET et GOOGLE_REFRESH_TOKEN. Portee "
    "calendar.readonly pour lire ; calendar.events en plus pour poser un "
    "rendez-vous. Aucune ne s'ecrit dans le depot."
)

#: Sa journee de travail. **Declaree ici**, pas devinee : un creneau a 3 h du
#: matin serait exact et inutilisable.
HEURE_DEBUT = int(os.getenv("AGENDA_HEURE_DEBUT", "8"))
HEURE_FIN = int(os.getenv("AGENDA_HEURE_FIN", "18"))

#: Les jours travailles, 0 = lundi. Le dimanche est exclu par defaut.
JOURS_OUVRES = (0, 1, 2, 3, 4, 5)

#: Duree minimale d'un creneau qui vaut la peine d'etre propose. En dessous, on
#: ne deplace pas une equipe.
DUREE_MINIMALE_MINUTES = 60

#: Plafond que nous nous imposons : interroger l'agenda en boucle ne le rend pas
#: plus a jour.
QUOTA_PAR_MINUTE = 60

#: Poser un rendez-vous est plus rare, et plus cher a defaire.
CREATIONS_PAR_MINUTE = 5

DELAI_SECONDES = 15.0
DUREE_SONDE_SECONDES = 60.0

#: Combien d'evenements sont lus au maximum pour une fenetre.
EVENEMENTS_MAX = 250


# --- Lire une date de Google -------------------------------------------------------

def _instant(brut: Optional[Dict[str, Any]]) -> Optional[datetime]:
    """Un `start`/`end` de Google en datetime, ou `None` si illisible.

    Google rend `dateTime` (avec fuseau) pour un evenement horaire, et `date`
    pour un evenement sur la journee entiere. Les deux se lisent ; ce qu'on ne
    sait pas lire rend `None`, et l'appelant le compte au lieu de l'oublier.
    """
    if not isinstance(brut, dict):
        return None
    horaire = brut.get("dateTime")
    if isinstance(horaire, str) and horaire:
        try:
            lu = datetime.fromisoformat(horaire.replace("Z", "+00:00"))
        except ValueError:
            return None
        return lu if lu.tzinfo else lu.replace(tzinfo=timezone.utc)

    journee = brut.get("date")
    if isinstance(journee, str) and journee:
        try:
            jour = date.fromisoformat(journee)
        except ValueError:
            return None
        # Un evenement « journee entiere » occupe la journee entiere : Google
        # rend `end.date` au LENDEMAIN, donc minuit a minuit couvre bien le
        # jour. Le compter comme un point laisserait l'apres-midi libre.
        return datetime.combine(jour, heure_du_jour(0, 0), tzinfo=timezone.utc)
    return None


@dataclass(frozen=True)
class Occupation:
    """Un moment pris, avec ce qui le prend."""

    debut: datetime
    fin: datetime
    titre: str

    def chevauche(self, debut: datetime, fin: datetime) -> bool:
        """Vrai si les deux intervalles se touchent autrement que bout a bout."""
        return self.debut < fin and debut < self.fin


@dataclass(frozen=True)
class Lecture:
    """Ce qui a ete lu, et ce qui n'a pas pu l'etre."""

    occupations: List[Occupation]
    illisibles: int


def lire_occupations(evenements: Any) -> Lecture:
    """Transforme les evenements de Google en moments pris.

    Un evenement annule ne prend rien. Un evenement dont on ne sait lire ni le
    debut ni la fin est **compte comme illisible**, jamais silencieusement
    ignore : c'est peut-etre lui qui remplit la journee.
    """
    occupations: List[Occupation] = []
    illisibles = 0
    for evenement in evenements if isinstance(evenements, list) else []:
        if not isinstance(evenement, dict):
            illisibles += 1
            continue
        if evenement.get("status") == "cancelled":
            continue
        debut = _instant(evenement.get("start"))
        fin = _instant(evenement.get("end"))
        if debut is None:
            illisibles += 1
            continue
        if fin is None or fin <= debut:
            # Sans fin lisible, on ne devine pas une duree : l'evenement bloque
            # la journee ou il commence. Le contraire — le compter comme un
            # point — annoncerait libre un jour occupe.
            fin = datetime.combine(debut.date(), heure_du_jour(0, 0),
                                   tzinfo=debut.tzinfo) + timedelta(days=1)
        occupations.append(Occupation(
            debut=debut, fin=fin,
            titre=str(evenement.get("summary") or "(sans titre)")))
    return Lecture(occupations=sorted(occupations, key=lambda o: o.debut),
                   illisibles=illisibles)


# --- Les deux questions qui comptent -------------------------------------------------

def conflits(occupations: List[Occupation], debut: datetime,
             fin: datetime) -> List[Occupation]:
    """Ce qui tombe sur le creneau propose. Liste vide = rien ne le recouvre."""
    return [o for o in occupations if o.chevauche(debut, fin)]


def creneaux_libres(
    occupations: List[Occupation],
    debut: datetime,
    fin: datetime,
    duree_minutes: int = DUREE_MINIMALE_MINUTES,
    heure_debut: int = HEURE_DEBUT,
    heure_fin: int = HEURE_FIN,
    jours_ouvres: Tuple[int, ...] = JOURS_OUVRES,
) -> List[Tuple[datetime, datetime]]:
    """Les creneaux ouvres qu'aucun evenement ne recouvre, du plus proche au plus loin.

    Args:
        occupations: ce qui est deja pris.
        debut, fin: la fenetre examinee.
        duree_minutes: la duree minimale d'un creneau utile.
        heure_debut, heure_fin: sa journee de travail.
        jours_ouvres: les jours travailles, 0 = lundi.

    Returns:
        Des couples (debut, fin). Une liste vide veut dire « rien de libre dans
        cette fenetre » — jamais « on ne sait pas ».
    """
    duree = timedelta(minutes=max(1, duree_minutes))
    libres: List[Tuple[datetime, datetime]] = []

    jour = debut.date()
    dernier = fin.date()
    while jour <= dernier:
        if jour.weekday() in jours_ouvres:
            ouverture = datetime.combine(jour, heure_du_jour(heure_debut), tzinfo=debut.tzinfo)
            fermeture = datetime.combine(jour, heure_du_jour(heure_fin), tzinfo=debut.tzinfo)
            curseur = max(ouverture, debut)
            limite = min(fermeture, fin)

            pris = sorted((o for o in occupations if o.chevauche(curseur, limite)),
                          key=lambda o: o.debut)
            for occupation in pris:
                if occupation.debut - curseur >= duree:
                    libres.append((curseur, occupation.debut))
                curseur = max(curseur, occupation.fin)
            if limite - curseur >= duree:
                libres.append((curseur, limite))
        jour += timedelta(days=1)
    return libres


# --- La couche reseau -----------------------------------------------------------------

def _http(chemin: str, parametres: Dict[str, Any], jeton: str) -> Dict[str, Any]:
    """Un GET sur l'API Calendar."""
    url = f"{BASE_URL.rstrip('/')}/{chemin.lstrip('/')}"
    with httpx.Client(timeout=DELAI_SECONDES) as client:
        reponse = client.get(url, params=parametres,
                             headers={"Authorization": f"Bearer {jeton}"})
        reponse.raise_for_status()
        return reponse.json()


def _http_post(chemin: str, charge: Dict[str, Any], jeton: str) -> Dict[str, Any]:
    """Un POST sur l'API Calendar. **Le seul chemin qui ecrit.**"""
    url = f"{BASE_URL.rstrip('/')}/{chemin.lstrip('/')}"
    with httpx.Client(timeout=DELAI_SECONDES) as client:
        reponse = client.post(url, json=charge,
                              headers={"Authorization": f"Bearer {jeton}"})
        reponse.raise_for_status()
        return reponse.json()


AppelHttp = Callable[[str, Dict[str, Any], str], Dict[str, Any]]


def _rendre_creneau(creneau: Tuple[datetime, datetime]) -> Dict[str, str]:
    debut, fin = creneau
    return {"debut": debut.isoformat(timespec="minutes"),
            "fin": fin.isoformat(timespec="minutes")}


class CalendrierConnector(Connecteur):
    """Lecture de l'agenda, creneaux libres, conflits, et un rendez-vous confirme."""

    service = "calendar"
    nom = "calendrier"

    ROUTES: Dict[str, Any] = {
        "lire": (f"calendars/{AGENDA}/events", ("timeMin", "timeMax")),
        "creneaux": (f"calendars/{AGENDA}/events", ("timeMin", "timeMax")),
        "conflits": (f"calendars/{AGENDA}/events", ("timeMin", "timeMax")),
        "creer": (f"calendars/{AGENDA}/events", ()),
    }

    #: Ce qu'il faut connaitre pour poser un rendez-vous. Jamais devine.
    REQUIS_POUR_CREER = ("titre", "debut", "fin")

    def __init__(self, appel: Optional[AppelHttp] = None,
                 appel_jeton: Optional[Callable[..., Dict[str, Any]]] = None,
                 appel_creation: Optional[AppelHttp] = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._appel = appel or _http
        self._appel_creation = appel_creation or _http_post
        self._jetons = JetonGoogle(echange=appel_jeton)
        self._sante: Optional[Sante] = None
        self._sante_mesuree_a: float = 0.0

    # --- Capacites ----------------------------------------------------------------

    def capacites(self) -> Dict[str, Capacite]:
        """Trois lectures, et une ecriture qui passe par la confirmation."""
        def lecture(nom: str, action: str, description: str) -> Capacite:
            return Capacite(nom=nom, action=action, description=description,
                            ecriture=False, quota_par_minute=QUOTA_PAR_MINUTE)

        return {
            "lire": lecture("lire", "read",
                            "Les rendez-vous d'une periode, du plus proche au plus loin."),
            "creneaux": lecture("creneaux", "free_slots",
                                "Les creneaux ouvres qu'aucun rendez-vous ne recouvre."),
            "conflits": lecture("conflits", "read",
                                "Ce qui tombe deja sur un creneau propose."),
            # `action="create"` : la politique la classe en CONFIRMATION. Poser
            # un rendez-vous engage une journee de travail.
            "creer": Capacite(
                nom="creer", action="create",
                description="Pose un rendez-vous dans l'agenda du proprietaire.",
                ecriture=True, quota_par_minute=CREATIONS_PAR_MINUTE),
        }

    def jeton(self) -> Optional[str]:
        return self._jetons.obtenir()

    def authentifier(self) -> bool:
        """Vrai seulement si Google a reellement rendu un jeton."""
        return self.jeton() is not None

    # --- Sante ---------------------------------------------------------------------

    def sonder(self) -> Sante:
        """Demande la liste des agendas. Une mesure recente est reutilisee une minute."""
        from core.connectors.base import _maintenant

        maintenant = time.monotonic()
        if self._sante is not None and maintenant - self._sante_mesuree_a < DUREE_SONDE_SECONDES:
            return self._sante

        absentes = manquantes()
        if absentes:
            sante = Sante(
                etat=EtatSante.NON_CONFIGURE,
                message=f"Agenda non connecte : {', '.join(absentes)} absente(s) du .env.",
                ce_qui_manque=CE_QUI_MANQUE, mesure_le=_maintenant())
        elif self.jeton() is None:
            sante = Sante(
                etat=EtatSante.NON_CONFIGURE,
                message="Google a refuse les identifiants : jeton non obtenu.",
                ce_qui_manque=CE_QUI_MANQUE, mesure_le=_maintenant())
        else:
            try:
                charge = self._appel("users/me/calendarList", {"maxResults": 1},
                                     self.jeton() or "")
            except Exception as erreur:  # noqa: BLE001
                sante = Sante(etat=EtatSante.EN_PANNE,
                              message=f"L'agenda ne repond pas : {type(erreur).__name__}",
                              mesure_le=_maintenant())
            else:
                agendas = (charge or {}).get("items")
                nombre = len(agendas) if isinstance(agendas, list) else 0
                sante = Sante(
                    etat=EtatSante.OPERATIONNEL,
                    message=f"Agenda joignable ({nombre} agenda(s) visible(s)).",
                    mesure_le=_maintenant())

        self._sante = sante
        self._sante_mesuree_a = maintenant
        return sante

    # --- Execution -------------------------------------------------------------------

    def _fenetre(self, parametres: Dict[str, Any]) -> Tuple[datetime, datetime]:
        """La periode examinee. Par defaut : les sept prochains jours."""
        debut = parametres.get("debut")
        fin = parametres.get("fin")
        if not isinstance(debut, datetime):
            debut = datetime.now(timezone.utc)
        if not isinstance(fin, datetime):
            fin = debut + timedelta(days=7)
        return debut, fin

    def _evenements(self, jeton: str, debut: datetime, fin: datetime) -> Any:
        chemin, _ = self.ROUTES["lire"]
        return self._appel(chemin, {
            "timeMin": debut.isoformat(timespec="seconds"),
            "timeMax": fin.isoformat(timespec="seconds"),
            "singleEvents": "true", "orderBy": "startTime",
            "maxResults": EVENEMENTS_MAX,
        }, jeton)

    def _executer(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        jeton = self.jeton()
        if jeton is None:
            return non_configure(action=capacite.nom, cible=self.nom,
                                 ce_qui_manque=CE_QUI_MANQUE)

        if capacite.nom == "creer":
            return self._creer(capacite, jeton, parametres)

        debut, fin = self._fenetre(parametres)
        try:
            charge = self._evenements(jeton, debut, fin)
        except Exception as erreur:  # noqa: BLE001
            logger.info("Agenda en echec : %s", type(erreur).__name__)
            return echec(action=capacite.nom, cible=self.nom,
                         message=f"L'agenda n'a pas repondu : {type(erreur).__name__}.")

        lecture = lire_occupations((charge or {}).get("items"))
        preuve = f"GET events {debut.date()} -> {fin.date()}"

        if capacite.nom == "lire":
            return succes(
                action=capacite.nom, cible=self.nom,
                message=f"{len(lecture.occupations)} rendez-vous sur la periode.",
                preuve=preuve,
                donnees=[{"debut": o.debut.isoformat(timespec="minutes"),
                          "fin": o.fin.isoformat(timespec="minutes"),
                          "titre": o.titre} for o in lecture.occupations],
                illisibles=lecture.illisibles)

        if capacite.nom == "conflits":
            propose_debut = parametres.get("creneau_debut")
            propose_fin = parametres.get("creneau_fin")
            if not isinstance(propose_debut, datetime) or not isinstance(propose_fin, datetime):
                return echec(action=capacite.nom, cible=self.nom,
                             message="Aucun creneau propose : il n'y a rien a verifier.")
            trouves = conflits(lecture.occupations, propose_debut, propose_fin)
            return succes(
                action=capacite.nom, cible=self.nom,
                message=("Rien ne tombe sur ce creneau." if not trouves
                         else f"{len(trouves)} rendez-vous tombe(nt) sur ce creneau."),
                preuve=preuve,
                donnees=[{"debut": o.debut.isoformat(timespec="minutes"),
                          "fin": o.fin.isoformat(timespec="minutes"),
                          "titre": o.titre} for o in trouves],
                illisibles=lecture.illisibles)

        duree = parametres.get("duree_minutes")
        libres = creneaux_libres(
            lecture.occupations, debut, fin,
            duree_minutes=duree if isinstance(duree, int) else DUREE_MINIMALE_MINUTES)
        return succes(
            action=capacite.nom, cible=self.nom,
            message=(f"{len(libres)} creneau(x) libre(s) entre {debut.date()} "
                     f"et {fin.date()}."),
            preuve=preuve,
            donnees=[_rendre_creneau(c) for c in libres],
            # Ce qu'on n'a pas su lire se dit : c'est peut-etre ce qui remplit
            # la journee qu'on vient d'annoncer libre.
            illisibles=lecture.illisibles)

    def _creer(self, capacite: Capacite, jeton: str,
               parametres: Dict[str, Any]) -> ResultatAction:
        """Pose le rendez-vous. Appele **uniquement** apres confirmation."""
        titre = str(parametres.get("titre") or "").strip()
        debut = parametres.get("debut")
        fin = parametres.get("fin")
        manquants = [nom for nom, valeur in (
            ("titre", titre),
            ("debut", debut if isinstance(debut, datetime) else ""),
            ("fin", fin if isinstance(fin, datetime) else ""),
        ) if not valeur]
        if manquants:
            return echec(
                action=capacite.nom, cible=self.nom,
                message=("Rien n'est pose : il manque " + ", ".join(manquants)
                         + ". Je ne devine pas l'heure d'un rendez-vous."),
                manquants=manquants)
        if fin <= debut:
            return echec(action=capacite.nom, cible=self.nom,
                         message="La fin precede le debut : rien n'est pose.")

        chemin, _ = self.ROUTES["creer"]
        corps = {
            "summary": titre,
            "start": {"dateTime": debut.isoformat(timespec="seconds")},
            "end": {"dateTime": fin.isoformat(timespec="seconds")},
        }
        lieu = str(parametres.get("lieu") or "").strip()
        if lieu:
            corps["location"] = lieu

        try:
            charge = self._appel_creation(chemin, corps, jeton)
        except Exception as erreur:  # noqa: BLE001
            logger.info("Creation refusee : %s", type(erreur).__name__)
            return echec(
                action=capacite.nom, cible=self.nom,
                message=(f"Google a refuse la creation ({type(erreur).__name__}). "
                         "Si la portee calendar.events n'a pas ete accordee, elle "
                         "manque : rien n'est pose."))

        identifiant = (charge or {}).get("id") if isinstance(charge, dict) else None
        if not identifiant:
            return echec(action=capacite.nom, cible=self.nom,
                         message="L'agenda a repondu sans identifiant : creation non prouvee.")
        return succes(
            action=capacite.nom, cible=self.nom,
            message=f"Rendez-vous pose : {titre}, le {debut.date()}.",
            preuve=str(identifiant), titre=titre)
