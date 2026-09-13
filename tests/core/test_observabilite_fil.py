"""Le fil d'une demande : un identifiant, du premier octet HTTP a la derniere action.

Avant le 13/09/2026, `request_id` n'existait **nulle part** — zero occurrence
dans `core/`, `apps/`, `agents/`. `/api/actions` montrait ce qu'ARENA avait
tente, `/api/observability` ce que les voies avaient coute, et rien ne reliait
les deux a une meme demande.

Ce que ces tests tiennent, dans l'ordre ou une erreur couterait cher :

1. **Deux demandes en parallele ne melangent pas leurs fils.** C'est la raison
   d'etre du `contextvars` : avec une variable de module, le journal
   attribuerait les actions de l'un au fil de l'autre — une trace FAUSSE, pire
   qu'aucune trace.
2. **Rien n'est fabrique hors demande.** Un script, une tache de fond, un test
   n'ont pas de demande derriere eux, et `None` le dit.
3. **Un identifiant venu du dehors est une donnee.** Sans validation, un
   appelant ecrirait des retours a la ligne dans le journal, et une fausse
   ligne y serait indiscernable d'une vraie.
"""
import asyncio

import pytest

from core.observabilite.fil import (
    ENTETE,
    LONGUEUR_MAX,
    fil_courant,
    identifiant_acceptable,
    nouveau_fil,
    nouvel_identifiant,
)

# --------------------------------------------------------------------------
# Hors demande, rien n'est invente
# --------------------------------------------------------------------------

def test_hors_demande_le_fil_est_none():
    """`None` est une reponse : « ce qui tourne ne vient pas d'une demande »."""
    assert fil_courant() is None


def test_le_fil_est_rendu_a_la_sortie_du_bloc():
    with nouveau_fil():
        assert fil_courant() is not None

    assert fil_courant() is None


def test_le_fil_est_rendu_meme_si_le_bloc_leve():
    """Sans `finally`, une demande en erreur empoisonnerait la suivante."""
    with pytest.raises(RuntimeError):
        with nouveau_fil("demande-en-echec"):
            raise RuntimeError("panne")

    assert fil_courant() is None


def test_un_fil_imbrique_rend_le_precedent_pas_le_vide():
    """`reset` et non `set(None)` : un sous-fil ne doit pas effacer son parent."""
    with nouveau_fil("externe"):
        with nouveau_fil("interne"):
            assert fil_courant() == "interne"
        assert fil_courant() == "externe"

    assert fil_courant() is None


# --------------------------------------------------------------------------
# Deux demandes en parallele — la raison du contextvars
# --------------------------------------------------------------------------

def test_deux_demandes_simultanees_gardent_chacune_son_fil():
    """Le test qui condamne une variable de module.

    Le serveur est `async` et sert plusieurs demandes a la fois. Avec une
    globale, la seconde ecraserait la premiere et le journal attribuerait les
    actions de l'une au fil de l'autre.
    """
    async def une_demande(nom, attente):
        with nouveau_fil(nom):
            await asyncio.sleep(attente)
            return fil_courant()

    async def les_deux():
        # La premiere attend PLUS longtemps : elle se termine donc apres la
        # seconde, ce qui est exactement le cas ou une globale aurait ete
        # ecrasee entre-temps.
        return await asyncio.gather(
            une_demande("demandeA", 0.02), une_demande("demandeB", 0.001),
        )

    assert asyncio.run(les_deux()) == ["demandeA", "demandeB"]


# --------------------------------------------------------------------------
# Un identifiant venu du dehors est une donnee, jamais une consigne
# --------------------------------------------------------------------------

@pytest.mark.parametrize("propose", [
    "abc123", "trace-du-client", "un_identifiant_valide", "a", "A" * LONGUEUR_MAX,
    "0123456789abcdef0123456789abcdef",
])
def test_un_identifiant_bien_forme_est_adopte(propose):
    assert identifiant_acceptable(propose)
    with nouveau_fil(propose) as retenu:
        assert retenu == propose


@pytest.mark.parametrize("propose, pourquoi", [
    (None, "absent"),
    ("", "vide"),
    ("A" * (LONGUEUR_MAX + 1), "trop long"),
    ("avec espace", "espace"),
    ("deux\nlignes", "retour a la ligne — une fausse ligne de journal"),
    ("avec\ttabulation", "tabulation"),
    ("point.virgule;", "ponctuation"),
    ("<script>", "balise"),
    ("../../etc/passwd", "chemin"),
    ("fil'; DROP TABLE journal_actions--", "injection SQL"),
])
def test_un_identifiant_mal_forme_est_refuse_puis_remplace(propose, pourquoi):
    """Refuse, mais la demande est **servie** : un en-tete mal forme n'est pas
    une raison de ne pas repondre a quelqu'un."""
    assert not identifiant_acceptable(propose), pourquoi

    with nouveau_fil(propose) as retenu:
        assert retenu != propose
        assert identifiant_acceptable(retenu), (
            "le remplacement doit lui-meme etre acceptable"
        )


def test_un_identifiant_genere_est_unique():
    assert len({nouvel_identifiant() for _ in range(1000)}) == 1000


def test_l_entete_suit_la_convention_repandue():
    """En inventer une autre obligerait chaque outil exterieur a apprendre la notre."""
    assert ENTETE == "X-Request-ID"
