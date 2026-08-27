"""Recherche web, avec ce qu'il faut pour trouver de l'information récente.

Trois reglages de `ddgs` sont utilises ici, et chacun coute une reponse quand il
manque :

- `region` : sans lui, la recherche part en `us-en`. Une question en francais sur
  un club espagnol remonte des pages americaines.
- `timelimit` : sans contrainte de fraicheur, « le dernier match » ramene des
  pages de 2019 aussi volontiers que celle d'hier.
- la categorie `news` : distincte de `text`, elle rend des articles **dates**,
  classes par date. C'est la seule qui voit ce qui a moins d'une heure.

Mesure du 2026-08-27, machine du proprietaire. `news` sur « actualite Senegal »
avec un filtre de 24 h leve `DDGSException: No results found.` La version
precedente traitait cette exception comme une panne, se rabattait sur `text`, et
rendait cinq pages d'accueil de journaux — `seneweb.com`, `senego.com` — toutes
sans date. Le modele recevait donc des sommaires non dates pour repondre a une
question d'actualite, et comblait le vide en inventant.

Trois corrections en decoulent :

1. **une recherche vide n'est pas une erreur.** `No results found` est un
   resultat, pas une panne : on elargit au lieu d'abandonner.
2. **on elargit la requete avant de changer de categorie.** « actualite Senegal »
   sur 24 h rend zero ; « Senegal » sur 24 h rend cinq articles dates. Les mots
   de remplissage — actualite, dernieres, nouvelles — retrecissent la recherche
   au lieu de la preciser.
3. **une page d'accueil ne vaut pas un article.** `https://seneweb.com/` n'a pas
   de date et n'a pas de sujet ; elle passe apres tout ce qui est date.

Mesure du 2026-08-27, meme machine. La passe 1 a leve
`operation timed out` — un alea reseau, pas une absence de resultat — et la
recherche est passee a la suite. Les cinq resultats rendus dataient du 10 au
19 aout : la seule passe qui voit ce qui a moins d'une heure avait ete perdue
pour un incident passager. D'ou la quatrieme correction :

4. **un timeout reseau se reessaie une fois.** Un moteur qui ne repond pas
   n'est pas un moteur qui n'a rien trouve. Un seul reessai, et un delai global
   pour qu'une reponse ne depende jamais d'un moteur muet.
"""
import logging
import re
import time
from typing import Dict, List
from urllib.parse import urlparse

logger = logging.getLogger("usman.tools.search")

REGION_PAR_DEFAUT = "fr-fr"

# `ddgs` leve une exception quand il ne trouve rien, au lieu de rendre une liste
# vide. Ce message-la ne signale aucune panne : ni reseau coupe, ni moteur en
# erreur, seulement une requete trop etroite.
ABSENCE_DE_RESULTAT = "no results found"

# Signatures d'une panne **passagere** : le moteur n'a pas repondu a temps, ou
# la connexion a lache. Un reessai a un sens. Toute autre erreur — parametre
# refuse, categorie inconnue, quota epuise — se reproduira a l'identique, et
# reessayer ne ferait que doubler l'attente.
PANNES_PASSAGERES = (
    "timed out", "timeout", "connection", "connexion",
    "temporarily", "temporary", "reset by peer", "broken pipe",
    "network", "unreachable", "502", "503", "504",
)

# Delai global d'une recherche complete, toutes passes confondues. Il est
# verifie **avant** chaque passe : la derniere engagee peut donc le depasser du
# temps d'un appel moteur. Ce n'est pas une garantie a la seconde, c'est une
# borne qui empeche une reponse d'attendre indefiniment un moteur muet.
DELAI_TOTAL_SECONDES = 25.0

# Mots qui decrivent le *genre* de la demande, pas son sujet. Un moteur
# d'actualites indexe deja des actualites : les lui redemander ne fait que
# reduire le nombre de pages qui correspondent.
MOTS_DE_REMPLISSAGE = {
    "actualite", "actualites", "actu", "actus",
    "nouvelle", "nouvelles", "info", "infos", "information", "informations",
    "derniere", "dernieres", "dernier", "derniers",
    "recent", "recente", "recents", "recentes",
    "aujourd", "hui", "maintenant", "quoi", "de", "neuf", "sur", "les", "la",
    "le", "des", "du", "en", "au", "aux", "et",
}

ACCENTS = str.maketrans("àâäéèêëîïôöùûüç", "aaaeeeeiioouuuc")


def _sans_accent(mot: str) -> str:
    return mot.lower().translate(ACCENTS)


def est_panne_passagere(erreur: BaseException) -> bool:
    """Dit si l'erreur vaut un reessai.

    Le type ne suffit pas : `ddgs` enveloppe les erreurs de son client HTTP dans
    sa propre exception, et le motif reel n'est lisible que dans le message.
    Les deux sont donc regardes — le type quand il est explicite, le texte
    sinon.

    Rien ici ne traite le cas « aucun resultat » : `_executer` le rend avant
    d'arriver jusqu'ici. Un garde-fou de plus a ete ecrit puis retire — le
    saboter ne faisait echouer aucun test, ce qui est la definition d'une ligne
    qui ne protege rien.
    """
    if isinstance(erreur, (TimeoutError, ConnectionError)):
        return True
    return any(signature in str(erreur).lower() for signature in PANNES_PASSAGERES)


class WebSearchTool:
    """Outil de recherche web autonome local via ddgs."""

    def __init__(
        self,
        region: str = REGION_PAR_DEFAUT,
        delai_total: float = DELAI_TOTAL_SECONDES,
        pause_avant_reessai: float = 0.0,
    ):
        self.region = region
        self.delai_total = delai_total
        # Aucune pause par defaut : le timeout qui vient d'echouer a deja pris
        # son temps. Le reglage existe pour un moteur qui limite le debit, pas
        # pour ralentir le cas normal — et il est a zero dans les tests.
        self.pause_avant_reessai = pause_avant_reessai

    # --- Acces au moteur ------------------------------------------------------

    def _interroger(self, categorie: str, query: str, max_results: int, timelimit=None):
        """Appelle le moteur, sans rien rattraper. Isole pour etre reessayable.

        Tout ce qui peut echouer est ici, et rien d'autre : `_executer` decide
        quoi faire de l'echec, cette methode se contente de le laisser passer.
        """
        from ddgs import DDGS

        with DDGS() as ddgs:
            methode = getattr(ddgs, categorie)
            return list(methode(
                query,
                region=self.region,
                max_results=max_results,
                **({"timelimit": timelimit} if timelimit else {}),
            ))

    def _executer(self, categorie: str, query: str, max_results: int, timelimit=None) -> List[Dict[str, str]]:
        """Lance une recherche d'une categorie donnee. Rend [] plutot que lever.

        Trois issues possibles a un echec, et une seule donne lieu a un reessai :

        - **aucun resultat** : ce n'est pas une panne, c'est une reponse. On
          rend [] et l'appelant elargit ;
        - **panne passagere** (timeout, connexion perdue) : **un** reessai, puis
          on abandonne. Jamais de boucle ;
        - **toute autre erreur** : on abandonne tout de suite, comme avant. La
          reessayer ne ferait que doubler l'attente pour le meme echec.
        """
        bruts = None
        for tentative in (1, 2):
            try:
                bruts = self._interroger(categorie, query, max_results, timelimit)
                break
            except Exception as erreur:
                # Distinguer « rien trouve » de « le moteur est tombe » : le premier
                # est une information sur la requete, le second sur le systeme. Les
                # confondre a fait passer une requete trop etroite pour une panne.
                if ABSENCE_DE_RESULTAT in str(erreur).lower():
                    logger.info(
                        "Aucun resultat en %s%s pour %r : on elargit.",
                        categorie,
                        f" ({timelimit})" if timelimit else "",
                        query[:60],
                    )
                    return []

                if tentative == 1 and est_panne_passagere(erreur):
                    logger.warning(
                        "Recherche %s interrompue (%s) : un reessai.", categorie, erreur
                    )
                    if self.pause_avant_reessai:
                        time.sleep(self.pause_avant_reessai)
                    continue

                logger.warning(f"Recherche {categorie} impossible : {erreur}")
                return []

        if bruts is None:
            return []

        resultats = []
        for r in bruts:
            resultats.append({
                "title": r.get("title", ""),
                "href": r.get("href") or r.get("url", ""),
                "body": r.get("body") or r.get("excerpt", ""),
                # `news` date ses articles ; `text` ne le fait pas. L'absence de
                # date est dite par None, jamais remplacee par la date du jour.
                "date": r.get("date"),
                "source": categorie,
            })
        return resultats

    # --- Preparation de la requete -------------------------------------------

    @staticmethod
    def elargir(query: str) -> str:
        """Retire les mots qui decrivent le genre de la demande, pas son sujet.

        « dernieres actualites Senegal » devient « Senegal ». Rend une chaine
        vide si la requete n'etait faite que de ces mots-la : l'appelant saura
        alors qu'il n'y a rien a elargir.
        """
        mots = re.findall(r"[\w'-]+", query, flags=re.UNICODE)
        gardes = [m for m in mots if _sans_accent(m.strip("'-")) not in MOTS_DE_REMPLISSAGE]
        return " ".join(gardes).strip()

    @staticmethod
    def _est_page_daccueil(href: str) -> bool:
        """Vrai pour `https://seneweb.com/` ou `https://senego.com`, faux pour un article.

        Une page d'accueil change toutes les heures et ne porte aucune date : elle
        ne peut pas servir de source a une affirmation datee.
        """
        try:
            chemin = urlparse(href).path
        except Exception:
            return False
        return chemin.strip("/") == ""

    # --- Recherche ------------------------------------------------------------

    def search(self, query: str, max_results: int = 5, recent: bool = False) -> List[Dict[str, str]]:
        """Cherche, et privilegie ce qui est date quand `recent` est demande.

        Passes, dans l'ordre, chacune n'ayant lieu que si la precedente n'a pas
        suffi :

        1. `news` du jour — la seule qui voit ce qui a moins d'une heure ;
        2. `news` du jour sur la requete elargie — le cas mesure : « actualite
           Senegal » rend zero, « Senegal » rend cinq articles dates ;
        3. `news` de la semaine — un sujet peu couvert n'a pas d'article du jour ;
        4. `text` de la semaine ;
        5. `text` sans contrainte de date, pour ne jamais rendre zero resultat
           quand la reponse existe mais n'est pas recente.

        Sans `recent`, seule la derniere passe a lieu : une question intemporelle
        n'a rien a gagner a un filtre de fraicheur.

        Les resultats dates passent devant les autres, et les pages d'accueil
        passent en dernier : elles n'ont ni date ni sujet.

        Chaque passe peut etre reessayee une fois sur panne reseau, et le
        tout est borne par `delai_total`, verifie avant chaque passe.
        """
        resultats: List[Dict[str, str]] = []
        vus = set()
        # Echeance locale, jamais stockee sur l'instance : deux recherches
        # simultanees ne doivent pas se voler leur budget.
        echeance = time.monotonic() + self.delai_total

        def ajouter(nouveaux):
            for r in nouveaux:
                if r["href"] and r["href"] not in vus:
                    vus.add(r["href"])
                    resultats.append(r)

        def il_en_manque() -> bool:
            """Reste-t-il des resultats a chercher, et du temps pour le faire ?

            La premiere passe part toujours : au demarrage, le delai global est
            forcement intact. Les suivantes ne s'engagent que si le budget n'est
            pas epuise — un moteur muet ne peut donc pas retarder la reponse
            passe cette borne.
            """
            if time.monotonic() >= echeance:
                logger.warning(
                    "Delai global de %.0f s atteint : recherche arretee avec %d resultat(s).",
                    self.delai_total, len(resultats),
                )
                return False
            return len(resultats) < max_results

        if recent:
            ajouter(self._executer("news", query, max_results, timelimit="d"))

            elargie = self.elargir(query)
            if il_en_manque() and elargie and elargie.lower() != query.lower():
                ajouter(self._executer("news", elargie, max_results, timelimit="d"))

            if il_en_manque():
                ajouter(self._executer("news", query, max_results, timelimit="w"))

            if il_en_manque():
                ajouter(self._executer("text", query, max_results, timelimit="w"))

        if il_en_manque():
            ajouter(self._executer("text", query, max_results))

        if not resultats:
            logger.warning(f"Aucun resultat pour : {query[:60]!r}")

        return self._classer(resultats, recent)[:max_results]

    @staticmethod
    def _classer(resultats: List[Dict[str, str]], recent: bool) -> List[Dict[str, str]]:
        """Date d'abord, page d'accueil en dernier. Ordre d'arrivee sinon.

        `sorted` est stable : a rang egal, l'ordre des passes est conserve, donc
        un article du jour reste devant un article de la semaine.
        """
        if not recent:
            return resultats

        def rang(r: Dict[str, str]) -> int:
            if WebSearchTool._est_page_daccueil(r.get("href", "")):
                return 2
            return 0 if r.get("date") else 1

        return sorted(resultats, key=rang)
