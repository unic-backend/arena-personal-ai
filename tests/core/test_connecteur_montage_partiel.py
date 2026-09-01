"""Un plan à moitié tombé n'est pas un succès.

Mesuré le 01/09/2026, sur une vraie vidéo et une vraie exécution :

```
STATUT  -> SUCCESS
MESSAGE -> « Sonde » : 1 piste(s), 0 ms, 640x360.
ERREURS -> ['#4 ajouter_clip : aucun media « 1 » importe dans ce projet']
```

La timeline faisait **zéro milliseconde**, l'unique clip avait été refusé, et
le statut disait « réussi ». L'erreur existait — dans `detail.erreurs`, un
champ que le message lu ne reprenait pas.

C'est exactement ce que `Statut.PARTIEL` existe pour dire, et il n'était pas
utilisé ici.
"""
from core.connectors.montage import ConnecteurMontage

PLAN_SAIN = [
    {"operation": "creer_projet", "nom": "Essai", "largeur": 640, "hauteur": 360},
    {"operation": "ajouter_piste", "nom": "principale", "type": "video"},
]


def composer(operations):
    return ConnecteurMontage().executer("composer", operations=operations)


class TestUnPlanAMoitieTombe:

    def test_un_plan_entierement_valide_reste_un_succes(self):
        resultat = composer(PLAN_SAIN)

        assert resultat.statut.value == "SUCCESS"
        assert resultat.detail["erreurs"] == []

    def test_une_operation_tombee_rend_partiel(self):
        resultat = composer(PLAN_SAIN + [
            {"operation": "ajouter_clip", "piste_id": 1, "media_id": 1,
             "debut_ms": 0, "duree_ms": 2000}])

        assert resultat.statut.value == "PARTIAL"

    def test_le_compte_entre_dans_le_message_pas_seulement_dans_le_detail(self):
        """C'est le message qui est lu ; un champ que personne n'affiche ne dit rien."""
        resultat = composer(PLAN_SAIN + [
            {"operation": "ajouter_clip", "piste_id": 1, "media_id": 1,
             "debut_ms": 0, "duree_ms": 2000}])

        assert "1 ligne(s) ecartee(s)" in resultat.message

    def test_les_lignes_ecartees_restent_nommees(self):
        resultat = composer(PLAN_SAIN + [
            {"operation": "ajouter_clip", "piste_id": 1, "media_id": 1,
             "debut_ms": 0, "duree_ms": 2000}])

        assert any("ajouter_clip" in e for e in resultat.detail["erreurs"])

    def test_un_projet_jamais_cree_reste_un_echec(self):
        """`PARTIAL` dit « une partie a eu lieu » — sans projet, rien n'a eu lieu."""
        resultat = composer([{"operation": "ajouter_piste", "nom": "x", "type": "video"}])

        assert resultat.statut.value == "FAILED"
