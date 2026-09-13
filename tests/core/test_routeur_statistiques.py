"""Ce que chaque type de tache coute — mesure, jamais suppose, jamais invente.

Trois proprietes portent ces tests, et chacune ferme une facon de se tromper
cher :

1. **Deux comptes, jamais un.** `CompteurUsage` EST le quota : y faire entrer un
   appel local couperait le cloud sans qu'un appel distant soit parti. La
   statistique, elle, doit prendre le local — l'ignorer la rendrait aveugle sur
   le fournisseur le plus sollicite.
2. **Un taux sur zero passage vaut `None`.** `0.0` se lirait « ce fournisseur
   echoue toujours » et le ferait ecarter alors qu'il n'a jamais ete essaye.
3. **Aucune qualite n'est inventee**, et la mesure ne choisit rien.
"""
import asyncio

import pytest

from core.models.routeur import RouteurModeles
from core.models.statistiques import (
    HORS_INTENTION,
    QUALITE_NON_MESUREE,
    Passage,
    StatistiquesRoutage,
)
from core.models.usage import CompteurUsage
from core.observabilite.fil import tache


class FournisseurDeTest:
    """Un fournisseur deterministe. Le modele reel ne tourne pas ici."""

    def __init__(self, nom: str, casse: bool = False, secondes=0.42):
        self.model_name = nom
        self.configure = True
        self._casse = casse
        self.derniere_mesure = type("Mesure", (), {
            "secondes_total": secondes, "jetons_entree": 10, "jetons_sortie": 20,
        })()

    async def is_available(self):
        return True

    async def generate(self, prompt, system_prompt=None):
        if self._casse:
            raise RuntimeError("panne du fournisseur")
        return "une reponse"


@pytest.fixture
def statistiques(tmp_path) -> StatistiquesRoutage:
    return StatistiquesRoutage(db_path=str(tmp_path / "stats.db"))


@pytest.fixture
def compteur(tmp_path) -> CompteurUsage:
    return CompteurUsage(requetes_par_jour=3, db_path=str(tmp_path / "usage.db"))


def routeur_local(statistiques, compteur, casse=False) -> RouteurModeles:
    """Un routeur sans aucun cloud : tout part en local."""
    return RouteurModeles(
        local=FournisseurDeTest("qwen-local", casse=casse), distants={},
        compteur=compteur, statistiques=statistiques,
    )


def demander(routeur, intention, combien=1):
    async def tout():
        for _ in range(combien):
            with tache(intention):
                try:
                    await routeur.generate("bonjour")
                except RuntimeError:
                    pass  # un echec est une mesure, pas une panne de test
    asyncio.run(tout())


# --------------------------------------------------------------------------
# Deux comptes, jamais un — la propriete centrale
# --------------------------------------------------------------------------

def test_un_appel_local_est_mesure_sans_consommer_le_quota(statistiques, compteur):
    """Le piege, prouve avant d'ecrire le module.

    Trois appels locaux enregistres dans `CompteurUsage` rendraient
    « cloud autorise = False, plafond atteint » alors qu'aucun appel distant
    n'est parti. La statistique les prend ; le quota ne les voit pas.
    """
    routeur = routeur_local(statistiques, compteur)

    demander(routeur, "CHAT", combien=3)

    assert compteur.requetes_aujourdhui == 0, "un appel local a consomme le quota"
    assert compteur.verdict().autorise is True, "le cloud a ete coupe par du local"
    assert statistiques.par_type_de_tache()["passages_totaux"] == 3


def test_un_appel_distant_est_pris_par_les_deux(statistiques, compteur, monkeypatch):
    """Le contre-test : le distant doit continuer d'alimenter le quota."""
    routeur = RouteurModeles(
        local=FournisseurDeTest("qwen-local"),
        distants={"groq": FournisseurDeTest("llama-groq")},
        compteur=compteur, statistiques=statistiques,
    )

    demander(routeur, "CHAT", combien=1)

    assert compteur.requetes_aujourdhui == 1
    assert statistiques.par_type_de_tache()["passages_totaux"] == 1


# --------------------------------------------------------------------------
# Un taux sur zero passage vaut None
# --------------------------------------------------------------------------

def test_un_rapport_vide_ne_pretend_a_aucune_mesure(statistiques):
    """Zero type mesure est une reponse : aucun appel n'a encore eu lieu."""
    rapport = statistiques.par_type_de_tache()

    assert rapport["passages_totaux"] == 0
    assert rapport["par_type_de_tache"] == {}
    assert rapport["types_mesures"] == 0


@pytest.mark.parametrize("numerateur, total, attendu", [
    (0, 0, None),      # la regle : rien a diviser -> pas de taux
    (3, 0, None),
    (0, 2, 0.0),       # zero sur DEUX passages est une mesure, elle
    (1, 2, 0.5),
    (4, 4, 1.0),
])
def test_le_taux_distingue_zero_mesure_et_rien_a_mesurer(numerateur, total, attendu):
    """Le test que le sabotage a reclame (13/09/2026).

    `test_un_taux_sur_zero_passage_vaut_none` ne touchait en realite que le
    rapport vide : il n'atteignait jamais `_taux(n, 0)`. Remplacer `None` par
    `0.0` dans le helper laissait donc **30 tests au vert** — le sabotage l'a
    montre, et c'est exactement ce a quoi il sert.

    La branche n'est pas atteignable par `par_type_de_tache()` (les groupes
    sont construits par `append`, donc jamais vides). Elle est gardee et
    testee **ici, en unite** : c'est une protection contre une division par
    zero si `_resumer` recoit un jour une liste vide, et le contrat qu'elle
    defend — `None` n'est pas `0.0` — est celui qui coute le plus cher a
    perdre dans tout ce module.
    """
    from core.models.statistiques import _taux

    assert _taux(numerateur, total) == attendu


def test_une_mediane_sans_duree_mesuree_vaut_none(statistiques):
    """Un `0.0` se lirait « instantane »."""
    statistiques.enregistrer(Passage(
        type_tache="CHAT", fournisseur="local", modele="qwen",
        succes=True, secondes=None))

    bloc = statistiques.par_type_de_tache()["par_type_de_tache"]["CHAT"]

    assert bloc["mediane_secondes"] is None
    assert bloc["durees_mesurees"] == 0
    assert bloc["passages"] == 1


def test_un_echec_fait_baisser_le_taux_sans_l_annuler(statistiques):
    for succes in (True, True, False, True):
        statistiques.enregistrer(Passage(
            type_tache="CHAT", fournisseur="local", modele="qwen", succes=succes))

    assert statistiques.par_type_de_tache()["par_type_de_tache"]["CHAT"][
        "taux_de_succes"] == 0.75


def test_un_echec_reel_du_fournisseur_est_mesure(statistiques, compteur):
    """Une panne est une mesure : elle entre au rapport, elle ne le vide pas."""
    routeur = routeur_local(statistiques, compteur, casse=True)

    demander(routeur, "CODE_EXECUTION", combien=2)

    bloc = statistiques.par_type_de_tache()["par_type_de_tache"]["CODE_EXECUTION"]
    assert bloc["passages"] == 2
    assert bloc["taux_de_succes"] == 0.0, (
        "zero sur DEUX passages est une mesure ; zero sur ZERO passage serait "
        "une supposition — les deux ne doivent pas se confondre"
    )


# --------------------------------------------------------------------------
# Aucune qualite n'est inventee
# --------------------------------------------------------------------------

def test_la_qualite_est_toujours_nulle_et_dit_pourquoi(statistiques):
    statistiques.enregistrer(Passage(
        type_tache="CHAT", fournisseur="local", modele="qwen", succes=True))

    rapport = statistiques.par_type_de_tache()

    assert rapport["qualite"] == QUALITE_NON_MESUREE
    assert "proprietaire" in rapport["qualite"], (
        "le rapport doit nommer la seule source honnete d'un tel score"
    )
    assert rapport["par_type_de_tache"]["CHAT"]["qualite"] is None


def test_la_mesure_ne_choisit_rien():
    """Structurel : le routeur ne doit LIRE ses statistiques nulle part.

    Un routeur qui changerait son choix d'apres des mesures a peine commencees
    changerait de comportement sur des donnees minces — et pourrait passer
    devant le classement de confidentialite, que l'audit dit de ne pas toucher.
    """
    from pathlib import Path

    source = Path("core/models/routeur.py").read_text(encoding="utf-8")
    lectures = [
        ligne.strip() for ligne in source.splitlines()
        if "self.statistiques" in ligne and "enregistrer" not in ligne
        and "par_type_de_tache" not in ligne and "StatistiquesRoutage" not in ligne
    ]

    assert lectures == [], (
        f"le routeur lit ses propres statistiques : {lectures}. La mesure "
        f"rapporte, elle ne choisit pas."
    )


# --------------------------------------------------------------------------
# Le type de tache vient du fil, pas d'une supposition
# --------------------------------------------------------------------------

def test_chaque_type_de_tache_est_compte_a_part(statistiques, compteur):
    routeur = routeur_local(statistiques, compteur)

    demander(routeur, "CHAT", combien=3)
    demander(routeur, "CODE_EXECUTION", combien=2)

    par_type = statistiques.par_type_de_tache()["par_type_de_tache"]
    assert par_type["CHAT"]["passages"] == 3
    assert par_type["CODE_EXECUTION"]["passages"] == 2


def test_un_appel_sans_intention_n_est_pas_range_sous_chat(statistiques, compteur):
    """Le ranger d'office sous `CHAT` fausserait la statistique cherchee."""
    routeur = routeur_local(statistiques, compteur)

    demander(routeur, None, combien=1)

    par_type = statistiques.par_type_de_tache()["par_type_de_tache"]
    assert HORS_INTENTION in par_type
    assert "CHAT" not in par_type


def test_le_fournisseur_est_detaille_dans_chaque_type(statistiques):
    for fournisseur, succes in (("local", True), ("groq", False), ("groq", True)):
        statistiques.enregistrer(Passage(
            type_tache="CHAT", fournisseur=fournisseur, modele=fournisseur,
            succes=succes))

    par_fournisseur = statistiques.par_type_de_tache()[
        "par_type_de_tache"]["CHAT"]["par_fournisseur"]

    assert par_fournisseur["local"]["taux_de_succes"] == 1.0
    assert par_fournisseur["groq"]["taux_de_succes"] == 0.5


def test_le_repli_est_compte_comme_tel(statistiques):
    statistiques.enregistrer(Passage(type_tache="CHAT", fournisseur="groq",
                                     modele="llama", succes=False, repli=False))
    statistiques.enregistrer(Passage(type_tache="CHAT", fournisseur="local",
                                     modele="qwen", succes=True, repli=True))

    bloc = statistiques.par_type_de_tache()["par_type_de_tache"]["CHAT"]

    assert bloc["taux_de_repli"] == 0.5


# --------------------------------------------------------------------------
# Une mesure ne bloque jamais une reponse
# --------------------------------------------------------------------------

def test_une_ecriture_impossible_ne_leve_pas(statistiques, monkeypatch):
    """Perdre une mesure est regrettable ; empecher une reponse l'est plus."""
    def casse(*_args, **_kwargs):
        raise RuntimeError("disque plein")

    monkeypatch.setattr(statistiques, "_connexion", casse)

    assert statistiques.enregistrer(Passage(
        type_tache="CHAT", fournisseur="local", modele="qwen", succes=True)) is False


def test_le_rapport_porte_sa_note_sur_le_routage(statistiques):
    rapport = statistiques.par_type_de_tache()

    assert "ne choisissent pas" in rapport["note"]
    assert "confidentialite" in rapport["note"]
