"""Une règle durcie dans le fichier doit s'appliquer sans redémarrer.

Défaut mesuré le 01/09/2026, sur les **deux** couches de permissions. Les deux
objets sont des singletons créés à l'import de `apps/backend/runtime.py`, donc
au démarrage du serveur, et lisaient leur fichier une seule fois :

```
1 AU DEMARRAGE  -> email/read = {'decision': 'ALLOWED', 'risque': 'LOW'}
2 FICHIER DURCI -> {'decision': 'NEEDS_CONFIRMATION', 'risque': 'HIGH'}
3 APPLIQUE      -> {'decision': 'ALLOWED', 'risque': 'LOW'}
```

Le sens du risque compte. Une règle **assouplie** qui n'est pas vue ne fait
rien de dangereux. Une règle **durcie** qui n'est pas vue laisse passer ce que
le propriétaire venait d'interdire.

Et la docstring de `PolitiqueDePermissions` annonçait exactement la capacité
qui manquait : « `recharger()` existe pour que le propriétaire puisse modifier
ses règles sans redémarrer le serveur » — `recharger()` existait, était testée,
et personne ne l'appelait.
"""
import yaml

from core.permissions.permission_manager import PermissionManager
from core.permissions.politique import Decision, PolitiqueDePermissions


def ecrire(chemin, donnees):
    chemin.write_text(yaml.safe_dump(donnees, allow_unicode=True), encoding="utf-8")


class TestLaPolitiqueSuitSonFichier:

    def test_une_regle_durcie_est_appliquee(self, tmp_path):
        fichier = tmp_path / "permissions_services.yaml"
        ecrire(fichier, {"services": {"email": {"read": {
            "decision": "ALLOWED", "risque": "LOW"}}}})
        politique = PolitiqueDePermissions(fichier)
        assert politique.decider("email", "read").decision is Decision.AUTORISE

        ecrire(fichier, {"services": {"email": {"read": {
            "decision": "DENIED", "risque": "HIGH"}}}})

        assert politique.decider("email", "read").decision is Decision.REFUSE

    def test_une_regle_de_compte_durcie_est_appliquee(self, tmp_path):
        fichier = tmp_path / "permissions_services.yaml"
        ecrire(fichier, {
            "services": {"email": {"send": {"decision": "ALLOWED", "risque": "LOW"}}},
            "comptes": {"moi@exemple.sn": {"email": {"send": "ALLOWED"}}}})
        politique = PolitiqueDePermissions(fichier)
        assert politique.decider(
            "email", "send", "moi@exemple.sn").decision is Decision.AUTORISE

        ecrire(fichier, {
            "services": {"email": {"send": {"decision": "ALLOWED", "risque": "LOW"}}},
            "comptes": {"moi@exemple.sn": {"email": {"send": "DENIED"}}}})

        assert politique.decider(
            "email", "send", "moi@exemple.sn").decision is Decision.REFUSE

    def test_un_fichier_efface_refuse_tout(self, tmp_path):
        """Refuser est bruyant et se remarque ; autoriser par défaut ne se remarque pas."""
        fichier = tmp_path / "permissions_services.yaml"
        ecrire(fichier, {"services": {"email": {"read": {
            "decision": "ALLOWED", "risque": "LOW"}}}})
        politique = PolitiqueDePermissions(fichier)
        assert politique.decider("email", "read").decision is Decision.AUTORISE

        fichier.unlink()

        assert politique.decider("email", "read").decision is Decision.REFUSE

    def test_un_fichier_inchange_n_est_pas_relu(self, tmp_path, monkeypatch):
        fichier = tmp_path / "permissions_services.yaml"
        ecrire(fichier, {"services": {"email": {"read": {
            "decision": "ALLOWED", "risque": "LOW"}}}})
        politique = PolitiqueDePermissions(fichier)

        relectures = []
        monkeypatch.setattr(politique, "recharger",
                            lambda: relectures.append(1))

        for _ in range(5):
            politique.decider("email", "read")

        assert relectures == []


class TestLesNeufBooleensSuiventAussi:

    def test_un_booleen_durci_est_applique(self, tmp_path):
        fichier = tmp_path / "permissions.yaml"
        ecrire(fichier, {"SEARCH_WEB": True})
        gestionnaire = PermissionManager(str(fichier))
        assert gestionnaire.is_allowed("SEARCH_WEB") is True

        ecrire(fichier, {"SEARCH_WEB": False})

        assert gestionnaire.is_allowed("SEARCH_WEB") is False

    def test_une_cle_retiree_revient_a_son_defaut(self, tmp_path):
        """Sans remise à zéro, elle garderait sa valeur — or trois défauts sont `False`."""
        fichier = tmp_path / "permissions.yaml"
        ecrire(fichier, {"PUBLISH": True})
        gestionnaire = PermissionManager(str(fichier))
        assert gestionnaire.is_allowed("PUBLISH") is True

        ecrire(fichier, {"SEARCH_WEB": True})

        assert gestionnaire.is_allowed("PUBLISH") is False, (
            "PUBLISH doit revenir a son defaut, qui est False"
        )
