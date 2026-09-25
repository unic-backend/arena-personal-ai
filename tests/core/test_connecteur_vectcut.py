from core.actions.resultat import Statut
from core.connectors.vectcut import ConnecteurVectCut, OUTILS
from core.mcp.transport import Reponse


class FauxVectCut:
    def __init__(self, outils=None, reponse=None):
        self._outils = outils or sorted(OUTILS)
        self._reponse = reponse or Reponse(ok=True, resultat={"content": [{"type": "text", "text": "ok"}]})
        self.appels = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def outils(self):
        return Reponse(ok=True, resultat={"tools": [{"name": n} for n in self._outils]})

    def appeler(self, nom, arguments=None):
        self.appels.append((nom, arguments or {}))
        return self._reponse


def test_sonde_verifie_les_onze_outils():
    connecteur = ConnecteurVectCut(client=FauxVectCut())
    assert connecteur.sonder().etat.value == "OPERATIONAL"


def test_duree_est_lecture_et_modifications_sont_ecritures():
    capacites = ConnecteurVectCut(client=FauxVectCut()).capacites()
    assert capacites["get_video_duration"].ecriture is False
    assert capacites["create_draft"].ecriture is True
    assert capacites["add_video"].ecriture is True
    assert capacites["save_draft"].ecriture is True


def test_appel_mcp_reellement_atteint_le_client():
    client = FauxVectCut()
    connecteur = ConnecteurVectCut(client=client)
    resultat = connecteur._executer(
        connecteur.capacites()["get_video_duration"],
        video_url="https://example.test/video.mp4",
    )
    assert resultat.statut is Statut.SUCCES
    assert client.appels == [
        ("get_video_duration", {"video_url": "https://example.test/video.mp4"})
    ]
