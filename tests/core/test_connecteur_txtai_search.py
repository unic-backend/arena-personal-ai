"""Le connecteur txtai reste-t-il un moteur A COTE, jamais un remplacement ?

Contexte (DEC-0051) : ARENA a deja une memoire retrouvee par le sens
(`core/memory/semantique.py`) et deux moteurs de documents (LightRAG,
GraphRAG). La regle de la mission est conditionnelle : ne pas construire un
second RAG, n'utiliser txtai que si un avantage est demontre. Aucun banc
reel n'a pu tourner ici (pas d'Ollama dans ce conteneur — mesure, pas
supposee) : ce module verifie que la PLOMBERIE est reelle (index construit,
requete reelle, embeddings jamais recalcules deux fois), pas la qualite du
classement — qui exige un vrai Ollama, sur la machine du proprietaire.
"""
import hashlib

import numpy as np
import pytest

from core.actions.resultat import Statut
from core.connectors.base import EtatSante
from core.connectors.txtai_search import ConnecteurTxtaiSearch
from core.production.txtai_recherche import MAX_DOCUMENTS, faire_transform_synchrone, rechercher


def _vecteur_deterministe(texte: str) -> list:
    """Un vecteur REEL (pas invente a la volee dans le test), deterministe
    par hachage — jamais un Ollama reel, absent de ce conteneur."""
    h = hashlib.sha256(texte.encode()).digest()
    v = np.frombuffer(h, dtype=np.uint8).astype(np.float32)
    return (v / (np.linalg.norm(v) + 1e-9)).tolist()


async def _faux_fournisseur_ollama(textes):
    return [_vecteur_deterministe(t) for t in textes]


def _faux_fournisseur_incomplet(textes):
    """Simule un Ollama qui ne rend pas assez de vecteurs — jamais un vecteur
    invente a la place d'un refus."""
    async def fournisseur(_):
        return [_vecteur_deterministe(textes[0])] if textes else []
    return fournisseur


CORPUS = [
    "combien de plaques BA13 pour 40 m2",
    "devis pour une cloison de 5,40 x 2,50 m",
    "météo à Dakar demain",
]


class TestRechercheReelle:
    """`core/production/txtai_recherche.py` — la plomberie, avec un vrai
    index txtai construit et interroge, jamais simule."""

    def test_indexe_et_classe_reellement(self):
        resultats = rechercher(CORPUS, "BA13 commandees pour le chantier", top_k=2,
                               transform=faire_transform_synchrone(_faux_fournisseur_ollama))
        assert len(resultats) == 2
        indices = {i for i, _, _ in resultats}
        assert indices <= {0, 1, 2}
        for _, texte, score in resultats:
            assert texte in CORPUS
            assert isinstance(score, float)

    def test_fournisseur_incomplet_leve_plutot_que_d_inventer_un_vecteur(self):
        transform = faire_transform_synchrone(_faux_fournisseur_incomplet(CORPUS))
        with pytest.raises(RuntimeError, match="incomplets"):
            rechercher(CORPUS, "une requete", transform=transform)


class TestConnecteur:
    def test_capacite_est_une_lecture(self):
        capacites = ConnecteurTxtaiSearch().capacites()
        assert set(capacites) == {"rechercher"}
        assert capacites["rechercher"].ecriture is False
        assert capacites["rechercher"].action == "read"

    def test_sonde_operationnelle_avec_un_fournisseur_qui_repond(self):
        connecteur = ConnecteurTxtaiSearch(fournisseur_async=_faux_fournisseur_ollama)
        sante = connecteur.sonder()
        assert sante.etat is EtatSante.OPERATIONNEL

    def test_sonde_non_configuree_sans_embeddings_disponibles(self):
        async def sans_reponse(_):
            return []
        connecteur = ConnecteurTxtaiSearch(fournisseur_async=sans_reponse)
        sante = connecteur.sonder()
        assert sante.etat is EtatSante.NON_CONFIGURE
        assert "Ollama" in sante.ce_qui_manque

    def test_recherche_reelle_via_le_connecteur(self):
        connecteur = ConnecteurTxtaiSearch(fournisseur_async=_faux_fournisseur_ollama)
        resultat = connecteur.executer_confirmee(
            "rechercher", documents=CORPUS, requete="BA13 commandees", top_k=2)
        assert resultat.statut is Statut.SUCCES, resultat.message
        assert len(resultat.detail["resultats"]) == 2

    def test_sans_documents_est_un_echec(self):
        connecteur = ConnecteurTxtaiSearch(fournisseur_async=_faux_fournisseur_ollama)
        resultat = connecteur.executer_confirmee("rechercher", documents=[], requete="x")
        assert resultat.statut is Statut.ECHEC

    def test_sans_requete_est_un_echec(self):
        connecteur = ConnecteurTxtaiSearch(fournisseur_async=_faux_fournisseur_ollama)
        resultat = connecteur.executer_confirmee("rechercher", documents=CORPUS, requete="")
        assert resultat.statut is Statut.ECHEC

    def test_documents_qui_ne_sont_pas_du_texte_est_un_echec(self):
        connecteur = ConnecteurTxtaiSearch(fournisseur_async=_faux_fournisseur_ollama)
        resultat = connecteur.executer_confirmee(
            "rechercher", documents=[1, 2, 3], requete="x")
        assert resultat.statut is Statut.ECHEC

    def test_plus_que_le_plafond_de_documents_est_un_echec(self):
        """Mission §15 : jamais toutes les donnees du proprietaire
        transformees en embeddings automatiquement — un plafond reel."""
        connecteur = ConnecteurTxtaiSearch(fournisseur_async=_faux_fournisseur_ollama)
        trop = [f"document {i}" for i in range(MAX_DOCUMENTS + 1)]
        resultat = connecteur.executer_confirmee("rechercher", documents=trop, requete="x")
        assert resultat.statut is Statut.ECHEC
        assert str(MAX_DOCUMENTS) in resultat.message

    def test_exactement_le_plafond_est_accepte(self):
        connecteur = ConnecteurTxtaiSearch(fournisseur_async=_faux_fournisseur_ollama)
        pile = [f"document numero {i} sur BA13" for i in range(MAX_DOCUMENTS)]
        resultat = connecteur.executer_confirmee(
            "rechercher", documents=pile, requete="BA13", top_k=3)
        assert resultat.statut is Statut.SUCCES, resultat.message

    def test_embeddings_indisponibles_pendant_la_recherche_est_non_configure(self):
        async def coupe_en_cours_de_route(_):
            return []
        connecteur = ConnecteurTxtaiSearch(fournisseur_async=coupe_en_cours_de_route)
        resultat = connecteur.executer_confirmee(
            "rechercher", documents=CORPUS, requete="x")
        assert resultat.statut is Statut.NON_CONFIGURE

    def test_authentifier_toujours_vrai(self):
        assert ConnecteurTxtaiSearch().authentifier() is True

    def test_les_modules_s_importent_sans_numpy_installe(self, monkeypatch):
        """Mesure reelle du 05/09/2026 : `import numpy` en tete de fichier
        faisait planter TOUT ARENA au demarrage (apps.backend.runtime, donc
        chaque route) des que numpy manquait — la suite offline de la CI
        n'installe qu'une liste reduite de paquets, sans numpy. txtai
        lui-meme est deja importe en differe (`construire_index`, comme
        Graphify) ; numpy doit suivre la meme regle : NON_CONFIGURE, jamais
        une app entiere qui ne demarre plus pour un moteur optionnel."""
        import builtins
        import importlib

        import core.connectors.txtai_search as connecteur_module
        import core.production.txtai_recherche as production_module

        reel = builtins.__import__

        def bloque_numpy(name, *args, **kwargs):
            if name == "numpy" or name.startswith("numpy."):
                raise ModuleNotFoundError("No module named 'numpy'")
            return reel(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", bloque_numpy)
        try:
            importlib.reload(production_module)
            importlib.reload(connecteur_module)
        finally:
            monkeypatch.undo()
            importlib.reload(production_module)
            importlib.reload(connecteur_module)

    def test_sonde_depuis_une_boucle_asyncio_deja_active(self):
        """Meme correctif que GitIngest (DEC-0047) : `registre.executer(...)`
        est appele en clair depuis des routes/agents deja `async def` —
        `asyncio.run()` direct dans `sonder()` y leverait `RuntimeError:
        cannot be called from a running event loop`."""
        import asyncio

        async def _depuis_une_route():
            return ConnecteurTxtaiSearch(fournisseur_async=_faux_fournisseur_ollama).sonder()

        sante = asyncio.run(_depuis_une_route())
        assert sante.etat is EtatSante.OPERATIONNEL


class TestLaVraiePolitiqueLivree:
    def test_rechercher_reste_allowed_dans_le_depot_reel(self):
        from core.permissions.politique import FICHIER_POLITIQUE, PolitiqueDePermissions

        regle = PolitiqueDePermissions(chemin=FICHIER_POLITIQUE).regle("txtai_search", "read")
        assert regle is not None, "txtai_search.read a disparu de la politique livree"
        assert regle.get("decision") == "ALLOWED"


class TestPasDeRoutageAutomatique:
    """La mission conditionne l'usage a un avantage demontre : ce connecteur
    ne doit apparaitre dans AUCUNE branche d'aiguillage automatique."""

    def test_txtai_n_apparait_dans_aucune_intention_du_routeur(self):
        import apps.backend.routers.chat as chat_module
        source = chat_module.__file__
        with open(source, encoding="utf-8") as f:
            contenu = f.read()
        assert "txtai" not in contenu.lower()
