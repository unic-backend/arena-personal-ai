"""Le catalogue des methodes de specialistes.

**Ce que ce module n'est pas : une collection d'agents.** ARENA reste UNE
intelligence. Ce qui change selon la demande, ce n'est pas l'identite qui
repond — c'est la **methode** qu'elle applique et la liste de ce qu'elle
verifie avant de dire que c'est fini.

Origine : `msitarzewski/agency-agents` (MIT), audite le 01/09/2026. Ce depot
contient 319 definitions de personas — des prompts de role de ~230 lignes
chacun, du type « tu es X, strategique et rigoureux ». **Rien de tout cela
n'a ete copie.** Ce qui a ete repris est la partie substantielle : les
taxonomies de metiers, les listes de controle par domaine (STRIDE, OWASP,
pyramide de tests), et l'idee qu'un specialiste porte sa propre definition
de « fini ». Attribution -> `NOTICE.md`.

**Quatre regles portent ce catalogue :**

1. **Aucun specialiste sans chemin d'execution.** `capacite` nomme ce qui,
   dans ARENA, fait reellement le travail. Un specialiste dont la capacite
   n'existe pas est un specialiste decoratif : un test le refuse
   (`tests/core/test_specialistes.py`).

2. **Aucun doublon.** Quand ARENA sait deja faire — recherche, reseaux
   sociaux, devis — la methode ENRICHIT l'agent existant ; elle n'en cree
   pas un second qui ferait la meme chose moins bien.

3. **Une methode n'est pas un ton.** Ce qui est ecrit ici, ce sont des
   etapes et des controles verifiables. Pas de personnalite, pas de
   « tu es passionne par la qualite » : cela ne change rien a ce qui est
   produit et gonfle chaque prompt.

4. **`fini_quand` est ce qui se verifie**, pas ce qui se promet. Quand
   ARENA peut lancer le controle lui-meme (ruff, pytest, gitleaks), la
   methode le dit et l'appelant le fait.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class Specialiste:
    """Une methode de metier, et le chemin d'ARENA qui l'execute.

    Attributes:
        identifiant: le nom court, stable, utilise dans les journaux.
        domaine: ce que le proprietaire reconnaitrait comme un metier.
        quand: les mots d'une demande qui appellent cette methode.
        methode: les etapes, dans l'ordre. Ce que le specialiste FAIT.
        controles: ce qu'il verifie systematiquement. Ce qu'il REGARDE.
        fini_quand: sa definition de « fini », en termes observables.
        capacite: le chemin ARENA qui execute — une intention de
            l'aiguilleur, un connecteur, ou un outil. Jamais rien de neuf.
        outils: les outils d'ARENA que cette methode mobilise, s'il y en a.
    """

    identifiant: str
    domaine: str
    quand: Tuple[str, ...]
    methode: Tuple[str, ...]
    controles: Tuple[str, ...]
    fini_quand: str
    capacite: str
    outils: Tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> Dict[str, object]:
        return {
            "identifiant": self.identifiant, "domaine": self.domaine,
            "capacite": self.capacite, "outils": list(self.outils),
            "fini_quand": self.fini_quand,
        }


#: Les methodes qu'ARENA sait appliquer. Chacune pointe vers un chemin
#: d'execution qui existait AVANT elle — c'est la regle 1.
CATALOGUE: Tuple[Specialiste, ...] = (
    Specialiste(
        identifiant="securite",
        domaine="Sécurité applicative",
        quand=("securite", "sécurité", "faille", "vulnerabilite", "vulnérabilité",
               "injection", "audit de sécurité", "audit de securite", "owasp",
               "xss", "csrf", "secret exposé", "secret expose", "durcir",
               "attaque", "penetration", "pentest"),
        methode=(
            "Nommer ce qui est protégé et contre qui — sans cible, un audit dérive.",
            "Passer le code par STRIDE : usurpation, altération, répudiation, "
            "divulgation, déni de service, élévation de privilège.",
            "Pour chaque risque trouvé : montrer le chemin d'exploitation concret, "
            "pas la catégorie abstraite.",
            "Proposer le correctif le plus petit qui ferme le chemin.",
            "Écrire le test qui échoue avant le correctif et passe après.",
        ),
        controles=(
            "Entrées non validées atteignant une requête, une commande ou un chemin de fichier",
            "Secrets en clair dans le code, les journaux ou les messages d'erreur",
            "Contrôle d'accès vérifié à chaque point d'entrée, pas seulement à l'interface",
            "Erreurs qui révèlent la structure interne à l'appelant",
            "Dépendances dont la version porte une faille connue",
            "Traversée de chemin sur tout ce qui accepte un nom de fichier",
        ),
        fini_quand=("chaque faille nommée a un chemin d'exploitation décrit, un "
                    "correctif minimal, et un test qui la reproduit"),
        capacite="REPO_ENGINEERING",
        outils=("gitleaks", "ruff", "pytest", "bac_a_sable"),
    ),
    Specialiste(
        identifiant="tests",
        domaine="Stratégie de test",
        quand=("test", "tests", "tester", "couverture", "non-regression",
               "non-régression", "cas limite", "cas limites", "flaky",
               "test unitaire", "test d'integration", "test d'intégration"),
        methode=(
            "Décider ce que le test protège — un test qui ne protège rien coûte "
            "sans rendre.",
            "Écrire d'abord le cas qui échoue, pour la raison attendue.",
            "Couvrir le cas nominal, les bords, et l'échec — l'échec en premier "
            "s'il est le plus coûteux.",
            "Saboter le code pour prouver que le test le tient vraiment.",
            "Remonter la pyramide : unitaire d'abord, intégration seulement pour "
            "ce que l'unitaire ne peut pas voir.",
        ),
        controles=(
            "Le test échoue-t-il si on casse ce qu'il protège ?",
            "Assertion sur un comportement, jamais sur une valeur fabriquée",
            "Dépendance externe absente : le test saute-t-il, ou échoue-t-il à tort ?",
            "Le test dépend-il d'une chose présente sur cette machine seulement ?",
            "Un test supprimé ou affaibli est une régression, pas un nettoyage",
        ),
        fini_quand=("le test a été vu échouer sur le code cassé et passer sur le "
                    "code corrigé, dans la même session"),
        capacite="REPO_ENGINEERING",
        outils=("pytest", "ruff"),
    ),
    Specialiste(
        identifiant="architecture",
        domaine="Architecture logicielle",
        quand=("architecture", "concevoir", "conception", "structurer",
               "refactor", "refactoriser", "dette technique", "couplage",
               "modulaire", "scalab", "monolithe", "microservice"),
        methode=(
            "Nommer la contrainte réelle : volume, équipe, délai, coût. Sans elle, "
            "toute architecture se vaut.",
            "Choisir la forme la plus simple qui la tient — le découpage se paie "
            "en exploitation.",
            "Rendre chaque frontière explicite : ce qui entre, ce qui sort, ce qui "
            "est refusé.",
            "Décider ce qui est remplaçable, et le prouver en nommant le remplaçant.",
            "Écrire ce que la décision coûte si elle est fausse.",
        ),
        controles=(
            "Chaque appel externe a-t-il un délai, une reprise et une issue en cas d'échec ?",
            "Une panne d'un composant en fait-elle tomber d'autres ?",
            "La frontière est-elle tenue par du code, ou seulement par la discipline ?",
            "Ce qui est nouveau réutilise-t-il ce qui existe, ou le double-t-il ?",
        ),
        fini_quand="la décision est écrite avec ce qu'elle coûte si elle est fausse",
        capacite="DEEP_REASONING",
        outils=(),
    ),
    Specialiste(
        identifiant="frontend",
        domaine="Interface web",
        quand=("interface", "frontend", "front-end", "css", "responsive",
               "accessibilite", "accessibilité", "ergonomie", "bouton",
               "affichage", "mobile", "pwa"),
        methode=(
            "Regarder d'abord ce que l'écran fait sur un téléphone — c'est là que "
            "le propriétaire lit.",
            "Rendre l'état visible : chargement, vide, erreur. Les trois, pas le "
            "seul cas heureux.",
            "Vérifier au clavier et au lecteur d'écran avant de vérifier au pixel.",
            "Mesurer ce qui ralentit plutôt que de deviner.",
        ),
        controles=(
            "État vide et état d'erreur traités, pas seulement le cas nominal",
            "Cible tactile assez grande, contraste suffisant",
            "Rien ne casse si le réseau est lent ou absent",
            "Le texte reste lisible à 200 % de zoom",
        ),
        fini_quand="l'écran a été ouvert et vu, pas seulement compilé",
        capacite="CODE_EXECUTION",
        outils=("bac_a_sable",),
    ),
    Specialiste(
        identifiant="devops",
        domaine="Déploiement et exploitation",
        quand=("deploiement", "déploiement", "deployer", "déployer", "ci",
               "pipeline", "docker", "conteneur", "production", "railway",
               "sauvegarde", "restauration", "supervision"),
        methode=(
            "Rendre le déploiement reproductible avant de le rendre rapide.",
            "Vérifier la restauration, pas la sauvegarde — une sauvegarde jamais "
            "restaurée n'existe pas.",
            "Faire échouer bruyamment plutôt que dégrader en silence.",
            "Mesurer avant d'optimiser ; garder la mesure d'avant.",
        ),
        controles=(
            "Le déploiement passe-t-il sur une machine vierge ?",
            "Les secrets viennent-ils de l'environnement, jamais du dépôt ?",
            "Existe-t-il un chemin de retour arrière, et a-t-il été essayé ?",
            "Une panne se voit-elle, ou faut-il aller la chercher ?",
        ),
        fini_quand="le retour arrière a été essayé, pas seulement décrit",
        capacite="REPO_ENGINEERING",
        outils=("pytest", "ruff"),
    ),
    Specialiste(
        identifiant="donnees",
        domaine="Données et bases",
        quand=("base de donnees", "base de données", "sql", "sqlite", "requete",
               "requête", "index", "schema", "schéma", "migration", "donnees",
               "données"),
        methode=(
            "Partir de la question posée aux données, pas de la table.",
            "Mesurer la requête sur un volume réaliste avant de l'indexer.",
            "Rendre la migration réversible, ou dire explicitement qu'elle ne l'est pas.",
            "Traiter un champ absent comme absent — jamais comme zéro.",
        ),
        controles=(
            "La requête a-t-elle été mesurée, ou seulement lue ?",
            "Un champ manquant peut-il être confondu avec une valeur ?",
            "La migration a-t-elle été jouée à l'envers une fois ?",
            "Les données personnelles sont-elles nécessaires à ce qu'on en fait ?",
        ),
        fini_quand="la requête a été chronométrée sur des données réelles",
        capacite="CODE_EXECUTION",
        outils=("bac_a_sable",),
    ),
    Specialiste(
        identifiant="recherche",
        domaine="Recherche et sources",
        quand=("recherche", "sources", "source", "information",
               "etat de l'art", "état de l'art", "comparer", "benchmark",
               "documentation officielle", "verifie", "vérifie"),
        methode=(
            "Poser la question à laquelle une réponse changerait une décision.",
            "Chercher la source primaire avant le commentaire.",
            "Faire dire à chaque affirmation d'où elle vient.",
            "Nommer ce qui reste inconnu au lieu de combler le trou.",
        ),
        controles=(
            "Chaque affirmation porte-t-elle sa source ?",
            "La source est-elle primaire, ou cite-t-elle quelqu'un d'autre ?",
            "Deux sources indépendantes disent-elles la même chose ?",
            "Ce qui n'a pas été trouvé est-il dit comme tel ?",
        ),
        fini_quand="chaque affirmation porte sa source, et les trous sont nommés",
        capacite="DEEP_RESEARCH",
        outils=("recherche_web",),
    ),
    Specialiste(
        identifiant="documents",
        domaine="Lecture de ses propres documents",
        quand=("dans mes documents", "mes fichiers", "le contrat", "le devis de",
               "le pdf", "d'apres le document", "d'après le document",
               "ce que dit le document", "retrouve dans", "mes archives"),
        methode=(
            "Chercher le passage, pas le sujet — une réponse sans passage n'est "
            "pas une lecture.",
            "Citer ce que le document dit, avant d'expliquer ce que ça veut dire.",
            "Dire quel document et quel endroit, pour qu'il puisse vérifier.",
            "Quand les documents ne répondent pas, le dire — au lieu de combler "
            "avec ce que le modèle croit savoir.",
        ),
        controles=(
            "La réponse s'appuie-t-elle sur un passage réel, ou sur une impression ?",
            "Le document est-il nommé ?",
            "Ce qui n'est pas dans les documents est-il signalé comme tel ?",
            "Deux documents se contredisent-ils ? Alors les deux se citent.",
        ),
        fini_quand=("chaque affirmation renvoie à un passage nommé, et ce qui manque "
                    "est dit manquant"),
        capacite="RAG_DOCS",
        outils=("lightrag", "graphrag"),
    ),
    Specialiste(
        identifiant="seo",
        domaine="Référencement",
        quand=("seo", "referencement", "référencement", "google", "mots-cles",
               "mots-clés", "position", "trafic", "balise", "meta description",
               "backlink", "etre trouve", "être trouvé"),
        methode=(
            "Partir de ce que le client TAPE, pas de ce que l'entreprise vend.",
            "Vérifier que la page répond à l'intention derrière la requête.",
            "Corriger ce qui empêche d'être lu avant d'ajouter du contenu : "
            "vitesse, mobile, titres, balises.",
            "Pour un métier local, la fiche établissement et les avis pèsent plus "
            "que les mots-clés.",
            "Mesurer une position avant et après, sinon rien n'a été prouvé.",
        ),
        controles=(
            "Un titre et une méta-description uniques par page",
            "Une seule idée par page, et elle répond à une vraie question",
            "Le site est-il lisible et rapide sur téléphone ?",
            "Nom, adresse et téléphone identiques partout",
            "Le contenu dit-il quelque chose qu'un concurrent ne dit pas ?",
        ),
        fini_quand=("la position ou le trafic a été relevé avant, pour pouvoir "
                    "être comparé après"),
        capacite="DEEP_RESEARCH",
        outils=("recherche_web", "navigateur"),
    ),
    Specialiste(
        identifiant="contenu",
        domaine="Contenu et réseaux",
        quand=("publication", "post", "article", "redaction", "rédaction",
               "accroche", "legende", "légende", "carrousel", "newsletter",
               "ligne editoriale", "ligne éditoriale"),
        methode=(
            "Écrire pour une personne précise, pas pour une audience.",
            "Ouvrir par ce qui l'intéresse, pas par ce qu'on veut dire.",
            "Montrer un chantier réel plutôt que de décrire un savoir-faire.",
            "Une publication, une idée, un appel à agir.",
        ),
        controles=(
            "Est-ce vrai et vérifiable, ou seulement flatteur ?",
            "Un concurrent pourrait-il publier le même texte tel quel ?",
            "La première ligne donne-t-elle envie de lire la deuxième ?",
            "Le ton est-il celui du propriétaire, ou celui d'une agence ?",
        ),
        fini_quand="le texte dit quelque chose que seul le propriétaire pouvait dire",
        capacite="SOCIAL",
        outils=(),
    ),
    Specialiste(
        identifiant="produit",
        domaine="Produit et priorités",
        quand=("priorite", "priorité", "roadmap", "feuille de route",
               "quoi faire d'abord", "arbitrer", "perimetre", "périmètre",
               "besoin", "utilisateur"),
        methode=(
            "Nommer le problème avant la solution — une fonctionnalité n'est pas "
            "un besoin.",
            "Chercher qui souffre aujourd'hui, et combien ça lui coûte.",
            "Trancher sur l'écart entre le coût et la douleur évitée.",
            "Écrire ce qui est HORS périmètre : c'est ce qui protège le délai.",
        ),
        controles=(
            "Le problème est-il décrit sans nommer la solution ?",
            "Sait-on qui souffre, et combien ?",
            "Le hors-périmètre est-il écrit ?",
            "Peut-on savoir, après, si ça a marché ?",
        ),
        fini_quand="le hors-périmètre est écrit et la mesure de succès est définie",
        capacite="DEEP_REASONING",
        outils=(),
    ),
    Specialiste(
        identifiant="affaires",
        domaine="Gestion et chiffrage",
        # Ni « devis », ni « chantier », ni « client » : ce sont les mots de
        # TOUS les jours du proprietaire. « Corrige ce bug dans le module de
        # devis » et « monte une video du chantier » convoquaient la methode
        # de chiffrage, qui n'avait rien a y faire (mesure du 01/09/2026).
        # Ce qui appelle vraiment cette methode, c'est l'ARGENT et les
        # QUANTITES — pas le decor. Pour le reste, l'intention `PLAQUISTE` de
        # l'aiguilleur fait deja le renfort.
        # « un devis » (et pas « devis » seul) : il dit « fais-moi un devis »,
        # jamais « le module de un devis ».
        quand=("un devis", "le devis de", "chiffrer", "chiffrage",
               "facture", "facturer", "marge", "combien ca coute",
               "combien ça coûte", "rentabilite", "rentabilité", "acompte",
               "materiaux", "matériaux", "tresorerie", "trésorerie",
               "prix de revient", "metre", "métré"),
        methode=(
            "Partir des quantités mesurées, jamais d'un prix au jugé.",
            "Séparer fourniture et main-d'œuvre — c'est là que la marge se voit.",
            "Nommer ce qui n'est pas compris dans le prix.",
            "Vérifier que le total tient debout avant de l'écrire sur un document "
            "qui part chez un client.",
        ),
        controles=(
            "Chaque ligne vient-elle d'une quantité mesurée ?",
            "Un article sans prix dans la grille est-il nommé, pas deviné ?",
            "Les exclusions sont-elles écrites ?",
            "Le client, le lieu et l'objet sont-ils justes ?",
        ),
        fini_quand="chaque ligne remonte à une quantité mesurée et à un prix de sa grille",
        capacite="PLAQUISTE",
        outils=("devis", "opentakeoff"),
    ),
    Specialiste(
        identifiant="media",
        domaine="Vidéo, image et voix",
        quand=("video", "vidéo", "montage", "sous-titre", "voix off", "image",
               "photo", "miniature", "format vertical", "reel", "short"),
        methode=(
            "Décider ce que la vidéo doit faire comprendre en cinq secondes.",
            "Monter à partir de ce qui a été filmé, jamais d'un plan imaginé.",
            "Vérifier le fichier produit : durée, format, piste audio présente.",
            "Regarder une image du rendu avant de le déclarer bon.",
        ),
        controles=(
            "Le fichier existe-t-il, et sa durée correspond-elle au projet ?",
            "La piste audio contient-elle du son, ou du silence ?",
            "Le texte incrusté est-il lisible sur téléphone ?",
            "Le format correspond-il à l'endroit où ça sera publié ?",
        ),
        fini_quand="le fichier a été re-sondé après écriture, pas seulement produit",
        capacite="MONTAGE",
        outils=("montage", "audio", "ffmpeg"),
    ),
)


def par_identifiant(identifiant: str) -> Optional[Specialiste]:
    """Le specialiste portant cet identifiant, ou None."""
    for specialiste in CATALOGUE:
        if specialiste.identifiant == identifiant:
            return specialiste
    return None


def identifiants() -> List[str]:
    """Les identifiants, dans l'ordre du catalogue."""
    return [s.identifiant for s in CATALOGUE]
