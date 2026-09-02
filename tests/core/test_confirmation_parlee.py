"""Dire « oui » suffit — mais jamais pour ce qui ne se rattrape pas.

Ce fichier existe à cause d'un défaut mesuré le 02/09/2026 sur une capture
d'écran du propriétaire. Usman préparait son devis PDF et affichait :

    Confirme avec l'identifiant aaffc054d9854d7abb94dc278bf90a44.

Il répondait « Fait le en pdf c'est bon ». Rien. Et **rien ne pouvait se
passer** : `POST /api/actions/{id}/confirm` existait côté serveur et aucun
client ne l'appelait jamais. C'est la raison pour laquelle il n'a jamais
obtenu un seul PDF.

`test_sa_phrase_exacte_confirme` est le test qui porte la correction.
`test_un_envoi_de_mail_ne_se_confirme_jamais_par_une_phrase` est celui qui
protège ce que la correction ne doit pas ouvrir.
"""
import tempfile
from pathlib import Path

import pytest

from core.actions.attente import ActionEnAttente, FileDAttente
from core.actions.confirmation_parlee import (
    a_confirmer_par_phrase,
    confirmable_par_phrase,
    est_une_confirmation,
)


class RegistreDouble:
    """Rend le service et l'action de politique, comme le vrai registre."""

    def __init__(self, couples):
        # {nom_connecteur: (service, {capacite: action_de_politique})}
        self._couples = couples

    def obtenir(self, nom):
        if nom not in self._couples:
            return None
        service, capacites = self._couples[nom]

        class Capacite:
            def __init__(self, action):
                self.action = action

        class Connecteur:
            def __init__(self):
                self.service = service

            def capacites(self):
                return {n: Capacite(a) for n, a in capacites.items()}

        return Connecteur()


REGISTRE = RegistreDouble({
    "devis": ("plaquiste", {"produire": "document"}),
    "gmail": ("email", {"envoyer": "send", "lister": "read"}),
    "social": ("social", {"publier": "publish"}),
})


def _action(connecteur="devis", capacite="produire") -> ActionEnAttente:
    return ActionEnAttente(
        action="Ecrit le devis PDF", cible="demonstration", risque="MEDIUM",
        resultat_attendu="un fichier", connecteur=connecteur, capacite=capacite)


# --- Ce qui vaut « oui » --------------------------------------------------------

class TestCeQuiVautOui:
    def test_sa_phrase_exacte_confirme(self):
        """La phrase reellement tapee par le proprietaire, capture du 02/09/2026."""
        assert est_une_confirmation("Fait le en pdf c'est bon") is True

    @pytest.mark.parametrize("phrase", [
        "oui", "ok", "c'est bon", "vas-y", "vas y", "je confirme", "valide",
        "d'accord", "parfait", "nickel", "fais-le",
    ])
    def test_les_accords_francs(self, phrase):
        assert est_une_confirmation(phrase) is True

    def test_le_vide_ne_confirme_rien(self):
        assert est_une_confirmation("") is False
        assert est_une_confirmation("   ") is False


class TestCeQuiNeVautPasOui:
    """Le coût des deux erreurs n'est pas le même.

    Ne pas reconnaître un accord fait retaper trois lettres. En reconnaître un
    à tort produit un document que le propriétaire allait corriger.
    """

    @pytest.mark.parametrize("phrase", [
        "oui mais change le prix",
        "ok par contre ajoute la peinture",
        "ok mais d'abord corrige la quantite",
        "c'est bon ? je ne sais pas",
        "attends",
        "non",
        "annule",
        "pourquoi c'est si cher",
        "combien ca fait",
        "fais-moi un devis demonstration",
    ])
    def test_une_phrase_qui_demande_autre_chose(self, phrase):
        assert est_une_confirmation(phrase) is False

    def test_une_phrase_longue_n_est_pas_un_accord(self):
        """Plus la phrase est longue, moins « ok » en est le sujet."""
        longue = "ok alors reprends tout depuis le debut avec les nouvelles mesures du chantier"

        assert est_une_confirmation(longue) is False


# --- Ce qu'une phrase a le droit de confirmer -------------------------------------

class TestUnePhraseNeConfirmeQueCeQuiResteSurLaMachine:
    """La règle qui n'est pas négociable.

    Écrire un fichier se défait — on le supprime. Envoyer un mail, publier,
    supprimer chez un fournisseur : cela ne se rattrape pas. Le partage n'est
    pas décidé ici : il lit `INTERRUPTEURS_OBLIGATOIRES`, le plancher que le
    dépôt tient déjà pour ces trois effets.
    """

    def test_un_document_se_confirme_par_une_phrase(self):
        assert confirmable_par_phrase(_action(), REGISTRE) is True

    def test_un_envoi_de_mail_ne_se_confirme_jamais_par_une_phrase(self):
        """Le test qui protège ce que la correction ne doit pas ouvrir."""
        envoi = _action(connecteur="gmail", capacite="envoyer")

        assert confirmable_par_phrase(envoi, REGISTRE) is False

    def test_une_publication_non_plus(self):
        publication = _action(connecteur="social", capacite="publier")

        assert confirmable_par_phrase(publication, REGISTRE) is False

    def test_un_connecteur_illisible_repond_non(self):
        """Un doute répond non : on ne sait pas ce qu'on autoriserait."""
        assert confirmable_par_phrase(_action(connecteur="inconnu"), REGISTRE) is False
        assert confirmable_par_phrase(_action(capacite="disparue"), REGISTRE) is False
        assert confirmable_par_phrase(_action(), None) is False


class TestLeChoixDeLActionAConfirmer:
    def test_le_document_seul_est_choisi(self):
        devis = _action()

        assert a_confirmer_par_phrase([devis], REGISTRE) is devis

    def test_rien_en_attente_ne_choisit_rien(self):
        assert a_confirmer_par_phrase([], REGISTRE) is None

    def test_un_envoi_seul_n_est_jamais_choisi(self):
        envoi = _action(connecteur="gmail", capacite="envoyer")

        assert a_confirmer_par_phrase([envoi], REGISTRE) is None

    def test_deux_actions_en_attente_ne_choisissent_rien(self):
        """« oui » ne dit pas laquelle, et choisir à sa place est exactement ce
        qu'une confirmation existe pour empêcher."""
        devis = _action()
        envoi = _action(connecteur="gmail", capacite="envoyer")

        assert a_confirmer_par_phrase([devis, envoi], REGISTRE) is None

    def test_deux_documents_non_plus(self):
        assert a_confirmer_par_phrase([_action(), _action()], REGISTRE) is None


class TestBoutEnBoutSurLaVraieFile:
    """La phrase confirme vraiment, et l'action part vraiment."""

    def test_confirmer_par_phrase_execute_l_action(self):
        appels = []

        def executeur(connecteur, capacite, compte=None, **parametres):
            from core.actions.resultat import succes
            appels.append((connecteur, capacite))
            return succes(capacite, connecteur, "PDF ecrit.", "/tmp/devis.pdf")

        file = FileDAttente(db_path=str(Path(tempfile.mkdtemp()) / "a.db"),
                            executeur=executeur)
        file.deposer(
            action="Ecrit le devis PDF", cible="demonstration", risque="MEDIUM",
            resultat_attendu="un fichier", connecteur="devis", capacite="produire")

        choisie = a_confirmer_par_phrase(file.en_attente(), REGISTRE)
        assert choisie is not None
        resultat = file.confirmer(choisie.identifiant)

        assert appels == [("devis", "produire")]
        assert resultat.preuve == "/tmp/devis.pdf"
