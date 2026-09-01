"""WanGP refusant un appel n'est pas WanGP répondant.

MCP distingue deux échecs, et `ok` n'en couvre qu'un : `ok=False` dit que le
transport n'a pas abouti, `ok=True, isError=True` dit que l'outil a refusé —
**et pourquoi**.

Mesuré le 01/09/2026 avec un double : WanGP répondant « VRAM insuffisante :
modèle non chargé » faisait rendre `SUCCESS` à ce connecteur, avec le message
« WanGP a répondu pour modeles. ». Le message réel était jeté.

```
avant : modeles -> SUCCESS | WanGP a repondu pour modeles.
après : modeles -> FAILED  | WanGP a refuse : VRAM insuffisante : modele non charge
```

Le connecteur voisin (`opentakeoff`) posait déjà cette question depuis une
mesure sur le serveur réel. Celui-ci ne la posait pas — la même règle apprise
sur une frontière et jamais portée sur l'autre, quatrième fois de la nuit.
"""
import pytest

from core.connectors.wan2gp import OUTIL_GENERER, Wan2GPConnector
from core.mcp.transport import Reponse

MESSAGE = "VRAM insuffisante : modele non charge"


class ClientDouble:
    """Un serveur WanGP scripté. Rien ne part sur le réseau."""

    url = "http://faux"

    def __init__(self, resultat):
        self._resultat = resultat
        self.appels = []

    def outils(self):
        return Reponse(ok=True, resultat={
            "tools": [{"name": OUTIL_GENERER}, {"name": "get_job_status"}]})

    def appeler(self, outil, arguments=None):
        self.appels.append((outil, arguments))
        return Reponse(ok=True, resultat=self._resultat)


def connecteur(resultat):
    return Wan2GPConnector(client=ClientDouble(resultat))


ERREUR = {"isError": True, "content": [{"type": "text", "text": MESSAGE}]}


class TestUnRefusApplicatifNEstPasUnSucces:

    @pytest.mark.parametrize("capacite,parametres", [
        ("modeles", {}),
        ("galerie", {}),
        ("etat_travail", {"job_id": "x"}),
    ])
    def test_le_refus_devient_un_echec(self, capacite, parametres):
        resultat = connecteur(ERREUR).executer(capacite, **parametres)

        assert resultat.statut.value == "FAILED"

    def test_la_raison_reelle_de_wangp_est_transmise(self):
        """Sans elle, le propriétaire lit « a répondu » et ne sait pas quoi faire."""
        resultat = connecteur(ERREUR).executer("modeles")

        assert MESSAGE in resultat.message

    def test_un_iserror_sans_texte_ne_rend_pas_un_message_vide(self):
        resultat = connecteur({"isError": True, "content": []}).executer("modeles")

        assert resultat.statut.value == "FAILED"
        assert resultat.message.strip()

    def test_une_vraie_reponse_reste_un_succes(self):
        """`FAILED` ne doit pas devenir le statut par défaut de WanGP."""
        resultat = connecteur(
            {"structuredContent": {"models": ["wan-1"]}}).executer("modeles")

        assert resultat.statut.value == "SUCCESS"
        assert resultat.detail["donnees"] == {"models": ["wan-1"]}


class TestLaRegleVitSurLaReponse:
    """Écrite une fois : deux connecteurs posent la même question."""

    def test_sans_iserror_il_n_y_a_pas_d_erreur_applicative(self):
        assert Reponse(ok=True, resultat={"content": []}).erreur_applicative is None

    def test_avec_iserror_le_texte_est_rendu(self):
        assert Reponse(ok=True, resultat=ERREUR).erreur_applicative == MESSAGE

    def test_opentakeoff_lit_la_meme_regle(self):
        from core.connectors.opentakeoff import _erreur_outil

        assert _erreur_outil(Reponse(ok=True, resultat=ERREUR)) == MESSAGE
        assert _erreur_outil(Reponse(ok=True, resultat={})) is None
