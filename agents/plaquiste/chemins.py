"""Où vivent la configuration du métier et ses documents.

**Aucun chemin ne nomme plus une entreprise.** Décision du propriétaire,
02/09/2026 : « ce projet est libre comme bonjour, tout le monde peut s'en
servir ». Un fichier appelé `unic_plaquiste.yaml` disait le contraire à
quiconque clonait le dépôt, même quand le code, lui, était général.

Les noms sont donc `config/metier.yaml`, `config/marque/logo.png`,
`documents/metier/`. Un plombier, un menuisier ou un imprimeur y met le sien.

**Pourquoi une résolution, et pas trois constantes.** `documents/` est exclu
de git (`.gitignore` : « Documents clients […] noms, montants, chantiers »).
Renommer le dossier ici ne renomme donc **rien** sur la machine du
propriétaire : ses archives et sa signature manuscrite sont restées dans
`documents/unic_plaquiste/`, et une constante qui pointerait sur le nouveau nom
les rendrait invisibles du jour au lendemain — sans erreur, sans message.

La règle tient en une phrase : **l'ancien dossier est lu tant qu'il porte des
documents que le nouveau n'a pas.** Le jour où le propriétaire déplace ses
fichiers, ou dès qu'il en dépose un dans le nouveau, la bascule se fait seule.

Rien n'est deviné : chaque fonction regarde le disque et rend ce qu'elle y
trouve.
"""
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]

#: Le mode d'emploi du dossier n'est pas un document du propriétaire : sa
#: présence seule ne fait pas d'un dossier un dossier qui sert.
FICHIERS_NON_COMPTES = {"lisez_moi.md", "readme.md", ".gitkeep"}

FICHIER_METIER = RACINE / "config" / "metier.yaml"
FICHIER_METIER_ANCIEN = RACINE / "config" / "unic_plaquiste.yaml"

DOSSIER_DOCUMENTS = RACINE / "documents" / "metier"
DOSSIER_DOCUMENTS_ANCIEN = RACINE / "documents" / "unic_plaquiste"

LOGO = RACINE / "config" / "marque" / "logo.png"
LOGO_ANCIEN = RACINE / "config" / "marque" / "logo_unic_plaquiste.png"

NOM_SIGNATURE = "signature.png"
NOM_SIGNATURE_ANCIEN = "signature_uthman.png"


def _porte_des_documents(dossier: Path) -> bool:
    """Le dossier contient-il autre chose que son mode d'emploi ?"""
    if not dossier.is_dir():
        return False
    return any(f.is_file() and f.name.lower() not in FICHIERS_NON_COMPTES
               for f in dossier.iterdir())


def fichier_metier() -> Path:
    """Le fichier de configuration du métier.

    Celui-ci est suivi par git : le renommage l'a déplacé pour tout le monde.
    L'ancien nom reste lu au cas où quelqu'un aurait gardé le sien à côté —
    un fichier de prix perdu, c'est un devis qui ne se chiffre plus.
    """
    if not FICHIER_METIER.is_file() and FICHIER_METIER_ANCIEN.is_file():
        return FICHIER_METIER_ANCIEN
    return FICHIER_METIER


def dossier_des_documents() -> Path:
    """Le dossier des archives et de la signature.

    L'ancien nom l'emporte tant qu'il porte des documents que le nouveau n'a
    pas : ce dossier est hors de git, et le renommer ici ne déplace rien sur
    la machine de qui que ce soit.
    """
    if _porte_des_documents(DOSSIER_DOCUMENTS_ANCIEN) \
            and not _porte_des_documents(DOSSIER_DOCUMENTS):
        return DOSSIER_DOCUMENTS_ANCIEN
    return DOSSIER_DOCUMENTS


def logo() -> Path:
    """Le logo de la marque, suivi par git."""
    if not LOGO.is_file() and LOGO_ANCIEN.is_file():
        return LOGO_ANCIEN
    return LOGO


def signature() -> Path:
    """La signature manuscrite. **Elle reste hors de git et doit le rester :**
    versionnée, n'importe qui disposant du dépôt pourrait l'apposer sur
    n'importe quel document."""
    dossier = dossier_des_documents()
    nouvelle = dossier / NOM_SIGNATURE
    ancienne = dossier / NOM_SIGNATURE_ANCIEN
    if not nouvelle.is_file() and ancienne.is_file():
        return ancienne
    return nouvelle
