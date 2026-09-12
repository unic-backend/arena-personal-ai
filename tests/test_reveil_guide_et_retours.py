"""`workflow_guide` et `formbricks` reveilles, sur l'agent de son metier.

Les deux derniers des cinq connecteurs qu'aucun chemin d'execution
n'atteignait (`tests/test_connecteurs_dormants.py`) :

- `workflow_guide` : « aucun agent ne le consulte » — alors qu'il est
  OPERATIONNEL et ecrit dans `media/rendered/`, le meme dossier et la meme
  route deja servie que le devis.
- `formbricks` : « aucun agent ni route ne les demande ».

Reveilles le 12/09/2026, a la demande du proprietaire, sur
`PlaquisteAgent` : une fiche de pose remise a un ouvrier et un retour de
satisfaction client sont des objets de son metier, pas d'une couche neuve.

Ce que ces tests refusent de laisser passer : un mode operatoire INVENTE.
Sans etapes dictees, aucun fichier ne doit s'ecrire.
"""
import pytest

from agents.plaquiste.plaquiste_agent import (
    PlaquisteAgent,
    demande_les_retours,
    demande_un_guide,
    etapes_dictees,
    titre_du_guide,
)
from core.actions.resultat import Statut, succes


class FauxRegistre:
    def __init__(self, resultat=None):
        self.appels = []
        self._resultat = resultat or succes(
            "generer", "media/rendered/g.pdf", "Guide ecrit.",
            "media/rendered/g.pdf", url="/media/rendered/g.pdf")

    def executer(self, nom, capacite, **parametres):
        self.appels.append((nom, capacite, parametres))
        return self._resultat


class FauxFournisseur:
    model_name = "faux"

    async def generate(self, prompt, system_prompt=None):
        return "reponse"

    async def is_available(self):
        return True


def agent(registre):
    return PlaquisteAgent(provider=FauxFournisseur(), registre=registre)


# --- La detection, deterministe ------------------------------------------------

class TestDetection:
    @pytest.mark.parametrize("texte", [
        "fais-moi un mode operatoire pour la pose\n1. Tracer\n2. Visser",
        "guide de pose en pdf\n- Tracer au sol\n- Poser les rails",
    ])
    def test_une_demande_de_guide_est_reconnue(self, texte):
        assert demande_un_guide(texte) is True

    @pytest.mark.parametrize("texte", [
        "comment poser du BA13 ?",
        "fais-moi un devis pour 18 metres de cloison",
    ])
    def test_une_question_n_est_pas_une_commande_de_document(self, texte):
        assert demande_un_guide(texte) is False

    def test_les_etapes_sont_lues_jamais_devinees(self):
        etapes = etapes_dictees("guide de pose\n1. Tracer au sol\n2) Poser les rails\n- Visser")
        assert [e["titre"] for e in etapes] == ["Tracer au sol", "Poser les rails", "Visser"]

    def test_aucune_etape_dictee_rend_une_liste_vide(self):
        assert etapes_dictees("fais-moi un guide de pose") == []

    def test_le_titre_vient_de_sa_phrase(self):
        assert titre_du_guide("Pose cloison 72/48\n1. Tracer") == "Pose cloison 72/48"

    def test_une_demande_de_retours_est_reconnue(self):
        assert demande_les_retours("montre-moi les retours clients") is True
        assert demande_les_retours("fais le devis") is False


# --- Le guide, sur le vrai agent ------------------------------------------------

class TestGuide:
    async def test_un_guide_avec_ses_etapes_est_reellement_ecrit(self):
        registre = FauxRegistre()

        resultat = await agent(registre).run(
            "mode operatoire pose cloison\n1. Tracer au sol\n2. Poser les rails",
            context={"message_actuel":
                     "mode operatoire pose cloison\n1. Tracer au sol\n2. Poser les rails"})

        assert registre.appels, "le connecteur n'a jamais ete appele"
        nom, capacite, parametres = registre.appels[0]
        assert (nom, capacite) == ("workflow_guide", "generer")
        assert [e["titre"] for e in parametres["etapes"]] == ["Tracer au sol", "Poser les rails"]
        assert parametres["titre"] == "mode operatoire pose cloison"
        assert resultat["status"] == "success"
        assert resultat["document"]["url"] == "/media/rendered/g.pdf", (
            "sans URL, le fichier existe et reste inatteignable depuis son telephone")

    async def test_sans_etapes_aucun_fichier_n_est_ecrit(self):
        """La garantie qui compte : un mode operatoire ne s'invente pas."""
        registre = FauxRegistre()

        resultat = await agent(registre).run(
            "fais-moi un mode operatoire",
            context={"message_actuel": "fais-moi un mode operatoire"})

        assert registre.appels == [], (
            f"un guide a ete ecrit sans etapes dictees : {registre.appels}")
        assert resultat["status"] == "warning"
        assert "etapes" in resultat["response"]

    async def test_une_question_ordinaire_n_ecrit_aucun_guide(self):
        registre = FauxRegistre()

        await agent(registre).run("comment poser du BA13 ?",
                                  context={"message_actuel": "comment poser du BA13 ?"})

        assert all(nom != "workflow_guide" for nom, _, _ in registre.appels)


# --- Les retours clients --------------------------------------------------------

class TestRetoursClients:
    async def test_les_retours_sont_demandes_au_connecteur(self):
        registre = FauxRegistre(resultat=succes(
            "lister", "formbricks", "2 sondage(s).", "formbricks/api"))

        resultat = await agent(registre).run(
            "montre-moi les retours clients",
            context={"message_actuel": "montre-moi les retours clients"})

        assert ("formbricks", "lister") == registre.appels[0][:2]
        assert resultat["status"] == "success"
        assert "sondage" in resultat["response"]

    async def test_formbricks_non_configure_le_dit_sans_rien_inventer(self):
        from core.actions.resultat import echec

        registre = FauxRegistre(resultat=echec(
            "lister", "formbricks",
            "FORMBRICKS_BASE_URL absente : aucun sondage lisible."))

        resultat = await agent(registre).run(
            "les avis clients du mois",
            context={"message_actuel": "les avis clients du mois"})

        assert resultat["status"] == "warning"
        assert "FORMBRICKS_BASE_URL" in resultat["response"]
        assert registre.appels[0][:2] == ("formbricks", "lister")
        assert Statut  # l'import sert la lisibilite du contrat teste
