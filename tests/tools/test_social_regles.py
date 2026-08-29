"""Les règles d'une publication, vérifiées par une machine.

Ces règles viennent de `charlie947/social-media-skills`, où elles sont écrites
en prose à l'usage d'un modèle. Le test qui porte l'intégration est
`test_une_consigne_n_est_pas_une_garantie` : le modèle a beau recevoir la règle,
c'est le comptage qui décide.
"""
import pytest

from tools.social.idees import FORMATS, matrice, resume
from tools.social.regles import (
    CARACTERES_ACCROCHE,
    LIGNES_MAX,
    MOTS_MIN,
    verifier_accroche,
    verifier_publication,
)


def publication(lignes, mots_par_ligne=8, cta=True):
    """Une publication synthétique qui respecte les règles, sauf ce qu'on casse."""
    corps = [" ".join(["mot"] * mots_par_ligne) for _ in range(lignes)]
    texte = "Accroche courte et nette.\n\nLe contraste tient ici.\n\n" + "\n\n".join(corps)
    return texte + ("\n\nPartage si ca t'a servi ♻" if cta else "")


# --- Le test qui porte l'intégration --------------------------------------------

def test_une_consigne_n_est_pas_une_garantie():
    """Le modèle a reçu « 20 lignes maximum ». Il en a écrit 26."""
    trop = publication(26)

    controle = verifier_publication(trop)

    assert not controle.conforme
    assert any(i.regle == "lignes_max" for i in controle.infractions)
    assert str(LIGNES_MAX) in controle.rendre()


def test_une_publication_conforme_passe():
    controle = verifier_publication(publication(16, mots_par_ligne=11))

    assert controle.conforme, controle.rendre()
    assert MOTS_MIN <= controle.mots


# --- Chaque infraction se nomme et se situe ---------------------------------------

def test_une_infraction_dit_ou_elle_est():
    """« Ce n'est pas conforme » n'aide personne à corriger."""
    texte = publication(10).replace("Accroche courte et nette.",
                                    "Une accroche " + "beaucoup " * 8 + "trop longue")

    controle = verifier_publication(texte)
    accroche = [i for i in controle.infractions if i.regle == "accroche"]

    assert accroche and accroche[0].ligne == 1
    assert str(CARACTERES_ACCROCHE) in accroche[0].detail


def test_le_tiret_cadratin_est_refuse():
    controle = verifier_publication(publication(10) + "\n\nUn tiret — ici.")

    assert any(i.regle == "tiret_cadratin" for i in controle.infractions)


def test_un_emoji_est_refuse_mais_pas_le_symbole_de_partage():
    avec_emoji = verifier_publication(publication(10) + "\n\nBravo 🚀")
    sans = verifier_publication(publication(10))

    assert any(i.regle == "emoji" for i in avec_emoji.infractions)
    assert not any(i.regle == "emoji" for i in sans.infractions)


def test_une_voix_peut_autoriser_les_emojis():
    """La règle vient de la source ; sa voix peut la desserrer."""
    controle = verifier_publication(publication(10) + "\n\nBravo 🚀",
                                    autoriser_emoji=True)

    assert not any(i.regle == "emoji" for i in controle.infractions)


def test_l_appel_a_l_action_manquant_est_signale():
    controle = verifier_publication(publication(10, cta=False))

    assert any(i.regle == "cta" for i in controle.infractions)


def test_une_publication_vide_le_dit():
    controle = verifier_publication("   ")

    assert not controle.conforme
    assert controle.infractions[0].regle == "vide"


def test_aucune_correction_automatique():
    """On mesure, on rapporte. Réécrire son texte sans le dire serait pire."""
    texte = publication(26)

    controle = verifier_publication(texte)

    assert "26" not in str(controle.to_dict().get("texte", ""))
    assert "texte" not in controle.to_dict(), "le controle ne rend pas un texte reecrit"


# --- Les crochets -------------------------------------------------------------------

def test_un_crochet_de_deux_lignes_courtes_passe():
    assert verifier_accroche("3 chantiers, 1 erreur.\nCelle-la m'a coute cher.").conforme


def test_un_crochet_trop_long_est_compte():
    """« 40 characters maximum per line. Count them. » — c'est fait."""
    controle = verifier_accroche("a" * 45 + "\nb" * 3)

    assert any(i.regle == "longueur" and i.ligne == 1 for i in controle.infractions)


def test_une_question_en_premiere_ligne_est_refusee():
    controle = verifier_accroche("Tu veux gagner du temps ?\nVoici comment.")

    assert any(i.regle == "question" for i in controle.infractions)


def test_un_crochet_d_une_seule_ligne_est_refuse():
    controle = verifier_accroche("Une seule ligne.")

    assert any(i.regle == "deux_lignes" for i in controle.infractions)


# --- La matrice d'idées ---------------------------------------------------------------

def test_la_matrice_rend_le_compte_qu_elle_annonce():
    """« 32+ post ideas » : ici c'est calculé, pas promis."""
    idees = matrice(["cloisons", "plafonds", "isolation", "devis"])

    assert len(idees) == 4 * len(FORMATS)
    assert resume(idees)["total"] == len(idees)


def test_sans_pilier_aucune_idee_n_est_inventee():
    assert matrice([]) == []
    assert matrice(["", "   "]) == []


def test_un_sujet_deja_publie_ne_revient_pas():
    complet = matrice(["cloisons"])
    deja = f"{complet[0].format} cloisons"

    restant = matrice(["cloisons"], deja_publies=[deja])

    assert len(restant) == len(complet) - 1


@pytest.mark.parametrize("format_attendu", ["chantier", "erreur", "chiffre"])
def test_les_formats_couvrent_ce_qu_un_artisan_raconte(format_attendu):
    assert format_attendu in FORMATS
