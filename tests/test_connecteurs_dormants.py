"""Un connecteur qu'aucun chemin d'exécution n'atteint est mort.

**Trois fois le même défaut, en deux jours** :

- DEC-0061 : OpenViking, atteignable par le graphe d'imports, jamais par une
  vraie conversation.
- DEC-0066 : le clonage vocal, complet dans l'agent et le connecteur, mais
  qu'aucune phrase du propriétaire ne pouvait atteindre.
- DEC-0068 (ici) : `gitingest` enregistré, testé, diagnostiqué par
  `doctor.py` — et appelé par **rien**.

`scripts/orphelins.py` tient déjà cette garantie pour les MODULES. Ce test la
tient pour les CONNECTEURS, qui échappent à la mesure des modules : leur
fichier est bel et bien importé par `apps/backend/runtime.py`, donc jamais
orphelin, alors même qu'aucun appelant ne les exécute jamais.

**Ce que ce test mesure**, sans rien croire sur parole : pour chaque
connecteur enregistré, il cherche son nom cité dans du code de production
ailleurs que dans son propre module et dans le runtime qui l'enregistre.

`DORMANTS_CONNUS` n'est pas une exemption confortable : c'est la liste de ce
qui est **réellement injoignable aujourd'hui**, et chaque entrée porte sa
raison. Le test échoue dans les DEUX sens — un connecteur qui s'endort sans
entrer dans la liste, et un connecteur réveillé qu'on aurait oublié d'en
sortir.
"""
import ast
import inspect
from functools import lru_cache
from pathlib import Path

import pytest

from scripts.orphelins import MOTEURS_EXTERNES

RACINE = Path(__file__).resolve().parent.parent

#: Les connecteurs qu'AUCUN chemin d'exécution n'atteint, au 07/09/2026,
#: mesurés par l'audit profond. Chacun existe, est testé et répond à
#: `doctor.py` — mais aucune phrase du propriétaire, aucune route et aucun
#: agent ne peut les faire tourner.
#:
#: Les y laisser est une DÉCISION, pas un oubli : leur brancher un chemin
#: demande de choisir où, et ce choix appartient au propriétaire. Ce qui ne
#: se négocie pas, c'est qu'ils ne se déclarent nulle part comme
#: opérationnels tant qu'ils sont ici.
DORMANTS_CONNUS = {
    # 22/09/2026 : vide. Le dernier dormant, txtai_search, est maintenant
    # joignable depuis le vrai chat PWA et le chat autonome pour une
    # comparaison explicite. Il ne remplace toujours jamais le moteur par
    # defaut : DEC-0051 reste gardee par TestPasDeRoutageAutomatique.
    #
    # 29/09/2026 : deux entrees, mesurees par la correction de `_propre_module`.
    # Le plan annonce au proprietaire branche les connecteurs d'abord, puis
    # l'aiguillage de JARVIS vers eux (etape 4) : c'est cette etape qui les
    # sortira d'ici, et `test_un_connecteur_reveille_sort_de_la_liste` l'y
    # obligera.
    "meta": ("Aucune phrase n'atteint encore Facebook ni Instagram : SocialAgent "
             "soumet toujours ses publications a tiktok. L'aiguillage par reseau "
             "est l'etape 4 du plan (DEC-0179)."),
    "netlify": ("Aucun agent ni route n'interroge encore les sites Netlify : "
                "l'aiguillage de JARVIS vers eux est l'etape 4 du plan (DEC-0180)."),
}


def _connecteurs_enregistres():
    from apps.backend.runtime import registre
    return sorted(getattr(registre, "_fabriques", {}).keys())


#: Les deux fichiers qui NOMMENT chaque connecteur sans l'appeler : celui qui
#: les enregistre, et le registre lui-meme. Les compter ferait passer tout
#: connecteur enregistre pour vivant.
FICHIERS_NEUTRES = ("apps/backend/runtime.py", "core/connectors/registre.py")


def _fichiers_de_production():
    """Les modules où un appel à un connecteur compterait vraiment.

    **Mesuré le 08/09/2026** : sans l'exclusion ci-dessous, ce parcours entre
    dans `tools/vision/faceplugin/.../.venv/` — un SDK externe installé sur
    la machine, gitignoré, jamais notre code (`scripts/orphelins.py` porte
    déjà l'exclusion, mesurée là le 03/09/2026 : « plus de 3000 modules »).

    **Ne prend plus le nom du connecteur en argument, mesure du 19/09/2026.**
    Il le prenait, et le fichier était donc relu et `ast.parse` une fois PAR
    connecteur enregistré — une quarantaine de parcours complets du dépôt,
    41 s par test, et deux tests le faisaient chacun de son côté : 82 s pour
    une mesure qui tient en une passe. Le module de chaque connecteur reste
    écarté, mais à la fin, sur le chemin déjà relevé — pas en relisant tout.
    """
    for dossier in ("agents", "core", "apps", "tools", "social"):
        for fichier in (RACINE / dossier).rglob("*.py"):
            relatif = fichier.relative_to(RACINE).as_posix()
            if any(relatif.startswith(m) for m in MOTEURS_EXTERNES):
                continue
            if relatif in FICHIERS_NEUTRES:
                continue
            yield relatif, fichier


@lru_cache(maxsize=1)
def _noms_cites() -> dict:
    """Chaque chaîne littérale citée en position d'appel, et où.

    Une seule passe sur le dépôt, quel que soit le nombre de connecteurs.
    La règle est mot pour mot celle d'avant — seul le nombre de lectures
    change.

    **Mesure du 07/09/2026** : une première version cherchait la chaîne au
    `grep`, et comptait donc les COMMENTAIRES. Sabotage à l'appui : débrancher
    l'appel réel laissait le test au vert, parce que le mot restait dans la
    docstring juste au-dessus. Un test qui compte les commentaires ne mesure
    rien — la même faute que celles trouvées la veille sur le filtre de
    clonage et sur la sonde du navigateur.

    La deuxième, par AST, comptait encore une étiquette d'affichage
    (`return vu, "gitingest"`) comme un appel. La troisième, limitée au
    premier argument du registre, déclarait mort `claude_context`, qui passe
    par une fonction intermédiaire.

    La règle qui tient les trois sabotages : le nom EXACT en argument d'un
    appel — ce qui exclut les commentaires, les docstrings, les messages de
    journal (qui contiennent le nom sans lui être égaux) et les étiquettes de
    retour, tout en attrapant l'indirection par une fonction.
    """
    cites: dict = {}

    def relever(valeur, relatif, ligne):
        if isinstance(valeur, str):
            cites.setdefault(valeur, []).append((relatif, f"{relatif}:{ligne}"))

    for relatif, fichier in _fichiers_de_production():
        try:
            arbre = ast.parse(fichier.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):  # pragma: no cover
            continue

        for noeud in ast.walk(arbre):
            # 1. Le nom EXACT passé en argument d'un appel. Couvre l'appel
            #    direct (`registre.executer("gitingest", ...)`) ET le passage
            #    par une fonction intermédiaire — `_executer_connecteur(
            #    registre, "claude_context", ...)` dans `recherche_unifiee`,
            #    que la seule lecture du premier argument déclarait mort à
            #    tort (mesure du 07/09/2026).
            if isinstance(noeud, ast.Call):
                for argument in list(noeud.args) + [m.value for m in noeud.keywords]:
                    if isinstance(argument, ast.Constant):
                        relever(argument.value, relatif, noeud.lineno)

            # 2. La constante de module : `CONNECTEUR = "formel"`, puis
            #    `registre.executer(CONNECTEUR, ...)` — le motif de
            #    `audio_agent.py` et `formel_agent.py`.
            elif (isinstance(noeud, ast.Assign)
                    and isinstance(noeud.value, ast.Constant)):
                relever(noeud.value.value, relatif, noeud.lineno)

    # 3. L'injection : `runtime.py` est neutre parce qu'il DECLARE chaque
    #    connecteur, mais `connecteur_case=registre.obtenir("case")` y remet
    #    le connecteur a un agent qui l'execute — un vrai chemin. Seul
    #    `obtenir(...)` compte dans ce fichier, jamais `declarer(...)`
    #    (mesure du 29/09/2026 : sans cette regle, `case`, appele par
    #    Dioumtoukay, passait pour dormant).
    runtime = RACINE / "apps/backend/runtime.py"
    for noeud in ast.walk(ast.parse(runtime.read_text(encoding="utf-8"))):
        if (isinstance(noeud, ast.Call) and isinstance(noeud.func, ast.Attribute)
                and noeud.func.attr == "obtenir"):
            for argument in noeud.args:
                if isinstance(argument, ast.Constant):
                    relever(argument.value, "apps/backend/runtime.py", noeud.lineno)

    return cites


@lru_cache(maxsize=None)
def _propre_module(nom: str) -> str:
    """Le fichier de la classe que la fabrique construit, là où il est.

    **Mesure du 29/09/2026** : ce test supposait `core/connectors/<nom>.py`.
    Le connecteur `meta` vit dans `social/meta/meta_connector.py` : sa propre
    ligne `nom = "meta"` comptait comme un appelant, et un connecteur
    qu'aucune phrase n'atteignait passait pour vivant. Le module est lu sur la
    fabrique elle-même, sans construire le connecteur.
    """
    from apps.backend.runtime import registre
    from core.connectors.base import Connecteur

    fabrique = registre._fabriques.get(nom)
    code = getattr(fabrique, "__code__", None)
    espace = getattr(fabrique, "__globals__", {})
    for symbole in (code.co_names if code else ()):
        objet = espace.get(symbole)
        if inspect.isclass(objet) and issubclass(objet, Connecteur):
            return Path(inspect.getsourcefile(objet)).resolve().relative_to(RACINE).as_posix()
    return f"core/connectors/{nom}.py"


def _appelants(nom: str):
    """Le code de production qui NOMME ce connecteur — dans du vrai code.

    Son propre module ne compte pas : un connecteur qui se cite lui-même
    n'est appelé par personne.
    """
    propre_module = _propre_module(nom)
    return [endroit for relatif, endroit in _noms_cites().get(nom, [])
            if relatif != propre_module]


def test_aucun_connecteur_ne_s_endort_en_silence():
    """Un connecteur neuf sans appelant doit faire échouer ce test, pas dormir."""
    dormants = {c for c in _connecteurs_enregistres() if not _appelants(c)}

    nouveaux = dormants - set(DORMANTS_CONNUS)

    assert nouveaux == set(), (
        f"Ces connecteurs sont enregistrés mais AUCUN code ne les appelle : "
        f"{sorted(nouveaux)}. Soit tu leur branches un chemin réel (agent, "
        f"route, ou couche existante), soit tu les ajoutes à DORMANTS_CONNUS "
        f"avec la raison — mais ils ne peuvent pas se déclarer opérationnels.")


def test_un_connecteur_reveille_sort_de_la_liste():
    """Une exemption survit toujours à sa raison. Elle doit partir avec elle.

    C'est la leçon de `scripts/orphelins.py`, qui a gardé une exemption pour
    `apps.pwa.server.*` bien après la suppression du dossier.
    """
    dormants = {c for c in _connecteurs_enregistres() if not _appelants(c)}

    reveilles = set(DORMANTS_CONNUS) - dormants

    assert reveilles == set(), (
        f"Ces connecteurs sont déclarés dormants mais ont maintenant un "
        f"appelant : {sorted(reveilles)}. Retire-les de DORMANTS_CONNUS.")


@pytest.mark.parametrize("nom", sorted(DORMANTS_CONNUS))
def test_chaque_dormant_porte_sa_raison(nom):
    """Une liste de noms sans raisons se fait vider par le prochain qui passe."""
    raison = DORMANTS_CONNUS[nom]

    assert len(raison) > 25 and raison.endswith("."), (
        f"la raison de {nom} n'explique rien : « {raison} »")


def test_txtai_a_bien_ete_reveille_sans_devenir_le_moteur_par_defaut():
    """Le dernier dormant a un vrai appelant, mais reste un banc explicite."""
    appelants = _appelants("txtai_search")

    assert appelants, "txtai_search est redevenu dormant"
    assert any("knowledge/vault.py" in ligne for ligne in appelants), (
        "txtai_search n'est plus relie au Knowledge Vault : "
        f"appelants trouves = {appelants}"
    )


def test_gitingest_a_bien_ete_reveille():
    """DEC-0068 : il était dormant, il ne doit plus l'être.

    Ce test est le miroir du correctif : `RepoEngineerAgent` analysait une
    architecture avec 30 lignes d'arborescence pendant que `gitingest`
    dormait. S'il redevient injoignable, c'est ici qu'on le verra.
    """
    appelants = _appelants("gitingest")

    assert appelants, "gitingest est redevenu dormant"
    assert any("repo_engineer" in ligne for ligne in appelants), (
        "gitingest n'est plus appelé par l'agent d'analyse de dépôt : "
        f"appelants trouvés = {appelants}")
