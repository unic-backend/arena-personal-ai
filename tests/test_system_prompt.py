"""Instruction système d'Usman : ce qu'elle affirme, et ce qu'elle n'affirme plus.

Elle contenait trois valeurs figées dans le code — l'année, le président et le
premier ministre du Sénégal. Une valeur figée devient fausse sans que rien ne le
signale, et un modèle la répète avec l'assurance d'un fait vérifié.
"""
from datetime import date

import pytest

from apps.backend import main, prompts

# Ce que la version précédente affirmait en dur.
AFFIRMATIONS_RETIREES = [
    "FAITS OFFICIELS",
    "Bassirou Diomaye Faye",
    "Ousmane Sonko",
    "Année actuelle",
    "Annee actuelle",
]


@pytest.fixture
def sans_fait_enregistre(monkeypatch):
    """Mémoire vide, hormis le propriétaire."""
    monkeypatch.setattr(prompts.memory, "get_fact", lambda cle: "Usman" if cle == "owner" else None)


@pytest.fixture
def date_fixee(monkeypatch):
    def _fixer(annee, mois, jour):
        monkeypatch.setattr(prompts, "date_du_jour", lambda: date(annee, mois, jour))
    return _fixer


# --- Ce qui a disparu ----------------------------------------------------------

@pytest.mark.parametrize("affirmation", AFFIRMATIONS_RETIREES)
def test_aucun_fait_date_n_est_ecrit_en_dur(sans_fait_enregistre, affirmation):
    assert affirmation not in prompts.get_arena_system_prompt()


def test_le_code_source_ne_contient_plus_ces_valeurs():
    """Le garde-fou porte aussi sur le fichier : les retirer du prompt ne suffit pas."""
    source = (main.BASE_DIR / "apps" / "backend" / "prompts.py").read_text(encoding="utf-8")
    ligne_de_code = [
        ligne for ligne in source.splitlines()
        if "Bassirou" in ligne or "Ousmane Sonko" in ligne
    ]
    # Seule la docstring qui explique le retrait peut mentionner le sujet.
    assert ligne_de_code == []


# --- Ce qui remplace -----------------------------------------------------------

def test_la_date_est_lue_sur_la_machine_pas_ecrite(sans_fait_enregistre, date_fixee):
    date_fixee(2030, 3, 15)

    prompt = prompts.get_arena_system_prompt()

    assert "15/03/2030" in prompt
    assert "2026" not in prompt


def test_la_date_reelle_apparait_par_defaut(sans_fait_enregistre):
    prompt = prompts.get_arena_system_prompt()

    assert date.today().strftime("%d/%m/%Y") in prompt


def test_le_modele_est_prevenu_que_la_date_ne_suffit_pas(sans_fait_enregistre):
    prompt = prompts.get_arena_system_prompt()

    assert "ne te donne aucune connaissance des evenements recents" in prompt
    assert "ne reponds pas" in prompt
    assert "verifier sur le web" in prompt


def test_le_proprietaire_est_nomme(sans_fait_enregistre):
    assert "Usman" in prompts.get_arena_system_prompt()


class TestLInstructionGeneraleNePorteAucuneEntreprise:
    """Décision du propriétaire, 02/09/2026 — elle **remplace** la sienne du
    même jour, et cette classe remplace le test qui tenait la précédente.

    Il avait d'abord demandé que sa présence en ligne soit connue partout : un
    client peut demander le site sans parler de devis. Il a ensuite tranché
    l'inverse, en des termes plus larges : « ce projet est libre comme bonjour,
    tout le monde peut s'en servir […] rien n'est aligné à UniC Plaquiste, que
    seulement le modèle UniC Plaquiste ».

    Ce n'est donc pas un test affaibli, c'est une décision retournée — et le
    dire ici est ce qui empêche de le relire un jour comme un relâchement.

    Ce qui ne change pas : l'agent métier porte toujours la présence en ligne
    dans SON espace, donc l'information n'est perdue nulle part ; elle n'est
    plus imposée à la vidéo, aux documents et au code.
    """

    ADRESSES = ("unicplaquiste.com", "maps.app.goo.gl",
                "tiktok.com/@unic_plaquiste", "instagram.com/unic_plaquiste")

    def test_aucun_lien_de_l_entreprise_dans_le_prompt_general(self, sans_fait_enregistre):
        prompt = prompts.get_arena_system_prompt()

        presents = [adresse for adresse in self.ADRESSES if adresse in prompt]
        assert presents == [], f"l'instruction generale porte encore : {presents}"

    def test_aucune_entreprise_nommee_dans_le_prompt_general(self, sans_fait_enregistre):
        prompt = prompts.get_arena_system_prompt().lower()

        assert "plaquiste" not in prompt
        assert "presence en ligne" not in prompt

    def test_le_prompt_general_ne_depend_plus_du_module_metier(self):
        """La règle est vérifiable, pas déclarée : si ce module importait
        encore `agents.plaquiste`, un métier pourrait y revenir sans qu'on le
        voie passer."""
        import ast
        import inspect

        arbre = ast.parse(inspect.getsource(prompts))
        importes = {
            noeud.module or ""
            for noeud in ast.walk(arbre) if isinstance(noeud, ast.ImportFrom)
        } | {
            alias.name
            for noeud in ast.walk(arbre) if isinstance(noeud, ast.Import)
            for alias in noeud.names
        }

        metier = [module for module in importes if module.startswith("agents.plaquiste")]
        assert metier == [], f"le prompt general importe encore : {metier}"

    def test_l_espace_metier_lui_connait_toujours_la_presence(self):
        """Ce que la décision ne doit pas abîmer : dans SON espace, l'agent
        UniC Plaquiste connaît toujours le site, l'appli et les réseaux."""
        from agents.plaquiste.plaquiste_agent import (
            FICHIER_METIER,
            charger_metier,
            composer_instruction,
        )

        instruction = composer_instruction(charger_metier(FICHIER_METIER))

        assert "unicplaquiste.com" in instruction
        assert "tiktok.com/@unic_plaquiste" in instruction


def test_le_ton_demande_est_naturel_pas_robotique(sans_fait_enregistre):
    """Demande du 02/09/2026 : le proprietaire trouvait les reponses trop
    hautes en langage, robotiques. Le prompt doit explicitement demander un
    francais simple et decourager le vocabulaire recherche."""
    prompt = prompts.get_arena_system_prompt()

    assert "vraie personne qui" in prompt
    assert "vocabulaire recherche" in prompt


# --- Faits enregistrés par le propriétaire -------------------------------------

def test_un_fait_absent_n_apparait_pas(sans_fait_enregistre):
    prompt = prompts.get_arena_system_prompt()

    assert "President de la Republique" not in prompt
    assert "Faits enregistres" not in prompt


def test_un_fait_enregistre_apparait_avec_sa_reserve(monkeypatch):
    valeurs = {"owner": "Usman", "president": "Une personne nommee par le proprietaire"}
    monkeypatch.setattr(prompts.memory, "get_fact", lambda cle: valeurs.get(cle))

    prompt = prompts.get_arena_system_prompt()

    assert "Une personne nommee par le proprietaire" in prompt
    assert "ils peuvent avoir change depuis" in prompt


def test_seuls_les_faits_reellement_enregistres_sont_listes(monkeypatch):
    valeurs = {"owner": "Usman", "premier_ministre": "Valeur enregistree"}
    monkeypatch.setattr(prompts.memory, "get_fact", lambda cle: valeurs.get(cle))

    prompt = prompts.get_arena_system_prompt()

    assert "Premier ministre" in prompt
    assert "President de la Republique" not in prompt


class TestDeuxNomsDeuxRoles:
    """L'assistant s'appelle Usman ; son propriétaire s'appelle Ousmane.

    Mesuré le 2026-08-26 : à « qui suis-je », Usman a répondu *« Je suis Usman,
    votre IA personnelle »*. Le renommage en masse avait mis « Usman » comme
    nom par défaut du propriétaire **aussi** : le prompt disait « Tu es Usman,
    l'IA personnelle de Usman », et le modèle a répondu la seule chose qu'il
    pouvait comprendre.
    """

    def test_l_assistant_et_le_proprietaire_n_ont_pas_le_meme_nom(self, monkeypatch):
        import apps.backend.prompts as prompts

        monkeypatch.setattr(prompts.memory, "get_fact", lambda cle: None)
        texte = prompts.get_arena_system_prompt()

        assert "Tu es Usman" in texte
        assert "Ousmane" in texte
        assert "l'IA autonome personnelle de Usman" not in texte

    def test_le_prompt_dit_explicitement_de_qui_parle_qui_suis_je(self, monkeypatch):
        import apps.backend.prompts as prompts

        monkeypatch.setattr(prompts.memory, "get_fact", lambda cle: "Ousmane")
        texte = prompts.get_arena_system_prompt()

        assert "qui suis-je" in texte
        assert "il parle de Ousmane, pas de toi" in texte

    def test_le_nom_enregistre_en_memoire_l_emporte(self, monkeypatch):
        import apps.backend.prompts as prompts

        monkeypatch.setattr(prompts.memory, "get_fact",
                            lambda cle: "Fatou" if cle == "owner" else None)
        assert "Fatou" in prompts.get_arena_system_prompt()
