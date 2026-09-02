"""La file d'attente : quatre choses qui ne peuvent pas arriver.

Le test qui compte le plus est `test_deposer_n_execute_rien` : c'est toute la
raison d'etre du module. Vient ensuite `test_confirmer_deux_fois_n_execute_qu_une_fois`,
parce qu'un double clic sur « envoie » ne doit pas envoyer deux devis.
"""
from datetime import timedelta
from typing import Any, Dict

import pytest

from core.actions.attente import (
    ActionEnAttente,
    EtatAttente,
    FileDAttente,
    parametre_secret,
)
from core.actions.journal import MASQUE
from core.actions.resultat import Statut, echec, succes


class ExecuteurEspion:
    """Note ce qu'on lui demande d'executer, et rend ce qu'on lui a dit de rendre."""

    def __init__(self, resultat=None, leve: bool = False, rend_nimporte_quoi: bool = False):
        self.appels: list = []
        self._resultat = resultat
        self._leve = leve
        self._nimporte_quoi = rend_nimporte_quoi

    def __call__(self, connecteur, capacite, compte=None, **parametres):
        self.appels.append((connecteur, capacite, compte, parametres))
        if self._leve:
            raise ConnectionError("le service ne repond pas")
        if self._nimporte_quoi:
            return {"status": "success"}
        return self._resultat or succes(capacite, connecteur, "Fait.", "preuve-1")


@pytest.fixture
def executeur():
    return ExecuteurEspion()


@pytest.fixture
def file(tmp_path, executeur):
    return FileDAttente(db_path=str(tmp_path / "attente.db"), executeur=executeur)


def _deposer(file: FileDAttente, **remplacements) -> ActionEnAttente:
    valeurs: Dict[str, Any] = {
        "action": "Envoie le devis UC-2026-0827",
        "cible": "client@exemple.sn",
        "risque": "HIGH",
        "resultat_attendu": "Un e-mail part vers le client avec le devis joint.",
        "connecteur": "gmail",
        "capacite": "send",
        "parametres": {"objet": "Devis"},
    }
    valeurs.update(remplacements)
    return file.deposer(**valeurs)


# --- 1. Deposer n'execute rien ------------------------------------------------

def test_deposer_n_execute_rien(file, executeur):
    """La garantie centrale : une action non confirmee ne part pas."""
    _deposer(file)

    assert executeur.appels == []


def test_l_action_deposee_attend(file):
    action = _deposer(file)

    assert file.lire(action.identifiant).etat is EtatAttente.EN_ATTENTE
    assert action.resultat_final is None


def test_lister_les_actions_en_attente_n_execute_rien(file, executeur):
    _deposer(file)
    _deposer(file)

    assert len(file.en_attente()) == 2
    assert executeur.appels == []


def test_annuler_n_execute_rien(file, executeur):
    action = _deposer(file)

    assert file.annuler(action.identifiant) is True
    assert executeur.appels == []
    assert file.lire(action.identifiant).etat is EtatAttente.ANNULEE


def test_une_action_annulee_ne_peut_plus_etre_confirmee(file, executeur):
    action = _deposer(file)
    file.annuler(action.identifiant)

    resultat = file.confirmer(action.identifiant)

    assert resultat.statut is Statut.ECHEC
    assert "CANCELLED" in resultat.message
    assert executeur.appels == []


def test_confirmer_est_le_seul_chemin_qui_execute(file, executeur):
    action = _deposer(file)

    resultat = file.confirmer(action.identifiant)

    assert resultat.statut is Statut.SUCCES
    assert len(executeur.appels) == 1
    assert executeur.appels[0][:3] == ("gmail", "send", None)


# --- 2. Confirmer deux fois n'execute qu'une fois -----------------------------

def test_confirmer_deux_fois_n_execute_qu_une_fois(file, executeur):
    """Un double clic sur « envoie » ne doit pas envoyer deux devis."""
    action = _deposer(file)

    premier = file.confirmer(action.identifiant)
    second = file.confirmer(action.identifiant)

    assert len(executeur.appels) == 1
    assert premier.statut is Statut.SUCCES
    assert second.statut is Statut.ECHEC
    assert "deja" in second.message


def test_la_seconde_confirmation_rappelle_le_resultat_de_la_premiere(file):
    action = _deposer(file)
    file.confirmer(action.identifiant)

    assert "SUCCESS" in file.confirmer(action.identifiant).message


def test_dix_confirmations_n_executent_qu_une_fois(file, executeur):
    action = _deposer(file)

    for _ in range(10):
        file.confirmer(action.identifiant)

    assert len(executeur.appels) == 1


def test_le_resultat_de_l_execution_est_conserve(file):
    action = _deposer(file)
    file.confirmer(action.identifiant)

    assert file.lire(action.identifiant).resultat_final == "SUCCESS"


def test_un_echec_d_execution_est_conserve_tel_quel(tmp_path):
    executeur = ExecuteurEspion(resultat=echec("send", "client", "boite pleine"))
    file = FileDAttente(db_path=str(tmp_path / "a.db"), executeur=executeur)
    action = _deposer(file)

    resultat = file.confirmer(action.identifiant)

    assert resultat.statut is Statut.ECHEC
    assert "boite pleine" in resultat.message
    assert file.lire(action.identifiant).resultat_final == "FAILED"


def test_une_action_echouee_n_est_pas_rejouee(tmp_path):
    """Confirmee reste confirmee, meme quand l'execution a echoue."""
    executeur = ExecuteurEspion(resultat=echec("send", "client", "boite pleine"))
    file = FileDAttente(db_path=str(tmp_path / "a.db"), executeur=executeur)
    action = _deposer(file)
    file.confirmer(action.identifiant)

    file.confirmer(action.identifiant)

    assert len(executeur.appels) == 1


# --- 3. Une confirmation perimee ne part pas ----------------------------------

def test_une_action_perimee_ne_s_execute_pas(tmp_path, executeur):
    file = FileDAttente(db_path=str(tmp_path / "a.db"), executeur=executeur, delai_heures=0)
    action = _deposer(file)

    resultat = file.confirmer(action.identifiant)

    assert resultat.statut is Statut.ECHEC
    assert "expire" in resultat.message
    assert executeur.appels == []


def test_une_action_perimee_disparait_de_la_liste_d_attente(tmp_path):
    file = FileDAttente(db_path=str(tmp_path / "a.db"), delai_heures=0)
    _deposer(file)

    assert file.en_attente() == []


def test_une_action_perimee_est_marquee_expiree(tmp_path):
    file = FileDAttente(db_path=str(tmp_path / "a.db"), delai_heures=0)
    action = _deposer(file)

    file.en_attente()

    assert file.lire(action.identifiant).etat is EtatAttente.EXPIREE


def test_une_action_dans_le_delai_reste_confirmable(file, executeur):
    action = _deposer(file)

    assert file.confirmer(action.identifiant).statut is Statut.SUCCES


def test_le_delai_est_ecrit_dans_l_action(file):
    from datetime import datetime

    action = _deposer(file)
    duree = datetime.fromisoformat(action.expire_le) - datetime.fromisoformat(action.cree_le)

    assert duree == timedelta(hours=24)


def test_une_date_d_expiration_illisible_est_traitee_comme_perimee():
    action = ActionEnAttente("a", "b", "LOW", "c", "gmail", "send", expire_le="pas une date")

    assert action.est_perimee() is True


# --- 4. Aucun secret n'est mis en attente -------------------------------------

@pytest.mark.parametrize("nom", [
    "access_token", "api_key", "password", "mot_de_passe", "client_secret",
    "Authorization", "private_key",
])
def test_un_parametre_secret_fait_refuser_le_depot(file, nom):
    with pytest.raises(ValueError, match="nom de secret"):
        _deposer(file, parametres={nom: "valeur"})


def test_un_secret_imbrique_est_trouve_aussi(file):
    with pytest.raises(ValueError):
        _deposer(file, parametres={"compte": {"oauth": {"access_token": "abc"}}})


def test_un_secret_dans_une_liste_est_trouve_aussi(file):
    with pytest.raises(ValueError):
        _deposer(file, parametres={"comptes": [{"api_key": "k"}]})


def test_le_refus_explique_ou_vont_les_identifiants(file):
    with pytest.raises(ValueError, match="configuration du connecteur"):
        _deposer(file, parametres={"api_key": "k"})


def test_un_depot_refuse_ne_laisse_rien_dans_la_file(file):
    with pytest.raises(ValueError):
        _deposer(file, parametres={"api_key": "k"})

    assert file.en_attente() == []


def test_parametre_secret_rend_none_quand_tout_est_anodin():
    assert parametre_secret({"objet": "Devis", "destinataire": "a@b.c"}) is None


def test_les_parametres_anodins_traversent_intacts(file, executeur):
    action = _deposer(file, parametres={"objet": "Devis UC-2026-0827", "copie": True})
    file.confirmer(action.identifiant)

    assert executeur.appels[0][3] == {"objet": "Devis UC-2026-0827", "copie": True}


def test_le_masquage_reste_un_second_filet():
    """Le refus couvre les noms connus ; le masquage couvre le reste."""
    from core.actions.journal import masquer

    assert masquer({"session_key": "abc"})["session_key"] == MASQUE


# --- L'executeur ---------------------------------------------------------------

def test_sans_executeur_rien_ne_part(tmp_path):
    file = FileDAttente(db_path=str(tmp_path / "a.db"), executeur=None)
    action = _deposer(file)

    resultat = file.confirmer(action.identifiant)

    assert resultat.statut is Statut.NON_IMPLEMENTE
    assert "rien n'a ete envoye" in resultat.message.lower()


def test_un_executeur_qui_leve_devient_un_echec(tmp_path):
    file = FileDAttente(db_path=str(tmp_path / "a.db"), executeur=ExecuteurEspion(leve=True))
    action = _deposer(file)

    resultat = file.confirmer(action.identifiant)

    assert resultat.statut is Statut.ECHEC
    assert "ne repond pas" in resultat.message


def test_un_executeur_qui_rend_un_dictionnaire_devient_un_echec(tmp_path):
    file = FileDAttente(db_path=str(tmp_path / "a.db"),
                        executeur=ExecuteurEspion(rend_nimporte_quoi=True))
    action = _deposer(file)

    assert file.confirmer(action.identifiant).statut is Statut.ECHEC


def test_confirmer_un_identifiant_inconnu_est_une_reponse(file):
    resultat = file.confirmer("jamais-depose")

    assert resultat.statut is Statut.NON_IMPLEMENTE
    assert "jamais-depose" in resultat.message


def test_annuler_un_identifiant_inconnu_rend_false(file):
    assert file.annuler("jamais-depose") is False


# --- Ce qui est montre avant de repondre --------------------------------------

def test_le_resume_montre_les_quatre_lignes_de_la_specification(file):
    lignes = _deposer(file).resume().splitlines()

    assert lignes[0].startswith("ACTION")
    assert lignes[1].startswith("CIBLE")
    assert lignes[2].startswith("RISQUE")
    assert lignes[3].startswith("RESULTAT ATTENDU")


def test_le_resume_porte_les_vraies_valeurs(file):
    resume = _deposer(file).resume()

    assert "UC-2026-0827" in resume
    assert "client@exemple.sn" in resume
    assert "HIGH" in resume
    assert "devis joint" in resume


def test_la_forme_transportable_porte_l_etat_et_l_identifiant(file):
    corps = _deposer(file).to_dict()

    assert corps["etat"] == "PENDING"
    assert len(corps["id"]) == 32
    assert corps["resultat_final"] is None


def test_les_actions_en_attente_reviennent_de_la_plus_recente(file):
    for index in range(3):
        _deposer(file, cible=f"client-{index}@exemple.sn")

    cibles = [a.cible for a in file.en_attente()]

    assert cibles[0] == "client-2@exemple.sn"


# --- 5. Une suggestion non validee ne survit pas -------------------------------

class TestUneSuggestionNonValideeNeSurvitPas:
    """Refusee ou perimee, l'action perd son contenu.

    Demande du proprietaire le 02/09/2026 : « il peut suggerer des reponses
    mais si je valide pas il supprime sa suggestion ».

    Mesure faite avant le correctif : `annuler()` marquait bien l'action
    `CANCELLED`, et le corps du message restait ecrit **en entier** dans
    `data/database/memory.db`, indefiniment. Un message que le proprietaire a
    explicitement refuse d'envoyer n'a aucune raison de rester quelque part.

    Ce qui reste volontairement : la trace (quoi, vers qui, quand, refuse).
    Elle ne contient pas le texte, et elle est ce qui permet a la garantie 2
    (« confirmer deux fois n'execute qu'une fois ») de continuer a repondre
    « deja annulee » plutot que « action inconnue ».
    """

    BROUILLON = {"objet": "Votre devis",
                 "corps": "Bonjour, voici notre proposition a 850000 FCFA."}

    def _contenu_sur_le_disque(self, file, identifiant) -> str:
        """Lit la colonne brute : ce qui est VRAIMENT ecrit, pas ce que l'objet rend."""
        import sqlite3
        with sqlite3.connect(file.db_path) as connexion:
            ligne = connexion.execute(
                f"SELECT parametres FROM {file.TABLE} WHERE identifiant = ?",
                (identifiant,)).fetchone()
        return ligne[0]

    def test_un_refus_efface_le_brouillon_du_disque(self, file):
        action = _deposer(file, parametres=self.BROUILLON)
        assert "850000" in self._contenu_sur_le_disque(file, action.identifiant)

        file.annuler(action.identifiant)

        assert self._contenu_sur_le_disque(file, action.identifiant) == "{}"

    def test_une_action_perimee_efface_aussi_son_brouillon(self, tmp_path, executeur):
        """Ne pas repondre est un refus, plus lent. Le contenu part pareil."""
        file = FileDAttente(db_path=str(tmp_path / "perime.db"),
                            executeur=executeur, delai_heures=0)
        action = _deposer(file, parametres=self.BROUILLON)

        file.en_attente()  # le passage qui marque les perimees

        assert file.lire(action.identifiant).etat is EtatAttente.EXPIREE
        assert self._contenu_sur_le_disque(file, action.identifiant) == "{}"

    def test_la_trace_reste_apres_un_refus(self, file):
        """Ce qui a ete propose et refuse reste lisible — sans le texte."""
        action = _deposer(file, parametres=self.BROUILLON)

        file.annuler(action.identifiant)
        relue = file.lire(action.identifiant)

        assert relue.etat is EtatAttente.ANNULEE
        assert relue.action == "Envoie le devis UC-2026-0827"
        assert relue.cible == "client@exemple.sn"
        assert relue.cree_le
        assert relue.parametres == {}

    def test_confirmer_apres_un_refus_reste_sans_effet(self, file, executeur):
        """L'effacement ne doit pas transformer un refus en action inconnue."""
        action = _deposer(file, parametres=self.BROUILLON)
        file.annuler(action.identifiant)

        resultat = file.confirmer(action.identifiant)

        assert resultat.statut is Statut.ECHEC
        assert "CANCELLED" in resultat.message
        assert executeur.appels == [], "rien ne doit partir apres un refus"

    def test_une_action_confirmee_garde_ses_parametres(self, file, executeur):
        """Le contraire de la garantie : ce qui est parti sur son ordre reste tracable."""
        action = _deposer(file, parametres=self.BROUILLON)

        file.confirmer(action.identifiant)

        assert file.lire(action.identifiant).parametres == self.BROUILLON
        assert executeur.appels, "l'action confirmee doit bien avoir ete executee"
