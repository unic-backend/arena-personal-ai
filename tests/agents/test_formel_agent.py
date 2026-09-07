"""L'agent de preuve : le modèle propose, Lean tranche, et jamais l'inverse.

Le test qui porte la mission est
`TestUnModeleNePeutPasSAutoDeclarerVerifie` : quoi que le modèle écrive —
« preuve vérifiée », « CQFD », ou une démonstration trouée qui compile —
le verdict d'ARENA vient du connecteur, donc du binaire.

Le modèle est scripté ici (Ollama est absent du CI). **Lean, lui, ne l'est
pas** dans les tests marqués par `_SANS_LEAN` : ils exécutent le vrai
binaire, ou sont sautés.
"""
import pytest

from agents.formel.formel_agent import FormelAgent, source_lean
from core.actions.resultat import echec, non_configure, succes
from core.connectors.lean_formel import chemin_de_lean

_SANS_LEAN = pytest.mark.skipif(
    chemin_de_lean() is None,
    reason="Lean absent : aucune vérification réelle ne peut être mesurée ici")


class RegistreDouble:
    """Note les appels et rend un résultat scripté — jamais un verdict inventé."""

    def __init__(self, *resultats):
        self.resultats, self.appels = list(resultats), []

    def executer(self, connecteur, capacite, **parametres):
        self.appels.append((connecteur, capacite, parametres))
        if self.resultats:
            return self.resultats.pop(0)
        return succes(action=capacite, cible=connecteur, message="ok", preuve="p",
                      verdict="VERIFIE", axiomes=[], troue=False)


class RegistreReel:
    """Le VRAI connecteur, sans la couche de permissions.

    Le coupe-circuit `EXECUTE_COMMANDS` est mesuré par
    `tests/core/test_connecteur_lean_formel.py` ; ici on veut voir Lean
    trancher, pas re-tester la permission.
    """

    def __init__(self, dossier):
        from core.connectors.lean_formel import ConnecteurLeanFormel
        self.connecteur = ConnecteurLeanFormel(dossier=dossier)
        self.appels = []

    def executer(self, connecteur, capacite, **parametres):
        self.appels.append((connecteur, capacite, parametres))
        return self.connecteur._verifier(**parametres)


class ModeleScripte:
    def __init__(self, *reponses):
        self.reponses, self.appels = list(reponses), []

    async def is_available(self) -> bool:
        return True

    async def generate(self, prompt: str, **_) -> str:
        self.appels.append(prompt)
        assert self.reponses, "le modele a ete appele plus que prevu"
        return self.reponses.pop(0)


class TestLeLeanFourniParLaDemande:
    """Une preuve donnée se vérifie telle quelle — sans déranger un modèle."""

    @pytest.mark.parametrize("phrase,attendu", [
        ("```lean\ntheorem t : 1 = 1 := by rfl\n```", "theorem t : 1 = 1 := by rfl"),
        ("```\ntheorem t : 1 = 1 := by rfl\n```", "theorem t : 1 = 1 := by rfl"),
        ("theorem brut : 1 = 1 := by rfl", "theorem brut : 1 = 1 := by rfl"),
    ])
    def test_la_source_est_extraite(self, phrase, attendu):
        assert source_lean(phrase) == attendu

    @pytest.mark.parametrize("phrase", [
        "prouve formellement que 2+2=4",
        "```lean\n-- juste un commentaire\n```",
        "",
    ])
    def test_une_phrase_sans_preuve_ne_rend_aucune_source(self, phrase):
        assert source_lean(phrase) is None

    @pytest.mark.asyncio
    async def test_aucun_modele_n_est_appele_quand_le_lean_est_donne(self):
        modele = ModeleScripte()  # aucune reponse : tout appel leverait
        agent = FormelAgent(provider=modele, registre=RegistreDouble())

        await agent.run("vérifie ```lean\ntheorem t : 1 = 1 := by rfl\n```")

        assert modele.appels == [], "un modele a ete derange pour une preuve deja ecrite"


class TestCeQuIlRefuseDeSimuler:
    @pytest.mark.asyncio
    async def test_sans_registre_il_le_dit(self):
        agent = FormelAgent(provider=ModeleScripte(), registre=None)
        r = await agent.run("theorem t : 1 = 1 := by rfl")
        assert r["status"] == "error"

    @pytest.mark.asyncio
    async def test_lean_absent_est_un_avertissement_jamais_une_preuve(self):
        agent = FormelAgent(provider=ModeleScripte(), registre=RegistreDouble(
            non_configure(action="verifier", cible="formel",
                          ce_qui_manque="Lean n'est pas installe")))

        r = await agent.run("theorem t : 1 = 1 := by rfl")

        assert r["status"] == "warning", "une capacite absente s'est dite en panne"
        assert r["status"] != "success"

    @pytest.mark.asyncio
    async def test_un_modele_muet_ne_produit_aucun_verdict(self):
        agent = FormelAgent(provider=ModeleScripte("je ne sais pas faire"),
                            registre=RegistreDouble())

        r = await agent.run("prouve formellement que 2+2=4")

        assert r["status"] == "error"
        assert agent.registre.appels == [], "le connecteur a ete appele sans preuve"


class TestLaBoucleDeReparationEstBornee:
    @pytest.mark.asyncio
    async def test_un_rejet_declenche_une_correction_avec_le_diagnostic_reel(self):
        modele = ModeleScripte(
            "```lean\ntheorem t : 2 + 2 = 5 := by rfl\n```",
            "```lean\ntheorem t : 2 + 2 = 4 := by rfl\n```")
        registre = RegistreDouble(
            echec(action="verifier", cible="formel", message="rejete",
                  verdict="REJETE", diagnostics="error: not definitionally equal"),
            succes(action="verifier", cible="formel", message="verifie", preuve="p",
                   verdict="VERIFIE", axiomes=[], troue=False))
        agent = FormelAgent(provider=modele, registre=registre)

        r = await agent.run("prouve formellement que 2+2=4")

        assert r["status"] == "success"
        assert r["tentatives"] == 2
        assert "not definitionally equal" in modele.appels[1], (
            "la correction a ete demandee sans le diagnostic reel de Lean")

    @pytest.mark.asyncio
    async def test_deux_rejets_arretent_la_boucle(self):
        """Sans borne, un modèle qui ne trouve pas coûterait des tours sans fin."""
        rejet = echec(action="verifier", cible="formel", message="rejete",
                      verdict="REJETE", diagnostics="error")
        modele = ModeleScripte(
            "```lean\ntheorem t : 2 + 2 = 5 := by rfl\n```",
            "```lean\ntheorem t : 2 + 2 = 6 := by rfl\n```")
        agent = FormelAgent(provider=modele,
                            registre=RegistreDouble(rejet, rejet))

        r = await agent.run("prouve formellement que 2+2=4")

        assert r["status"] == "error"
        assert r["tentatives"] == 2
        assert len(modele.appels) == 2, "la boucle a depasse sa borne"


@_SANS_LEAN
class TestUnModeleNePeutPasSAutoDeclarerVerifie:
    """**Le test qui porte la mission.** Lean tourne vraiment ici.

    Un modèle peut écrire n'importe quoi — y compris une preuve trouée, qui
    compile avec le code de sortie 0. Le verdict d'ARENA doit venir du
    binaire, jamais de la phrase du modèle.
    """

    @pytest.mark.asyncio
    async def test_une_preuve_trouee_ne_passe_pas_pour_verifiee(self, tmp_path):
        troue = "```lean\ntheorem t (n : Nat) : n + 0 = n := by sorry\n```"
        agent = FormelAgent(provider=ModeleScripte(troue, troue),
                            registre=RegistreReel(tmp_path))

        r = await agent.run("prouve formellement que n+0=n")

        assert r["status"] == "error", "une preuve trouee s'est dite verifiee"
        assert r["verdict"] == "REJETE"
        assert r["troue"] is True

    @pytest.mark.asyncio
    async def test_le_modele_a_beau_affirmer_lean_tranche(self, tmp_path):
        """Le modèle annonce « preuve vérifiée » sur un théorème FAUX."""
        agent = FormelAgent(
            provider=ModeleScripte(
                "Preuve vérifiée et rigoureuse, CQFD :\n"
                "```lean\ntheorem t : 2 + 2 = 5 := by rfl\n```",
                "```lean\ntheorem t : 2 + 2 = 5 := by rfl\n```"),
            registre=RegistreReel(tmp_path))

        r = await agent.run("prouve formellement que 2+2=5")

        assert r["status"] == "error"
        assert r["verdict"] == "REJETE"

    @pytest.mark.asyncio
    async def test_une_vraie_preuve_est_bien_acceptee(self, tmp_path):
        """Le miroir du test précédent : le module n'est pas juste sévère."""
        agent = FormelAgent(provider=ModeleScripte(), registre=RegistreReel(tmp_path))

        r = await agent.run("```lean\ntheorem vrai : 2 + 2 = 4 := by rfl\n```")

        assert r["status"] == "success", r["response"]
        assert r["verdict"] == "VERIFIE"
        assert r["axiomes_ajoutes"] == []
