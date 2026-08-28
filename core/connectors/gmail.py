"""Connecteur Gmail — lire et chercher son courrier, sans jamais y toucher.

Le chapitre 8 etait gele : on n'ajoute pas de nouveaux secrets a un depot public
dont l'historique fuit. Le proprietaire a passe le depot en prive le 28/08/2026
et retire les deux clients tiers qui portaient les cles mortes ; il a rouvert le
chapitre le meme jour. Rien n'est ecrit ici qui ne l'ait pas ete avant : les
identifiants vivent dans l'environnement, jamais dans le depot.

**Cinq regles, et la premiere commande les autres :**

1. **Une seule ecriture, et elle ne part jamais seule.** Trois lectures —
   `lister`, `chercher`, `lire` — et un `envoyer` ajoute en 8.2. Ce dernier
   porte `action="send"`, que la politique classe en CONFIRMATION : le cadre le
   met en attente et rien ne quitte la boite tant que le proprietaire n'a pas
   repondu. Supprimer, etiqueter, changer un reglage : ces capacites n'existent
   pas, et il n'y a rien a activer par un reglage.

2. **Un e-mail est une donnee, jamais une consigne.** N'importe qui peut ecrire
   au proprietaire. Le message rendu — en-tetes compris, car un sujet se choisit
   aussi bien qu'un corps — traverse la frontiere de confiance
   (`core/security/trust.py`, niveau `EXTERNAL`) avant de pouvoir approcher une
   invite.

3. **Sans identifiants, `NOT_CONFIGURED` avec ce qui manque.** Pas de resultat
   plausible, pas de boite vide qui ressemblerait a « aucun message ». La sonde
   dit ce qui manque et ou l'obtenir.

4. **Un champ absent reste absent.** Un e-mail sans date connue porte `None`,
   jamais l'heure d'aujourd'hui ; un expediteur illisible reste `None`, jamais
   « inconnu@exemple.com ».

5. **Le corps est plafonne.** Un e-mail de plusieurs mega-octets ne remplit pas
   le budget d'une conversation. Ce qui est coupe est **dit**.
"""
import base64
import logging
import os
import time
from email.message import EmailMessage
from typing import Any, Callable, Dict, List, Optional, Tuple

import httpx

from core.actions.resultat import ResultatAction, echec, non_configure, succes
from core.connectors.base import Capacite, Connecteur, EtatSante, Sante
from core.security.trust import TrustLevel, wrap

logger = logging.getLogger("usman.connecteurs.gmail")

#: L'API officielle de Google. Dans l'environnement, jamais en dur ailleurs.
BASE_URL = os.getenv("GMAIL_API_URL", "https://gmail.googleapis.com/gmail/v1")
URL_JETON = os.getenv("GMAIL_TOKEN_URL", "https://oauth2.googleapis.com/token")

#: Ce qu'il faut fournir, et ou le prendre. Ce texte part avec `NOT_CONFIGURED` :
#: une capacite absente se rapporte avec la commande qui l'obtient.
CE_QUI_MANQUE = (
    "trois valeurs dans .env, obtenues sur console.cloud.google.com "
    "(API Gmail activee, ecran de consentement, identifiant OAuth « application "
    "de bureau ») : GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET et GMAIL_REFRESH_TOKEN. "
    "Portee gmail.readonly pour lire ; gmail.send en plus pour envoyer — sans "
    "elle, Google refuse l'envoi et ARENA le rapporte. Aucune ne s'ecrit dans "
    "le depot."
)

#: Plafond que **nous** nous imposons, pas un quota publie par Google : lire la
#: boite en boucle ne la rend pas plus fraiche, et une boucle emballee y
#: passerait la journee.
QUOTA_PAR_MINUTE = 60

#: Plafond d'envoi, et il est bas exprès. Une boucle qui s'emballe sur une
#: lecture fait perdre du temps ; une boucle qui s'emballe sur un envoi ecrit a
#: ses clients. Chaque envoi passe deja par une confirmation : ce plafond est la
#: seconde barriere, pas la premiere.
ENVOIS_PAR_MINUTE = 5

#: Au-dela, on considere que Google ne repond pas plutot que de faire attendre
#: une reponse de chat.
DELAI_SECONDES = 15.0

#: Marge avant l'expiration du jeton : on le renouvelle un peu avant plutot que
#: de decouvrir en plein appel qu'il vient de perimer.
MARGE_JETON_SECONDES = 60.0

#: Ce qu'on garde du corps d'un message. Le reste est coupe, et la coupe est
#: annoncee dans le texte rendu.
CORPS_MAX_CARACTERES = 4000

#: Duree pendant laquelle une mesure de sante reste valable.
DUREE_SONDE_SECONDES = 60.0

#: Les en-tetes qu'on lit. Tout le reste est ignore : ce connecteur ne
#: reconstitue pas un client de messagerie.
ENTETES_LUS = ("From", "To", "Subject", "Date")


def identifiants() -> Tuple[str, str, str]:
    """Les trois valeurs OAuth, lues dans l'environnement. Vides si absentes."""
    return (
        os.getenv("GMAIL_CLIENT_ID", ""),
        os.getenv("GMAIL_CLIENT_SECRET", ""),
        os.getenv("GMAIL_REFRESH_TOKEN", ""),
    )


def _obtenir_jeton(client_id: str, client_secret: str, refresh_token: str) -> Dict[str, Any]:
    """Echange le jeton de rafraichissement contre un jeton d'acces. Leve si echec.

    Sortie reseau isolee dans une fonction : les tests la remplacent, et le
    reste du module se verifie sans Google.
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


def _http(chemin: str, parametres: Dict[str, Any], jeton: str) -> Dict[str, Any]:
    """Un GET sur l'API Gmail. Rend la charge JSON, ou leve."""
    url = f"{BASE_URL.rstrip('/')}/{chemin.lstrip('/')}"
    with httpx.Client(timeout=DELAI_SECONDES) as client:
        reponse = client.get(url, params=parametres,
                             headers={"Authorization": f"Bearer {jeton}"})
        reponse.raise_for_status()
        return reponse.json()


def _http_post(chemin: str, charge: Dict[str, Any], jeton: str) -> Dict[str, Any]:
    """Un POST sur l'API Gmail. **Le seul chemin qui ecrit quoi que ce soit.**

    Isole du GET pour que ce soit visible : une fonction qui envoie ne doit pas
    se confondre avec une fonction qui lit.
    """
    url = f"{BASE_URL.rstrip('/')}/{chemin.lstrip('/')}"
    with httpx.Client(timeout=DELAI_SECONDES) as client:
        reponse = client.post(url, json=charge,
                              headers={"Authorization": f"Bearer {jeton}"})
        reponse.raise_for_status()
        return reponse.json()


def message_brut(destinataire: str, sujet: str, corps: str) -> str:
    """Le message au format RFC 2822, encode comme Gmail l'attend.

    Construit par la bibliotheque standard : les accents d'un devis senegalais
    et un sujet non-ASCII ne doivent pas dependre d'un encodage bricole a la
    main.
    """
    message = EmailMessage()
    message["To"] = destinataire
    message["Subject"] = sujet
    message.set_content(corps)
    return base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")


#: Signatures de la couche reseau, injectables pour les tests.
AppelHttp = Callable[[str, Dict[str, Any], str], Dict[str, Any]]
AppelJeton = Callable[[str, str, str], Dict[str, Any]]


# --- Lecture d'un message --------------------------------------------------------

def _decoder(donnees: Optional[str]) -> str:
    """Decode le base64url de Gmail. Une charge illisible rend une chaine vide.

    Une exception ici ferait tomber la lecture de toute la boite pour un seul
    message mal forme.
    """
    if not donnees:
        return ""
    try:
        comble = donnees + "=" * (-len(donnees) % 4)
        return base64.urlsafe_b64decode(comble.encode("ascii")).decode("utf-8", "replace")
    except Exception:  # noqa: BLE001 — un message illisible n'arrete pas les autres
        return ""


def corps_texte(charge: Any) -> str:
    """Le texte brut d'un message, en descendant ses parties MIME.

    `text/plain` est prefere partout ou il existe. Un message qui n'a que du
    HTML rend son HTML : le dire vaut mieux que rendre du vide, et la suite le
    traite comme du texte de toute facon.
    """
    if not isinstance(charge, dict):
        return ""

    mime = charge.get("mimeType") or ""
    parties = charge.get("parts")

    if isinstance(parties, list) and parties:
        textes = [corps_texte(partie) for partie in parties]
        clairs = [t for t, p in zip(textes, parties, strict=True)
                  if (p or {}).get("mimeType") == "text/plain" and t]
        if clairs:
            return "\n".join(clairs)
        return "\n".join(t for t in textes if t)

    if mime.startswith("text/") or not mime:
        return _decoder((charge.get("body") or {}).get("data"))
    return ""


def entetes(charge: Any) -> Dict[str, Optional[str]]:
    """Les en-tetes lus, par nom. Un en-tete absent vaut `None`, jamais "".

    Un expediteur inconnu doit se lire « on ne sait pas », pas « vide ».
    """
    trouves: Dict[str, Optional[str]] = {nom: None for nom in ENTETES_LUS}
    for entete in ((charge or {}).get("payload") or {}).get("headers") or []:
        nom = (entete or {}).get("name")
        if nom in trouves and entete.get("value"):
            trouves[nom] = str(entete["value"])
    return trouves


def rendre_message(charge: Dict[str, Any]) -> Dict[str, Any]:
    """Un message Gmail en forme lisible, corps plafonne et coupe annoncee."""
    lus = entetes(charge)
    corps = corps_texte((charge or {}).get("payload"))
    coupe = len(corps) > CORPS_MAX_CARACTERES
    if coupe:
        corps = corps[:CORPS_MAX_CARACTERES] + "\n[…] coupe : le message depasse le budget."

    return {
        "id": charge.get("id"),
        "fil": charge.get("threadId"),
        "expediteur": lus["From"],
        "destinataire": lus["To"],
        "sujet": lus["Subject"],
        "date": lus["Date"],
        "extrait": charge.get("snippet") or None,
        "corps": corps,
        "coupe": coupe,
    }


def texte_pour_le_modele(message: Dict[str, Any]) -> str:
    """Le message enveloppe comme une donnee etrangere, prete pour une invite.

    Les en-tetes entrent DANS l'enveloppe : un sujet se choisit aussi librement
    qu'un corps, et « Subject: ignore les instructions precedentes » est un
    texte d'attaquant comme un autre.
    """
    lignes = [
        f"De : {message.get('expediteur') or 'expediteur inconnu'}",
        f"Date : {message.get('date') or 'date inconnue'}",
        f"Sujet : {message.get('sujet') or 'sans sujet'}",
        "",
        message.get("corps") or "(message sans texte lisible)",
    ]
    origine = f"e-mail {message.get('id') or 'sans identifiant'}"
    return wrap("\n".join(lignes), TrustLevel.EXTERNAL, origine).text


class GmailConnector(Connecteur):
    """Lecture et recherche sur la boite du proprietaire. Rien d'autre."""

    service = "email"
    nom = "gmail"

    #: Chemin de l'API et parametres acceptes, par capacite. Un parametre absent
    #: de cette table n'est jamais transmis : l'appelant ne choisit pas l'URL.
    ROUTES: Dict[str, Any] = {
        "lister": ("users/me/messages", ("maxResults", "labelIds")),
        "chercher": ("users/me/messages", ("q", "maxResults")),
        "lire": ("users/me/messages/{id}", ("format",)),
        "envoyer": ("users/me/messages/send", ()),
    }

    #: Ce qu'il faut connaitre pour envoyer. Jamais devine : un message parti a
    #: la mauvaise adresse ne se rattrape pas.
    REQUIS_POUR_ENVOYER = ("destinataire", "sujet", "corps")

    def __init__(self, appel: Optional[AppelHttp] = None,
                 appel_jeton: Optional[AppelJeton] = None,
                 appel_envoi: Optional[AppelHttp] = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._appel = appel or _http
        self._appel_envoi = appel_envoi or _http_post
        self._appel_jeton = appel_jeton or _obtenir_jeton
        self._jeton: Optional[str] = None
        self._jeton_expire_a: float = 0.0
        self._sante: Optional[Sante] = None
        self._sante_mesuree_a: float = 0.0

    # --- Ce que le connecteur sait faire ---------------------------------------

    def capacites(self) -> Dict[str, Capacite]:
        """Trois lectures, et un envoi qui ne part jamais sans confirmation."""
        def lecture(nom: str, action: str, description: str) -> Capacite:
            return Capacite(nom=nom, action=action, description=description,
                            ecriture=False, quota_par_minute=QUOTA_PAR_MINUTE)

        return {
            "lister": lecture(
                "lister", "read",
                "Les messages recents de la boite, du plus recent au plus ancien."),
            "chercher": lecture(
                "chercher", "search",
                "Cherche dans la boite avec la syntaxe Gmail (from:, subject:, has:...)."),
            "lire": lecture(
                "lire", "read",
                "Lit un message par son identifiant : en-tetes, corps, extrait."),
            # La seule ecriture. `action="send"` la place sous la regle
            # `email.send` de la politique : CONFIRMATION, risque HIGH,
            # coupe-circuit SEND_MESSAGES. Le cadre s'en occupe — ce connecteur
            # n'a aucun moyen de contourner sa propre declaration.
            "envoyer": Capacite(
                nom="envoyer", action="send",
                description="Envoie un message depuis la boite du proprietaire.",
                ecriture=True, quota_par_minute=ENVOIS_PAR_MINUTE),
        }

    # --- Identification --------------------------------------------------------

    def jeton(self) -> Optional[str]:
        """Un jeton d'acces valable, ou `None` si on n'a pas pu en obtenir.

        Le jeton est garde jusqu'a peu avant son expiration : le redemander a
        chaque appel ferait trois allers-retours pour lire un message.
        """
        if self._jeton and time.monotonic() < self._jeton_expire_a:
            return self._jeton

        client_id, client_secret, refresh = identifiants()
        if not (client_id and client_secret and refresh):
            return None

        try:
            charge = self._appel_jeton(client_id, client_secret, refresh)
        except Exception as erreur:  # noqa: BLE001 — un refus est un etat, pas un crash
            logger.info("Jeton Gmail refuse : %s", type(erreur).__name__)
            return None

        jeton = (charge or {}).get("access_token")
        if not jeton:
            logger.info("Google a repondu sans jeton d'acces.")
            return None

        duree = charge.get("expires_in")
        duree = float(duree) if isinstance(duree, (int, float)) else 3600.0
        self._jeton = str(jeton)
        self._jeton_expire_a = time.monotonic() + max(0.0, duree - MARGE_JETON_SECONDES)
        return self._jeton

    def authentifier(self) -> bool:
        """Vrai seulement si un jeton a **reellement** ete obtenu.

        Pas « les trois variables sont presentes » : trois valeurs peuvent etre
        la et etre revoquees. La question est « Google me repond-il oui ? ».
        """
        return self.jeton() is not None

    # --- Sante -----------------------------------------------------------------

    def sonder(self) -> Sante:
        """Demande le profil du compte. Une mesure recente est reutilisee une minute."""
        from core.connectors.base import _maintenant

        maintenant = time.monotonic()
        if self._sante is not None and maintenant - self._sante_mesuree_a < DUREE_SONDE_SECONDES:
            return self._sante

        client_id, client_secret, refresh = identifiants()
        manquantes = [nom for nom, valeur in (
            ("GMAIL_CLIENT_ID", client_id),
            ("GMAIL_CLIENT_SECRET", client_secret),
            ("GMAIL_REFRESH_TOKEN", refresh),
        ) if not valeur]

        if manquantes:
            sante = Sante(
                etat=EtatSante.NON_CONFIGURE,
                message=f"Gmail n'est pas connecte : {', '.join(manquantes)} absente(s) du .env.",
                ce_qui_manque=CE_QUI_MANQUE,
                mesure_le=_maintenant(),
            )
        else:
            jeton = self.jeton()
            if jeton is None:
                sante = Sante(
                    etat=EtatSante.NON_CONFIGURE,
                    message="Google a refuse les identifiants : jeton non obtenu.",
                    ce_qui_manque=CE_QUI_MANQUE,
                    mesure_le=_maintenant(),
                )
            else:
                try:
                    profil = self._appel("users/me/profile", {}, jeton)
                except Exception as erreur:  # noqa: BLE001
                    sante = Sante(
                        etat=EtatSante.EN_PANNE,
                        message=f"Gmail ne repond pas : {type(erreur).__name__}",
                        mesure_le=_maintenant(),
                    )
                else:
                    adresse = (profil or {}).get("emailAddress") or "compte inconnu"
                    total = (profil or {}).get("messagesTotal")
                    compte = f"{total} message(s)" if isinstance(total, int) else "total inconnu"
                    sante = Sante(
                        etat=EtatSante.OPERATIONNEL,
                        message=f"Gmail repond pour {adresse} : {compte}, en lecture seule.",
                        mesure_le=_maintenant(),
                    )

        self._sante = sante
        self._sante_mesuree_a = maintenant
        return sante

    # --- Execution ---------------------------------------------------------------

    def _executer(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        """Appelle l'API et rend le resultat. Aucun chemin n'ecrit quoi que ce soit."""
        jeton = self.jeton()
        if jeton is None:
            return non_configure(action=capacite.nom, cible=self.nom,
                                 ce_qui_manque=CE_QUI_MANQUE)

        chemin, acceptes = self.ROUTES[capacite.nom]
        envoyes = {cle: valeur for cle, valeur in parametres.items()
                   if cle in acceptes and valeur not in (None, "")}

        if capacite.nom == "envoyer":
            return self._envoyer(capacite, chemin, jeton, parametres)

        if capacite.nom == "lire":
            identifiant = str(parametres.get("id") or "").strip()
            if not identifiant:
                return echec(action=capacite.nom, cible=self.nom,
                             message="Aucun identifiant de message : rien a lire.")
            chemin = chemin.format(id=identifiant)
            envoyes.setdefault("format", "full")

        try:
            charge = self._appel(chemin, envoyes, jeton)
        except Exception as erreur:  # noqa: BLE001 — l'echec se rapporte, il ne remonte pas
            logger.info("Gmail %s en echec : %s", chemin, erreur)
            return echec(action=capacite.nom, cible=self.nom,
                         message=f"Gmail n'a pas repondu : {type(erreur).__name__}.",
                         chemin=chemin)

        if capacite.nom == "lire":
            message = rendre_message(charge if isinstance(charge, dict) else {})
            return succes(
                action=capacite.nom, cible=self.nom,
                message=f"Message lu : {message['sujet'] or 'sans sujet'}.",
                preuve=f"GET {chemin}",
                donnees=message,
                # Le texte pret pour une invite voyage a part, **enveloppe**.
                texte=texte_pour_le_modele(message),
            )

        references = self._references(charge)
        return succes(
            action=capacite.nom, cible=self.nom,
            message=f"{len(references)} message(s) trouve(s).",
            preuve=f"GET {chemin} {envoyes or ''}".strip(),
            donnees=references,
            # Ce que Gmail annonce, quand il l'annonce. Une estimation absente
            # reste absente : elle ne devient pas le nombre de references lues.
            estimation=(charge or {}).get("resultSizeEstimate")
            if isinstance(charge, dict) else None,
        )

    def _envoyer(self, capacite: Capacite, chemin: str, jeton: str,
                 parametres: Dict[str, Any]) -> ResultatAction:
        """Envoie le message. Appele **uniquement** apres confirmation du proprietaire.

        Le cadre a deja fait passer cette capacite par la file d'attente : quand
        cette methode s'execute, quelqu'un a dit oui. Ce qui reste a verifier
        ici, c'est que le message est complet — un envoi a une adresse devinee
        ne se rattrape pas.
        """
        valeurs = {nom: str(parametres.get(nom) or "").strip()
                   for nom in self.REQUIS_POUR_ENVOYER}
        manquants = [nom for nom, valeur in valeurs.items() if not valeur]
        if manquants:
            return echec(
                action=capacite.nom, cible=self.nom,
                message=("Rien n'est parti : il manque " + ", ".join(manquants)
                         + ". Je ne devine pas le destinataire d'un message."),
                manquants=manquants)

        try:
            charge = self._appel_envoi(
                chemin, {"raw": message_brut(**valeurs)}, jeton)
        except Exception as erreur:  # noqa: BLE001 — un envoi rate se rapporte
            logger.info("Envoi Gmail refuse : %s", type(erreur).__name__)
            return echec(
                action=capacite.nom, cible=self.nom,
                message=(f"Google a refuse l'envoi ({type(erreur).__name__}). "
                         "Si la portee gmail.send n'a pas ete accordee, elle "
                         "manque : rien n'est parti."),
                destinataire=valeurs["destinataire"])

        identifiant = (charge or {}).get("id") if isinstance(charge, dict) else None
        if not identifiant:
            # Sans identifiant, rien ne prouve que le message est parti. Un
            # succes sans preuve ne se construit pas.
            return echec(
                action=capacite.nom, cible=self.nom,
                message="Gmail a repondu sans identifiant de message : envoi non prouve.")

        return succes(
            action=capacite.nom, cible=self.nom,
            message=f"Message envoye a {valeurs['destinataire']}.",
            preuve=str(identifiant),
            destinataire=valeurs["destinataire"],
            sujet=valeurs["sujet"],
        )

    @staticmethod
    def _references(charge: Any) -> List[Dict[str, Any]]:
        """Les identifiants rendus par une liste ou une recherche.

        Gmail ne rend ici que des identifiants : lire un message est un second
        appel, et c'est voulu — on ne telecharge pas une boite entiere pour
        repondre a « ai-je du courrier ? ».
        """
        if not isinstance(charge, dict):
            return []
        messages = charge.get("messages")
        if not isinstance(messages, list):
            return []
        return [{"id": m.get("id"), "fil": m.get("threadId")}
                for m in messages if isinstance(m, dict) and m.get("id")]
