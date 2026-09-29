"""Les competences reseaux sociaux, devenues des capacites qui s'executent.

Elles viennent de `charlie947/social-media-skills` (MIT). Ce depot-la est un jeu
de `SKILL.md` : des instructions pour un modele. **Les recopier ici n'aurait rien
rendu vivant** — un dossier de prompts qu'aucune phrase n'atteint est exactement
ce que la mission « reveiller ce qui dort » a passe deux jours a corriger.

Ce qui est fait a la place : leur METHODE est extraite. Leurs regles chiffrees
deviennent du code qui compte (`tools/social/regles.py`), leur voix devient des
souvenirs (`tools/social/voix.py`), leur matrice devient une combinatoire
(`tools/social/idees.py`), et cet agent les enchaine sur une phrase reelle.

**Six regles :**

1. **Le proprietaire ne nomme jamais une competence.** Il dit « ecris une
   publication sur mon chantier » ; l'agent choisit.

2. **Sa voix ne s'invente pas.** Sans elle, l'agent DEMANDE au lieu d'ecrire
   dans un ton suppose. Un texte part sous son nom.

3. **Ce que le modele rend est RELU par une machine.** Le nombre de lignes, la
   longueur, les tirets, l'appel a l'action : mesures, pas confiance.

4. **Publier est une confirmation.** L'agent prepare tout et s'arrete la ou
   commence l'irreversible — le connecteur et la politique decident, pas lui.

5. **Une capacite indisponible se declare.** Apify, Gemini, un compte connecte :
   ce qui manque est nomme, avec ou l'obtenir. Le reste continue de marcher.

6. **Chaque execution laisse ses etapes.** « voix chargee, brouillon ecrit,
   relecture : 2 points » — un etat qui ne correspond a rien serait pire que pas
   d'etat du tout.
"""
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from core.agent.base_agent import BaseAgent
from core.connectors.registre import RegistreConnecteurs
from core.memory.memory_manager import MemoryManager
from core.memory.personnelle import MemoirePersonnelle
from core.models.base import ModelProvider
from tools.social import idees as matrice_idees
from tools.social import regles
from tools.social import voix as memoire_voix

logger = logging.getLogger("usman.agent.social")

#: D'ou viennent les methodes. L'attribution voyage avec le code.
SOURCE = "charlie947/social-media-skills (MIT)"

#: Combien de publications passees servent de contexte. Au-dela, on remplit le
#: prompt sans rien ajouter.
PUBLICATIONS_RELUES = 5


@dataclass(frozen=True)
class Capacite:
    """Une capacite du registre : ce qu'elle fait, ce qu'elle exige, comment on l'appelle."""

    nom: str
    description: str
    categorie: str
    declencheurs: tuple
    #: Ce dont elle a besoin pour tourner. Vide = elle tourne toujours.
    dependances: tuple = ()
    #: `draft` prepare sans rien envoyer ; `approbation` passe par la file.
    permission: str = "draft"

    def declenchee_par(self, texte: str) -> bool:
        minuscule = (texte or "").lower()
        return any(mot in minuscule for mot in self.declencheurs)

    def to_dict(self) -> Dict[str, Any]:
        return {"nom": self.nom, "description": self.description,
                "categorie": self.categorie, "dependances": list(self.dependances),
                "permission": self.permission}


#: **Le registre.** L'ordre compte : la premiere capacite declenchee gagne, et
#: les plus precises sont declarees avant les plus generales.
CAPACITES: tuple = (
    Capacite("social.voix", "Apprendre ou relire sa voix d'ecriture", "voix",
             ("ma voix", "mon style", "mon ton", "je n'ecris jamais",
              "je n ecris jamais", "j'ecris jamais", "apprends mon style")),
    Capacite("social.verifier", "Relire une publication avant de l'envoyer",
             "controle", ("relis", "verifie ce post", "verifie cette publication",
                          "analyse cette publication", "avant de publier",
                          "avant que je publie", "note ce post")),
    Capacite("social.idees", "Des idees de publication depuis ses piliers",
             "idees", ("idees de publication", "idees de post", "idees de contenu",
                       "de quoi parler", "sujets de publication", "matrice de contenu",
                       "10 idees", "donne-moi des idees")),
    Capacite("social.accroches", "Six crochets pour un sujet", "idees",
             ("accroche", "accroches", "crochet", "hook", "hooks",
              "phrase d'ouverture")),
    Capacite("social.profil", "Optimiser son profil", "profil",
             ("mon profil", "optimise mon profil", "ma bio", "ma biographie",
              "mon titre linkedin")),
    Capacite("social.recherche_niche", "Ce qui marche en ce moment dans son secteur",
             "recherche", ("qu'est-ce qui marche", "qu est ce qui marche",
                           "ce qui marche", "tendances de mon secteur",
                           "mon secteur", "mon domaine", "dans ma niche",
                           "sujets du moment"),
             dependances=("recherche web",)),
    Capacite("social.analytics", "Analyser ses publications passees", "mesure",
             ("mes publications recentes", "mes derniers posts",
              "analyse mes publications", "mes statistiques", "mes performances"),
             dependances=("compte connecte",)),
    Capacite("social.visuel", "Une image pour la publication", "visuel",
             ("une image pour", "un visuel pour", "une miniature", "un carrousel",
              "une infographie"),
             dependances=("generation d'images",)),
    Capacite("social.reels", "Un script de Reel", "video",
             ("un reel", "script de reel", "une video courte pour instagram"),
             dependances=("Apify", "Gemini")),
    # En dernier : la plus generale. Une demande d'ecriture qui n'est rien de
    # ce qui precede est une publication a ecrire.
    Capacite("social.post_writer", "Ecrire une publication", "redaction",
             ("publication", "publie", "poste", "post linkedin", "un post",
              "sur linkedin", "sur instagram", "sur facebook", "reseaux sociaux"),
             permission="approbation"),
)

#: Le reseau nomme dans la phrase (DEC-0181). L'ordre compte : « insta » est
#: cherche comme un mot, pour ne pas prendre « installe » pour Instagram.
RESEAUX: tuple = (
    ("instagram", re.compile(r"\b(instagram|insta|ig)\b", re.IGNORECASE)),
    ("facebook", re.compile(r"\b(facebook|fb)\b", re.IGNORECASE)),
    ("linkedin", re.compile(r"\blinkedin\b", re.IGNORECASE)),
    ("tiktok", re.compile(r"\btik ?tok\b", re.IGNORECASE)),
)

#: Une adresse d'image publique, seule chose qu'Instagram sait publier.
ADRESSE_HTTPS = re.compile(r"https://[^\s<>\"')]+")


def reseau_demande(texte: str) -> Optional[str]:
    """Le reseau que la phrase nomme, ou `None` si elle n'en nomme aucun."""
    for nom, motif in RESEAUX:
        if motif.search(texte or ""):
            return nom
    return None


#: Ce qui, dans la phrase, demande d'ENVOYER et non de preparer.
DEMANDE_D_ENVOI = re.compile(r"\b(publie[- ]?(le|la)?|envoie[- ]?(le|la)?|"
                             r"mets[- ]?(le|la)\s+en\s+ligne)\b", re.IGNORECASE)

INSTRUCTION_PUBLICATION = """Tu ecris une publication pour les reseaux sociaux, au nom du proprietaire.

REGLES ABSOLUES, elles ne se negocient pas :
- 20 lignes maximum, 150 a 300 mots.
- Ligne 1 : l'accroche, 50 caracteres maximum. Ligne 2 : le contraste, 50 maximum.
- Une phrase par ligne, 55 caracteres. Au plus 4 lignes peuvent en faire 110.
- Une ligne vide apres chaque ligne.
- AUCUN tiret cadratin. AUCUN emoji, sauf le symbole de partage dans la cloture.
- Vocabulaire simple. Pas de jargon. Pas d'adverbes.
- Termine par un appel au partage suivi du symbole de recyclage.
- Tu n'inventes AUCUN chiffre, AUCUN nom de client, AUCUNE date. Ce qui ne t'a
  pas ete donne n'existe pas : ecris sans, ou dis ce qui te manque.
"""

INSTRUCTION_ACCROCHES = """Tu ecris 6 crochets pour une publication, au nom du proprietaire.

Chaque crochet fait EXACTEMENT deux lignes, 40 caracteres maximum par ligne.
Les six formes, une chacune : chiffre en tete, contre-courant, transformation
personnelle, autorite empruntee, aveu, choc a venir.

Pas de question en premiere ligne. Pas de tiret cadratin. Pas de mot de
remplissage. Les chiffres en chiffres. Tu n'inventes aucun chiffre : si tu n'en
as pas, ecris le crochet sans.
"""

INSTRUCTION_PROFIL = """Tu revois le profil professionnel du proprietaire.

Rends trois choses, courtes : un titre, une section « a propos », et trois
ameliorations concretes. Tu n'inventes ni diplome, ni annee, ni client, ni
chiffre. Ce qui ne t'a pas ete donne n'existe pas.
"""


@dataclass
class Execution:
    """Ce qu'une capacite a reellement fait, etape par etape.

    Les etats correspondent a des operations reelles. Un « en cours » affiche
    pendant qu'il ne se passe rien serait pire que pas d'etat du tout.
    """

    capacite: str
    etapes: List[str] = field(default_factory=list)
    statut: str = "EN_COURS"
    detail: Dict[str, Any] = field(default_factory=dict)

    def etape(self, texte: str) -> None:
        self.etapes.append(texte)

    def to_dict(self) -> Dict[str, Any]:
        return {"capacite": self.capacite, "statut": self.statut,
                "etapes": list(self.etapes), **self.detail}


def choisir(texte: str) -> Optional[Capacite]:
    """La capacite que cette phrase demande, ou `None`.

    Le proprietaire ne nomme jamais une competence : c'est ici que « ecris une
    publication sur mon chantier » devient `social.post_writer`.
    """
    for capacite in CAPACITES:
        if capacite.declenchee_par(texte):
            return capacite
    return None


class SocialAgent(BaseAgent):
    """Prepare ce qui part sur ses reseaux, et s'arrete la ou commence l'envoi."""

    #: Comment l'agent se presente au registre (DEC-0145) : lu par la
    #: decouverte, jamais recopie dans une liste centrale.
    identifiant = "social"
    competences = ('reseaux sociaux', 'publication linkedin', 'accroches', 'redaction de post')

    def __init__(self, provider: ModelProvider, memory: Optional[MemoryManager] = None,
                 memoire_personnelle: Optional[MemoirePersonnelle] = None,
                 registre: Optional[RegistreConnecteurs] = None,
                 recherche: Optional[Callable[..., Any]] = None):
        super().__init__(
            name="SocialAgent",
            description="Redaction, relecture et preparation de ses publications.",
            provider=provider, memory=memory,
        )
        # Sa voix vit dans la memoire personnelle, pas dans un fichier a part.
        self.memoire_personnelle = memoire_personnelle
        self.registre = registre
        # La recherche web, si elle est branchee. Sans elle, la recherche de
        # niche se declare indisponible au lieu d'inventer des tendances.
        self.recherche = recherche

    # --- Sa voix -----------------------------------------------------------------

    def voix(self) -> Dict[str, List[str]]:
        if self.memoire_personnelle is None:
            return {}
        return memoire_voix.lire(self.memoire_personnelle)

    def _instruction(self, base: str) -> str:
        """L'instruction du modele, completee par sa voix quand elle est connue."""
        bloc = memoire_voix.formater(self.voix())
        return f"{base}\n\n{bloc}" if bloc else base

    def _sans_voix(self, execution: Execution, manquantes: List[str]) -> Dict[str, Any]:
        """Ce qu'on repond quand on ne connait pas encore sa voix.

        On ne devine pas un ton : le texte partirait sous son nom.
        """
        execution.statut = "MANQUE_CONTEXTE"
        execution.detail["manquantes"] = manquantes
        titres = ", ".join(memoire_voix.SECTIONS[m] for m in manquantes)
        return self._rendre(execution, (
            "Je ne connais pas encore assez ta voix pour ecrire en ton nom. "
            f"Il me manque : {titres}. Dis-le-moi une fois, je le garde."))

    # --- Le rendu -------------------------------------------------------------------

    @staticmethod
    def _rendre(execution: Execution, reponse: str, statut: str = "") -> Dict[str, Any]:
        if statut:
            execution.statut = statut
        return {"status": "success" if execution.statut not in
                ("INDISPONIBLE", "ECHEC") else "warning",
                "agent": "SocialAgent", "execution": execution.to_dict(),
                "response": reponse}

    # --- Les capacites ----------------------------------------------------------------

    async def ecrire_publication(self, sujet: str, envoyer: bool = False,
                                 reseau: Optional[str] = None) -> Dict[str, Any]:
        """Ecrit une publication, la RELIT, et s'arrete avant d'envoyer."""
        execution = Execution("social.post_writer")
        voix = self.voix()
        manquantes = memoire_voix.manquantes(voix)
        if manquantes:
            return self._sans_voix(execution, manquantes)
        execution.etape(f"voix chargee ({len(voix)} section(s))")

        brouillon = ((await self.rediger(
            prompt=f"Sujet de la publication : {sujet}",
            system_prompt=self._instruction(INSTRUCTION_PUBLICATION))) or "").strip()
        execution.etape("brouillon ecrit")

        # La relecture est mecanique. Une consigne n'est pas une garantie.
        controle = regles.verifier_publication(brouillon)
        execution.etape(f"relecture : {len(controle.infractions)} point(s)")
        execution.detail["controle"] = controle.to_dict()
        execution.detail["brouillon"] = brouillon

        envoi = self._proposer_l_envoi(brouillon, execution, reseau, sujet) if envoyer else None
        # « En attente d'approbation » seulement si une action attend vraiment
        # son accord : un refus ou un reseau non branche laissent un brouillon
        # PRET, rien d'autre.
        execution.statut = ("EN_ATTENTE_APPROBATION"
                            if envoi and envoi["statut"] == "NEEDS_CONFIRMATION" else "PRET")

        reponse = f"{brouillon}\n\n{controle.rendre()}"
        if envoi:
            reponse += f"\n\n{envoi['message']}"
        return self._rendre(execution, reponse)

    def _proposer_l_envoi(self, texte: str, execution: Execution,
                          reseau: Optional[str] = None, demande: str = "") -> Dict[str, Any]:
        """Soumet la publication au reseau nomme. **Rien ne part ici.**

        Le connecteur et la politique decident : `action="publish"` est une
        confirmation, et le coupe-circuit PUBLISH peut la refuser tout court.
        Sans reseau nomme, c'est TikTok, comme avant DEC-0181.
        """
        if self.registre is None:
            execution.etape("aucun connecteur de publication branche")
            return {"statut": "NOT_CONFIGURED",
                    "message": ("Je peux preparer la publication, pas l'envoyer : "
                                "aucun reseau n'est branche sur cet agent.")}
        if reseau == "facebook":
            resultat = self.registre.executer("meta", "publier_facebook", message=texte)
        elif reseau == "instagram":
            image = ADRESSE_HTTPS.search(demande or "")
            if image is None:
                # Rien n'est mis en attente : une action qui ne peut pas
                # partir ne doit pas attendre son accord.
                execution.etape("instagram : aucune adresse d'image")
                return {"statut": "MANQUE_CONTEXTE",
                        "message": ("Instagram publie une photo, pas un texte seul : "
                                    "donne-moi l'adresse https:// de l'image et je "
                                    "prepare l'envoi avec ce texte en legende.")}
            resultat = self.registre.executer("meta", "publier_instagram",
                                              image_url=image.group(0), legende=texte)
        elif reseau == "linkedin":
            # Un lien dans la phrase devient l'article du post (DEC-0183).
            lien = ADRESSE_HTTPS.search(demande or "")
            parametres = {"message": texte}
            if lien:
                parametres["lien"] = lien.group(0)
            resultat = self.registre.executer("linkedin", "publier", **parametres)
        else:
            resultat = self.registre.executer("tiktok", "publish_video",
                                              legende=texte, chemin_video="")
        execution.etape(f"envoi soumis : {resultat.statut.value}")
        return {"statut": resultat.statut.value, "message": resultat.message}

    async def proposer_accroches(self, sujet: str) -> Dict[str, Any]:
        """Six crochets, relus un par un."""
        execution = Execution("social.accroches")
        voix = self.voix()
        if memoire_voix.manquantes(voix):
            return self._sans_voix(execution, memoire_voix.manquantes(voix))
        execution.etape("voix chargee")

        brut = ((await self.rediger(
            prompt=f"Sujet : {sujet}",
            system_prompt=self._instruction(INSTRUCTION_ACCROCHES))) or "").strip()
        execution.etape("crochets ecrits")

        blocs = [bloc.strip() for bloc in re.split(r"\n\s*\n", brut) if bloc.strip()]
        controles = [regles.verifier_accroche(bloc).to_dict() for bloc in blocs]
        conformes = sum(1 for c in controles if c["conforme"])
        execution.etape(f"relecture : {conformes}/{len(controles)} conformes")
        execution.detail.update({"accroches": blocs, "controles": controles})
        return self._rendre(execution, brut, statut="PRET")

    def proposer_idees(self, deja_publies: Optional[List[str]] = None) -> Dict[str, Any]:
        """Croise ses piliers et les formats. Aucun appel au modele : c'est un calcul."""
        execution = Execution("social.idees")
        voix = self.voix()
        piliers = voix.get("piliers") or []
        if not piliers:
            return self._sans_voix(execution, ["piliers"])

        # Un pilier peut avoir ete dit en une phrase : « BA13, plafonds, devis ».
        eclates = [morceau.strip() for pilier in piliers
                   for morceau in re.split(r"[,;/]| et ", pilier) if morceau.strip()]
        execution.etape(f"{len(eclates)} pilier(s) lus dans sa voix")

        trouvees = matrice_idees.matrice(eclates, deja_publies or [])
        execution.etape(f"{len(trouvees)} idee(s) calculees")
        execution.detail["idees"] = [idee.to_dict() for idee in trouvees]
        execution.detail["resume"] = matrice_idees.resume(trouvees)

        lignes = [f"{index}. {idee.sujet}" for index, idee in enumerate(trouvees[:12], 1)]
        return self._rendre(execution, (
            f"{len(trouvees)} idees, tirees de tes {len(eclates)} piliers :\n"
            + "\n".join(lignes)), statut="PRET")

    def relire(self, texte: str) -> Dict[str, Any]:
        """Relit une publication qu'il a ecrite. Mecanique, sans modele."""
        execution = Execution("social.verifier")
        controle = regles.verifier_publication(texte)
        execution.etape(f"relecture : {len(controle.infractions)} point(s)")
        execution.detail["controle"] = controle.to_dict()
        return self._rendre(execution, controle.rendre(), statut="PRET")

    async def optimiser_profil(self, demande: str) -> Dict[str, Any]:
        execution = Execution("social.profil")
        voix = self.voix()
        if memoire_voix.manquantes(voix):
            return self._sans_voix(execution, memoire_voix.manquantes(voix))
        execution.etape("voix chargee")
        reponse = ((await self.rediger(
            prompt=demande, system_prompt=self._instruction(INSTRUCTION_PROFIL))) or "").strip()
        execution.etape("proposition ecrite")
        return self._rendre(execution, reponse, statut="PRET")

    def apprendre_la_voix(self, texte: str) -> Dict[str, Any]:
        """Retient ce qu'il dit de son style. Une correction pese plus lourd."""
        execution = Execution("social.voix")
        if self.memoire_personnelle is None:
            execution.statut = "INDISPONIBLE"
            return self._rendre(execution, "Aucune memoire n'est branchee sur cet agent.")

        correction = bool(re.search(r"jamais|pas comme ca|pas comme ça|plutot|plutôt",
                                    texte, re.IGNORECASE))
        if correction:
            memoire_voix.corriger(self.memoire_personnelle, texte)
            execution.etape("correction retenue (elle pese plus qu'une reponse)")
        else:
            memoire_voix.apprendre(self.memoire_personnelle, "ton", texte)
            execution.etape("element de voix retenu")

        etat = memoire_voix.resume(self.voix())
        execution.detail["voix"] = etat
        manque = ", ".join(memoire_voix.SECTIONS[m] for m in etat["sections_manquantes"])
        reponse = "C'est note, je l'ecrirai comme ca."
        if manque:
            reponse += f" Il me manque encore : {manque}."
        return self._rendre(execution, reponse, statut="PRET")

    async def rechercher_la_niche(self, demande: str) -> Dict[str, Any]:
        """Ce qui marche en ce moment. **Sans recherche branchee, on le dit.**

        Inventer des tendances serait exactement le contraire de ce qu'on
        demande a cette capacite.
        """
        execution = Execution("social.recherche_niche")
        if self.recherche is None:
            execution.statut = "INDISPONIBLE"
            execution.detail["manque"] = "recherche web"
            return self._rendre(execution, (
                "Je ne peux pas regarder ce qui marche en ce moment : la recherche "
                "web n'est pas branchee sur cet agent. Je n'invente pas de "
                "tendances."))
        resultats = self.recherche(demande)
        execution.etape(f"{len(resultats or [])} source(s) trouvee(s)")
        execution.detail["sources"] = resultats
        return self._rendre(execution, str(resultats), statut="PRET")

    def analyser_publications(self, demande: str) -> Dict[str, Any]:
        """Ses dernieres publications, lues sur le compte, et COMPTEES.

        Aucun modele : les chiffres viennent de Meta et sont additionnes ici.
        Un compte non connecte le dit, avec ce qui manque — jamais une analyse
        de publications qu'on n'a pas lues.
        """
        execution = Execution("social.analytics")
        reseau = reseau_demande(demande)
        cibles = {"instagram": ["instagram"], "facebook": ["facebook"]}.get(
            reseau, ["instagram", "facebook"])
        lignes: List[str] = []
        lues = 0
        for cible in cibles:
            capacite = "instagram_publications" if cible == "instagram" else "page_publications"
            resultat = self.registre.executer("meta", capacite, limite=10)
            execution.etape(f"{cible} : {resultat.statut.value}")
            if resultat.statut.value != "SUCCESS":
                lignes.append(f"{cible.capitalize()} : {resultat.message}")
                continue
            publications = [p for p in (resultat.detail.get("donnees") or []) if isinstance(p, dict)]
            lues += 1
            execution.detail[cible] = publications
            lignes.append(self._resumer(cible, publications))
        if reseau in ("linkedin", "tiktok"):
            lignes.insert(0, f"{reseau.capitalize()} : je ne sais pas encore lire ce compte.")
        execution.statut = "PRET" if lues else "INDISPONIBLE"
        return self._rendre(execution, "\n".join(lignes))

    @staticmethod
    def _resumer(reseau: str, publications: List[Dict[str, Any]]) -> str:
        """Des sommes, pas des impressions."""
        if not publications:
            return f"{reseau.capitalize()} : aucune publication lue."
        if reseau == "facebook":
            # Ces champs ne portent pas les reactions : on ne les invente pas.
            derniere = publications[0].get("created_time") or "?"
            return (f"Facebook : {len(publications)} publication(s) lue(s), la plus "
                    f"recente le {derniere}. Les reactions ne sont pas lues ici.")
        jaime = sum(int(p.get("like_count") or 0) for p in publications)
        commentaires = sum(int(p.get("comments_count") or 0) for p in publications)
        meilleure = max(publications, key=lambda p: int(p.get("like_count") or 0))
        legende = str(meilleure.get("caption") or "sans legende").splitlines()[0][:60]
        return (f"Instagram : {len(publications)} publication(s), {jaime} J'aime, "
                f"{commentaires} commentaire(s). La plus aimee "
                f"({int(meilleure.get('like_count') or 0)} J'aime) : « {legende} » "
                f"{meilleure.get('permalink') or ''}".rstrip())

    def indisponible(self, capacite: Capacite) -> Dict[str, Any]:
        """Une capacite dont les dependances manquent. On dit lesquelles."""
        execution = Execution(capacite.nom)
        execution.statut = "CONFIGURATION_REQUISE"
        execution.detail["manque"] = list(capacite.dependances)
        return self._rendre(execution, (
            f"« {capacite.description} » demande : {', '.join(capacite.dependances)}. "
            "Ce n'est pas branche ici, et je ne fais pas semblant. Le reste "
            "continue de marcher."))

    # --- Le tour de parole -------------------------------------------------------------

    async def run(self, user_input: str, context: Optional[Dict[str, Any]] = None
                  ) -> Dict[str, Any]:
        contexte = context or {}
        capacite = choisir(user_input)
        logger.info("SocialAgent : %r -> %s", (user_input or "")[:60],
                    capacite.nom if capacite else "aucune")

        if capacite is None:
            execution = Execution("aucune")
            execution.statut = "SANS_OBJET"
            return self._rendre(execution, (
                "Je n'ai pas reconnu de demande reseaux sociaux dans cette phrase."))

        if capacite.nom == "social.voix":
            return self.apprendre_la_voix(user_input)
        if capacite.nom == "social.verifier":
            return self.relire(str(contexte.get("publication") or user_input))
        if capacite.nom == "social.idees":
            return self.proposer_idees(contexte.get("deja_publies"))
        if capacite.nom == "social.accroches":
            return await self.proposer_accroches(user_input)
        if capacite.nom == "social.profil":
            return await self.optimiser_profil(user_input)
        if capacite.nom == "social.recherche_niche":
            return await self.rechercher_la_niche(user_input)
        if capacite.nom == "social.post_writer":
            return await self.ecrire_publication(
                user_input, envoyer=bool(DEMANDE_D_ENVOI.search(user_input)),
                reseau=reseau_demande(user_input))
        if capacite.nom == "social.analytics" and self.registre is not None:
            return self.analyser_publications(user_input)
        # Visuel, reels — et l'analyse sans registre : leurs dependances ne
        # sont pas ici.
        return self.indisponible(capacite)
