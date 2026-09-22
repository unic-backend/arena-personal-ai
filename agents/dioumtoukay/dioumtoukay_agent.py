"""Dioumtoukay : celui qui entre vraiment dans les fichiers et le terminal.

Nommé par le propriétaire le 02/09/2026 : « il doit être comme claude code
entrer dans mon terminal mon github et travailler sur le projet ». **DEC-0038**
enregistre qu'il a levé DEC-0014 en connaissance de cause — donc ici on
n'analyse pas, on **fait**.

C'est ce qui le sépare de `RepoEngineerAgent`, qui lit et propose sans jamais
modifier un fichier. Les deux existent, et le second n'est pas remplacé : lire
avant d'agir reste utile.

**La boucle.** Le modèle ne rend pas une réponse, il rend **une action à la
fois**. L'action est exécutée par `tools/atelier`, et son résultat réel —
sortie, erreur, code de sortie — revient dans l'invite suivante. Il travaille
donc sur ce qui s'est vraiment passé, jamais sur ce qu'il imaginait.

**Quatre choses que cet agent ne fait pas, et qui ne sont pas des garde-fous :**

1. **Il n'invente aucun résultat.** Une commande qui n'a pas tourné rend son
   erreur. Sans modèle joignable, il répond `NOT_CONFIGURED` avec ce qui manque
   — jamais un compte-rendu de travail qui n'a pas eu lieu.
2. **Il ne déclare pas la réussite à la place des commandes.** Ce qui est
   rapporté au propriétaire est la liste de ce qui a tourné, avec les codes de
   sortie tels quels. Un `pytest` rouge se lit rouge.
3. **Il s'arrête.** `TOURS_MAX` borne la boucle : un modèle qui tourne en rond
   consomme la machine sans rien produire, et une boucle sans fin est la
   première façon dont un agent autonome devient nuisible.
4. **Il laisse une trace.** Chaque action passe par `JournalDesActions` via
   l'atelier. Ce n'est pas une autorisation à demander, c'est un compte-rendu à
   lire.
"""
from __future__ import annotations

import logging
import re
import shlex
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional

from core.actions.resultat import Statut
from core.agent.base_agent import BaseAgent
from core.context.instantane_projet import instantane
from core.execution.reprise import JournalDeReprise
from core.memory.conversation import retenir_l_echange
from core.memory.memory_manager import MemoryManager
from core.memory.personnelle import MemoirePersonnelle
from core.models.base import ModelProvider
from core.skills.instantane import instantane_competences
from core.specialistes.selection import bloc_de_methode, choisir
from tools.atelier.atelier import Atelier, Resultat

logger = logging.getLogger("usman.agent.dioumtoukay")

#: Budget court pour le poste local : douze actions suffisent à la grande
#: majorité des tâches et gardent une borne ferme face à un modèle qui erre.
TOURS_MAX = 12

#: Sur Railway, un vrai cycle d'ingénierie distante coûte davantage d'étapes :
#: explorer -> lire -> créer une branche -> corriger plusieurs fichiers ->
#: comparer -> ouvrir une PR -> suivre la CI -> lire une revue -> recorriger.
#: Le plafond de 12 coupait donc précisément les tâches complexes que les
#: capacités GitHub ajoutées ensuite rendaient enfin possibles. On autorise
#: plus de profondeur UNIQUEMENT dans ce mode, tout en conservant les gardes
#: anti-boucle, anti-échecs et le plafond temporel ci-dessous.
TOURS_MAX_GITHUB_DISTANT = 24

#: Au-delà, le travail s'arrête même si le budget de tours n'est pas atteint.
#: Une action peut coûter jusqu'à `DELAI_PAR_DEFAUT` (`Atelier`, 120s) :
#: sans plafond de temps, une session profonde pourrait durer indéfiniment. Concept vérifié dans le code
#: source de mini-SWE-agent (`AgentConfig.wall_time_limit_seconds`) — 0
#: désactiverait la limite, comme chez eux, mais rien ici n'a demandé à la
#: désactiver.
DUREE_MAX_SECONDES = 20 * 60

#: Au-delà, une réponse illisible D'AFFILÉE n'est plus une réponse à renvoyer
#: une fois de plus : c'est un moteur qui ne sait pas produire le format
#: demandé, et continuer jusqu'à `TOURS_MAX` ne ferait que consommer le budget
#: sans qu'aucune action ne parte jamais. Concept vérifié dans le code source
#: de mini-SWE-agent (`AgentConfig.max_consecutive_format_errors`, défaut 3,
#: `DefaultAgent.run` : le compteur revient à zéro dès qu'un tour est propre).
ILLISIBLES_CONSECUTIVES_MAX = 3

#: Au-delà, la MÊME action valide, avec les MÊMES champs, demandée d'affilée
#: n'est plus une action à rejouer : c'est un modèle bloqué qui répète un geste
#: sans effet nouveau. EXCEPTION : les actions de suivi d'un état externe
#: peuvent légitimement être identiques pendant que leur RESULTAT évolue.
#: Celles-ci sont arrêtées seulement si la même action rend aussi la même
#: observation plusieurs fois de suite.
#: Concept vérifié dans le code source de Cline (Apache-2.0, `cline/cline`,
#: commit `fee4fb9`, `sdk/packages/core/src/runtime/safety/loop-detection.ts`) :
#: rien copié, réimplémenté sur la boucle existante.
ACTIONS_IDENTIQUES_CONSECUTIVES_MAX = 3

#: Polling légitime : l'appel est identique, mais le monde observé peut changer
#: entre deux tours. Ne jamais assimiler "queued -> in_progress -> success" à
#: une boucle. Si l'observation elle-même ne change plus, la même borne protège
#: toujours contre le polling infini.
ACTIONS_DE_SUIVI_EVOLUTIF = frozenset({"etat_ci", "ordinateur_etat"})

#: Au-delà, un ÉCHEC D'EXÉCUTION (commande en erreur, remplacement introuvable,
#: fichier absent...) répété d'affilée n'est plus une erreur à corriger au tour
#: suivant : c'est une approche qui ne marche pas et que rejouer ne réparera
#: pas seul. Distinct des deux gardes ci-dessus : l'action change à chaque
#: tour, mais échoue à chaque fois. Concept vérifié dans le code source de
#: Cline (Apache-2.0, `cline/cline`, commit `fee4fb9`,
#: `sdk/packages/core/src/runtime/safety/mistake-tracker.ts` —
#: `MistakeTracker.record`, raison `tool_execution_failed`) : rien copié,
#: réimplémenté ici en Python sur la structure déjà en place.
ECHECS_CONSECUTIFS_MAX = 3

#: Les actions qu'il sait faire. Toute autre étiquette est refusée et lui est
#: renvoyée telle quelle — corriger sa faute à sa place lui apprendrait à
#: écrire n'importe quoi.
#:
#: `analyser` et `diagnostiquer` datent de DEC-0073 : avant, `RepoEngineerAgent`
#: et `SWEAgent` étaient deux portes séparées que le propriétaire devait choisir
#: à la place de Dioumtoukay — leur analyse ne lui servait jamais. Elles
#: deviennent ici des outils qu'il consulte lui-même, en cours de tâche.
#: `ouvrir_pr` et `etat_ci` : le connecteur GitHub (core/connectors/github.py,
#: DEC-0073), le premier acces de Dioumtoukay a l'API GitHub — jusqu'ici,
#: seul `git` en shell nu, sans PR ni CI. `ouvrir_pr` passe par la meme
#: confirmation que toute autre ecriture externe (config/permissions_
#: services.yaml) : Dioumtoukay ne peut pas la contourner en l'appelant.
#: `convertir` : le connecteur `file_conversion` (DEC-0074, mission
#: « File_Converter_Pro »). Chemin d'entree GENERIQUE de cette capacite —
#: n'importe quel modele qui pilote Dioumtoukay peut demander une conversion
#: sans savoir que LibreOffice/Pillow/ffmpeg existent derriere.
#: `organiser_*` : le connecteur `file_organization` (DEC-0075, mission
#: « AI File Sorter »). Quatre actions, jamais une mutation directe : un
#: plan se propose (`organiser_planifier`), puis s'applique seulement sur
#: son identifiant deja valide (`organiser_appliquer`) — jamais une liste
#: d'operations fournie une deuxieme fois, non revue.
#: `isoler`/`nettoyer_worktree` : mission ARENA x TRANS4MERS (11/09/2026,
#: DEC-0091), `Atelier.isoler`/`nettoyer_worktree`. Une CAPACITE de plus,
#: jamais un chemin oblige — DEC-0038 reste entier, Dioumtoukay peut toujours
#: travailler directement sur l'arbre principal s'il le choisit.
#: `ordinateur_*` : mission ARENA x CASE (11/09/2026, DEC-0092), le connecteur
#: `case` (`core/connectors/case_computer.py`). Un ordinateur Linux ISOLE et
#: PERSISTANT, distinct de la machine du proprietaire — utile pour un test
#: qui doit tourner sous Linux, un paquet a ne pas installer sur la vraie
#: machine, un navigateur qui garde son identite entre deux sessions.
#: `ordinateur_detruire` passe par la meme confirmation que `ouvrir_pr` :
#: irreversible, jamais lance sans accord.
#: `git_statut`/`git_diff`/`git_checkpoint`/`git_restaurer` : mission ARENA x
#: GITGUI (11/09/2026, DEC-0093), `Atelier.git_statut` et consorts. Une
#: LECTURE structuree de plus (jamais une garde neuve sur `git`/`executer` —
#: DEC-0038 reste entier) et une paire checkpoint/restauration pour annuler
#: SES PROPRES modifications sans jamais toucher un fichier deja en
#: desordre avant elle.
#: `git_stager` a `git_abandonner` : mission ARENA x GITGUI, second passage
#: (11/09/2026, DEC-0094), `tools/atelier/git_ops.py`. Des OPERATIONS git
#: mutantes structurees — jamais une garde neuve sur `git()`/`executer()`
#: (DEC-0038 reste entier, `git()` reste le chemin sans aucune limite) : ce
#: sont des CAPACITES de plus, surs a rejouer (IDENTIFIANT_OPERATION —
#: repasser le meme ne rejoue jamais deux fois la meme mutation), qui
#: refusent de muter un depot qui a change de facon inattendue
#: (TETE_ATTENDUE) et qui verifient ce qu'elles ont reellement fait plutot
#: que de le supposer. `git_pousser` ne pousse JAMAIS en `--force` nu — seul
#: `FORCE_AVEC_BAIL` (`--force-with-lease`) existe, et un rejet
#: non-fast-forward n'est jamais retente avec la force automatiquement.
ACTIONS = ("lire", "chercher", "lister", "ecrire", "remplacer", "deplacer",
           "executer", "analyser", "diagnostiquer",
           "github_lister", "github_lire", "github_chercher", "github_diff",
           "github_branche_creer", "github_ecrire", "github_remplacer",
           "ouvrir_pr", "etat_ci", "commentaires_pr",
           "convertir", "organiser_inspecter", "organiser_planifier",
           "organiser_appliquer", "organiser_annuler",
           "pdf_fusionner", "pdf_demonter", "pdf_pages", "pdf_extraire_texte",
           "isoler", "nettoyer_worktree",
           "ordinateur_lister", "ordinateur_creer", "ordinateur_etat",
           "ordinateur_dormir", "ordinateur_reveiller", "ordinateur_executer",
           "ordinateur_lire_fichier", "ordinateur_ecrire_fichier",
           "ordinateur_naviguer", "ordinateur_capture_ecran",
           "ordinateur_detruire",
           "git_statut", "git_diff", "git_checkpoint", "git_restaurer",
           "git_stager", "git_desindexer", "git_commettre",
           "git_branches_lister", "git_branche_creer", "git_basculer",
           "git_recuperer", "git_tirer", "git_pousser",
           "git_fusionner", "git_rebaser", "git_cherry_pick", "git_revert",
           "git_tag_creer", "git_remiser", "git_remise_appliquer",
           "git_conflit_lire", "git_continuer", "git_abandonner",
           "terminer")

#: Les actions qui modifient quelque chose. Elles sont comptées à part dans le
#: rapport : « j'ai lu quatre fichiers » et « j'ai modifié quatre fichiers » ne
#: se lisent pas pareil, et c'est la seconde phrase qui demande une vérification.
ACTIONS_QUI_MODIFIENT = frozenset({
    "ecrire", "remplacer", "deplacer", "github_ecrire", "github_remplacer",
})

#: Mutations directes qui ne doivent jamais etre suivies immediatement de
#: `terminer`. Une verification REELLE doit arriver APRES la derniere
#: mutation : lire le resultat, lancer un test, regarder le diff ou la CI.
#: Le garde reste volontairement generique pour fonctionner aussi bien sur du
#: code que sur des fichiers ordinaires.
ACTIONS_A_VERIFIER = frozenset({
    "ecrire", "remplacer", "deplacer", "github_ecrire", "github_remplacer",
    "ordinateur_ecrire_fichier",
})

#: Actions capables d'apporter une preuve apres une mutation. Le prompt métier
#: decide quelle preuve est pertinente (tests pour du code, relecture pour un
#: document, CI pour GitHub) ; ce garde empeche seulement « j'ai ecrit, donc
#: c'est fini ».
ACTIONS_DE_VERIFICATION = frozenset({
    # Une preuve, pas une nouvelle opinion du modele : analyser/diagnostiquer
    # ne peuvent donc jamais valider une mutation.
    "lire", "lister", "executer",
    "github_lire", "github_diff", "etat_ci",
    "ordinateur_etat", "ordinateur_executer", "ordinateur_lire_fichier",
    "git_statut", "git_diff", "git_conflit_lire",
})

#: Le journal complet reste dans le stockage durable. Pour le MODELE, on borne
#: seulement le contexte repasse a chaque tour : sinon douze lectures de
#: 20 000 caracteres peuvent transformer une petite tache en requete enorme et
#: provoquer un 429 cloud. Les etapes recentes restent completes ; les plus
#: anciennes deviennent des resumes d'une ligne.
JOURNAL_MODELE_MAX_CARACTERES = 42_000
JOURNAL_MODELE_RESUME_MAX_CARACTERES = 8_000

#: Les actions dont la SORTIE est le résultat qui compte, pas seulement le
#: message. `_rapport()` ne montre le détail complet que de celles-ci : pour
#: `lire` ou `chercher`, le message suffit et la sortie serait du bruit.
#: `convertir` y entre pour la même raison qu'`etat_ci` : le détail (moteur
#: utilisé, URL du fichier écrit, tailles avant/après) est ce que le
#: propriétaire veut voir, pas seulement « converti ». `organiser_inspecter`/
#: `organiser_planifier` de même : l'inventaire et le plan JSON complet sont
#: ce qu'il doit lire pour décider — jamais `organiser_appliquer`/`_annuler`,
#: dont le message résume déjà les comptages (même choix qu'`ouvrir_pr`).
#: `pdf_fusionner`/`_demonter`/`_pages`/`_extraire_texte` de même : URL du
#: fichier écrit, liste des documents (manifeste), ou texte lui-même sont
#: ce que le propriétaire lit pour vérifier, pas un simple « fait ».
ACTIONS_QUI_ANALYSENT = frozenset({
    "analyser", "diagnostiquer", "etat_ci", "github_diff", "commentaires_pr", "convertir",
    "organiser_inspecter", "organiser_planifier",
    "pdf_fusionner", "pdf_demonter", "pdf_pages", "pdf_extraire_texte",
    "isoler",
    "ordinateur_lister", "ordinateur_creer", "ordinateur_etat",
    "ordinateur_executer", "ordinateur_lire_fichier",
    "ordinateur_naviguer", "ordinateur_capture_ecran",
    "git_statut", "git_diff", "git_checkpoint", "git_restaurer",
    "git_branches_lister", "git_conflit_lire",
})

#: Lectures dont la sortie sert de filet de securite seulement si le modele
#: n'a pas pu conclure. Sur un tour normal, la conclusion humaine a deja
#: extrait ce qui compte (par exemple trois fichiers sur onze) : recopier le
#: listing complet juste dessous est du bruit. En cas de 429/coupure apres
#: l'outil, cette preuve reste visible au lieu d'etre perdue.
ACTIONS_PREUVES_DE_REPLI = frozenset({
    "github_lister", "github_chercher", "lister", "chercher",
})

_ETIQUETTE = re.compile(r"^\s*ACTION\s*:\s*(\w+)", re.IGNORECASE | re.MULTILINE)
_CHAMP = re.compile(
    r"^\s*(CHEMIN|SOURCE|DESTINATION|COMMANDE|DOSSIER|TEXTE|DEPOT|TITRE|TETE|BASE|REF|FORMAT"
    r"|SHA|PLAN_ID|CONFIRMER_SUPPRESSION|OPERATION|PAGES|DEGRES|FORMAT_PDFX|NOM|NUMERO|COMPUTER_ID|URL"
    r"|CIBLE|IDENTIFIANT|IDENTIFIANT_OPERATION|DISTANT|BRANCHE|AMEND|FORCE_AVEC_BAIL"
    r"|TETE_ATTENDUE|REBASE|SUR|COMMIT|DEPUIS|BASCULER|MESSAGE|INDEX|GARDER"
    r"|INCLURE_NON_SUIVIS)"
    r"\s*:\s*(.+)$",
    re.IGNORECASE | re.MULTILINE)

#: Les blocs multilignes, chacun fermé par une ligne `FIN`. `remplacer` en
#: demande deux — l'ancien passage et le nouveau — ce qu'un bloc unique ne
#: pouvait pas porter.
BLOCS = ("CONTENU", "ANCIEN", "NOUVEAU")

CONSIGNE = """Tu es Dioumtoukay. Tu travailles sur la machine du proprietaire :
ses fichiers, son terminal, ses depots git. Tu n'expliques pas ce que tu ferais,
tu le fais.

Tu reponds par UNE SEULE action, dans ce format exact, et rien d'autre :

ACTION: lister
CHEMIN: .

ACTION: chercher
TEXTE: def calculer_total
CHEMIN: .

ACTION: lire
CHEMIN: apps/backend/config.py

ACTION: remplacer
CHEMIN: apps/backend/config.py
ANCIEN:
le passage exact, copie du fichier que tu viens de lire
FIN
NOUVEAU:
ce qui prend sa place
FIN

ACTION: ecrire
CHEMIN: apps/backend/config.py
CONTENU:
le contenu complet du fichier
FIN

ACTION: deplacer
SOURCE: vrac/photo.jpg
DESTINATION: photos/2026/photo.jpg

ACTION: executer
COMMANDE: python -m pytest -q
DOSSIER: .

ACTION: analyser
TEXTE: comment est organisee la gestion des connecteurs dans ce depot ?

ACTION: diagnostiquer
TEXTE: la route /machine/adresse rend 500 au lieu de 401 sans cle

ACTION: github_lister
DEPOT: owner/repo
REF: ta-branche
CHEMIN: apps

ACTION: github_lire
DEPOT: owner/repo
REF: ta-branche
CHEMIN: apps/backend/config.py

ACTION: github_chercher
DEPOT: owner/repo
TEXTE: def calculer_total

ACTION: github_diff
DEPOT: owner/repo
BASE: main
TETE: ta-branche

ACTION: github_branche_creer
DEPOT: owner/repo
NOM: fix-mobile
DEPUIS: main

ACTION: github_ecrire
DEPOT: owner/repo
BRANCHE: fix-mobile
CHEMIN: apps/backend/config.py
SHA: sha rendu par github_lire si le fichier existe
MESSAGE: fix: corrige la configuration
CONTENU:
le contenu complet du fichier
FIN

ACTION: github_remplacer
DEPOT: owner/repo
BRANCHE: fix-mobile
CHEMIN: apps/backend/config.py
SHA: sha rendu par github_lire
MESSAGE: fix: corrige la configuration
ANCIEN:
le passage exact et unique lu dans le fichier
FIN
NOUVEAU:
le passage qui le remplace
FIN

ACTION: ouvrir_pr
DEPOT: owner/repo
TETE: ta-branche
BASE: main
TITRE: Corrige la route /machine/adresse
CONTENU:
ce que le correctif change, pour qui va relire
FIN

ACTION: etat_ci
DEPOT: owner/repo
REF: ta-branche

ACTION: commentaires_pr
DEPOT: owner/repo
NUMERO: 123

ACTION: convertir
CHEMIN: documents/devis.pdf
FORMAT: docx

ACTION: organiser_inspecter
DOSSIER: vrac

ACTION: organiser_planifier
DOSSIER: vrac
CONTENU:
creer_dossier|Images||photos a trier
deplacer|IMG_2048.jpg|Images/clouds_over_lake.jpg|photo de nuages
FIN

ACTION: organiser_appliquer
PLAN_ID: identifiant rendu par organiser_planifier

ACTION: organiser_annuler
PLAN_ID: identifiant d'un plan deja applique

ACTION: pdf_fusionner
TITRE: Dossier client
FORMAT_PDFX: oui
CONTENU:
contrat.pdf
devis.pdf
facture.pdf
FIN

ACTION: pdf_demonter
CHEMIN: dossier-client.pdfx

ACTION: pdf_pages
CHEMIN: rapport.pdf
OPERATION: extraire_pages
PAGES: 3,4,5,6,7

ACTION: pdf_extraire_texte
CHEMIN: facture.pdf

ACTION: isoler
NOM: correctif-toiture
BASE: HEAD

ACTION: nettoyer_worktree
NOM: correctif-toiture

ACTION: ordinateur_creer
NOM: test-linux

ACTION: ordinateur_lister

ACTION: ordinateur_executer
COMPUTER_ID: id rendu par ordinateur_creer ou ordinateur_lister
COMMANDE: pytest -q

ACTION: ordinateur_lire_fichier
COMPUTER_ID: id de l'ordinateur
CHEMIN: /home/agent/rapport.txt

ACTION: ordinateur_ecrire_fichier
COMPUTER_ID: id de l'ordinateur
CHEMIN: /home/agent/notes.txt
CONTENU:
le contenu du fichier
FIN

ACTION: ordinateur_naviguer
COMPUTER_ID: id de l'ordinateur
URL: https://exemple.test

ACTION: ordinateur_capture_ecran
COMPUTER_ID: id de l'ordinateur

ACTION: ordinateur_dormir
COMPUTER_ID: id de l'ordinateur

ACTION: ordinateur_detruire
COMPUTER_ID: id de l'ordinateur

ACTION: git_statut
DOSSIER: .

ACTION: git_diff
CIBLE: travail
CHEMIN: apps/backend/config.py

ACTION: git_checkpoint
DOSSIER: .

ACTION: git_restaurer
IDENTIFIANT: identifiant rendu par git_checkpoint

ACTION: git_stager
CONTENU:
apps/backend/config.py
tests/test_config.py
FIN

ACTION: git_commettre
IDENTIFIANT_OPERATION: correctif-config-1
CONTENU:
fix: corrige le port par defaut de la config
FIN

ACTION: git_desindexer
CHEMIN: apps/backend/config.py

ACTION: git_branches_lister

ACTION: git_branche_creer
NOM: correctif-config
DEPUIS: HEAD
BASCULER: oui

ACTION: git_basculer
CIBLE: correctif-config

ACTION: git_recuperer
DISTANT: origin

ACTION: git_tirer
DISTANT: origin
REBASE: non

ACTION: git_pousser
DISTANT: origin
BRANCHE: correctif-config
FORCE_AVEC_BAIL: non

ACTION: git_fusionner
BRANCHE: main

ACTION: git_rebaser
SUR: main

ACTION: git_cherry_pick
COMMIT: a1b2c3d

ACTION: git_revert
COMMIT: a1b2c3d

ACTION: git_tag_creer
NOM: v1.2.0
CIBLE: HEAD
MESSAGE: version stable

ACTION: git_remiser
MESSAGE: travail en cours
INCLURE_NON_SUIVIS: non

ACTION: git_remise_appliquer
INDEX: 0
GARDER: non

ACTION: git_conflit_lire
CHEMIN: apps/backend/config.py

ACTION: git_continuer

ACTION: git_abandonner

ACTION: terminer
CONTENU:
ce que tu as fait, en francais simple, pour le proprietaire
FIN

COMMENT TRAVAILLER

1. TROUVER avant de corriger. `chercher` te dit dans quel fichier est le
   probleme ; deviner le fichier fait perdre des tours. Sur une tache large ou
   floue (« comment est fait ce depot », « ou est le bug »), `analyser` et
   `diagnostiquer` peuvent trouver plus vite qu'une suite de `chercher` a
   l'aveugle — ce sont deux specialistes, consulte-les, ne les remplace pas.
2. LIRE avant de modifier. Tu ne modifies jamais un fichier que tu n'as pas lu
   dans cette conversation. Sur GitHub distant, pour une correction locale dans
   un fichier existant, prefere `github_remplacer` : cite ANCIEN exactement et
   remplace seulement ce passage. `github_ecrire` reecrit le fichier complet.
   `analyser` et `diagnostiquer` NE MODIFIENT RIEN
   eux-memes : ils proposent, c'est toujours toi qui appliques par `remplacer`
   ou `ecrire`, apres avoir lu le fichier concerne.
3. `remplacer` est la BONNE facon de corriger : tu cites le passage exact et il
   change, le reste du fichier ne bouge pas. `ecrire` remplace TOUT le fichier
   et sert a en creer un nouveau — l'utiliser pour corriger une ligne t'oblige
   a reecrire tout le reste de memoire, et c'est ainsi qu'on casse un fichier
   qui marchait.
4. VERIFIER. Apres avoir touche du code, lance ce qui le prouve : les tests, le
   linter, ou la commande qui echouait. Un travail non verifie n'est pas fini,
   et tu ne dis jamais que ca marche sans l'avoir lance.
5. Une erreur se comprend avant de se corriger. Lis le message en entier,
   trouve la cause, corrige la cause. Ne contourne pas, ne desactive pas un
   test, n'attrape pas une exception pour la faire taire.
6. `ouvrir_pr` s'ouvre TOUJOURS en brouillon, meme si tu ne l'as pas demande —
   ce n'est pas un defaut a contourner. Elle demande une confirmation au
   proprietaire avant de partir : elle peut donc rendre « en attente » au lieu
   d'un lien tout de suite. Ne la retente pas plusieurs fois pour la meme
   branche en esperant un autre resultat.
7. `convertir` choisit elle-meme le moteur (LibreOffice, Pillow, ffmpeg...) —
   tu donnes juste CHEMIN et FORMAT (l'extension cible, sans le point). Un
   couple de formats que rien ne convertit encore te le dit clairement ;
   n'invente jamais un fichier converti que tu n'as pas reellement obtenu.
8. Pour ranger des fichiers : `organiser_inspecter` d'abord (regarde ce qu'il
   y a vraiment avant de proposer quoi que ce soit), PUIS `organiser_
   planifier` — un plan par ligne `type|source|destination|raison`
   (`destination` vide pour `supprimer`). `organiser_planifier` NE DEPLACE
   RIEN : il rend un identifiant de plan valide. Seul `organiser_appliquer`
   avec cet identifiant deplace reellement — et une suppression dans le plan
   exige en plus `CONFIRMER_SUPPRESSION: oui`, sans quoi elle est refusee.
   `organiser_annuler` defait un plan applique, sauf ses suppressions
   (jamais reversibles). N'invente jamais un identifiant de plan.
9. `isoler` cree un dossier de travail SEPARE (un worktree git, sur sa propre
   branche) sans toucher l'arbre principal — utile pour un correctif risque
   ou une tache parallele. Il rend le chemin du worktree ; passe ensuite ce
   chemin en DOSSIER: aux actions suivantes pour travailler VRAIMENT dedans.
   Ce n'est jamais obligatoire : tu peux continuer a travailler directement
   sur l'arbre principal si la tache ne le demande pas. `nettoyer_worktree`
   le retire une fois fini — il echoue si des modifications n'y sont pas
   commitees, et c'est voulu : rien n'ecrase un travail non sauvegarde.
10. `ordinateur_*` donne un ORDINATEUR LINUX ISOLE ET PERSISTANT (Case),
   different de la machine du proprietaire — jamais un chemin oblige non
   plus, utile pour un test specifiquement Linux, un paquet a ne pas
   installer sur la vraie machine, un navigateur qui doit garder son
   identite d'une session a l'autre. `ordinateur_creer` rend un COMPUTER_ID
   (ou `ordinateur_lister` en retrouve un existant) ; passe-le a toutes les
   actions suivantes. `ordinateur_detruire` demande une confirmation au
   proprietaire — irreversible, ne le retente pas en esperant un autre
   resultat.
11. `git_statut` te dit vraiment ce qui a change (branche, fichiers
   modifies/indexes/non suivis/en conflit) sans avoir a lire du texte —
   consulte-le AVANT de modifier davantage un depot dont tu ne connais pas
   l'etat. `git_diff` (CIBLE: travail|index|un commit, CHEMIN optionnel)
   montre le contenu reel d'un changement. Avant une modification risquee
   (plusieurs fichiers, un correctif dont tu n'es pas sur), `git_checkpoint`
   photographie l'etat actuel et rend un IDENTIFIANT ; si la suite tourne
   mal, `git_restaurer` avec cet identifiant annule CE QUE TU AS TOI-MEME
   ajoute depuis — jamais un fichier deja modifie par le proprietaire avant
   ton checkpoint, meme si tu l'as touche ensuite : ce fichier-la n'est
   jamais restaure, pour ne rien ecraser qui ne t'appartient pas.
12. `pdf_fusionner` prend un fichier par ligne dans CONTENU, DANS L'ORDRE
   demande — c'est cet ordre qui range les documents dans le resultat.
   `FORMAT_PDFX: oui` ajoute le manifeste (recuperable ensuite par
   `pdf_demonter`) ; sans lui, c'est une simple concatenation de PDF.
   `pdf_pages` : PAGES est une liste d'index a partir de 0 (page 1 du
   document = index 0) — jamais a partir de 1. OPERATION choisit entre
   `reordonner` (PAGES devient le nouvel ordre complet), `supprimer_pages`,
   `extraire_pages`, ou `pivoter_pages` (ajoute DEGRES, multiple de 90).
13. `git_stager`/`git_desindexer` (CONTENU : un chemin par ligne, ou CHEMIN
   pour un seul) avant `git_commettre` (CONTENU : le message). Un
   IDENTIFIANT_OPERATION repasse a l'identique NE REJOUE JAMAIS la meme
   mutation — utile apres une reponse perdue, jamais besoin de verifier "est-ce
   deja fait ?" a la main. TETE_ATTENDUE (le TETE rendu par un `git_statut`
   precedent) refuse de committer/fusionner/rebaser/picorer/annuler si le
   depot a change depuis sans que tu le saches — relis l'etat plutot que
   d'ignorer le refus. `git_pousser` ne force JAMAIS silencieusement : un
   rejet non-fast-forward reste un rejet, `FORCE_AVEC_BAIL: oui` ajoute
   seulement `--force-with-lease` (refuse tout seul si quelqu'un d'autre a
   pousse entre-temps), jamais un `--force` nu. `git_fusionner`/`git_rebaser`
   qui rendent un conflit laissent le depot EN CONFLIT : `git_conflit_lire`
   montre les trois cotes (ta version, la base, l'autre version) — ne choisis
   jamais automatiquement l'un des deux, ecris la resolution reelle, puis
   `git_stager` le fichier resolu, puis `git_continuer`. `git_abandonner`
   revient a l'etat d'avant la fusion/le rebase/le picorage/le revert en
   cours, proprement. Aucune de ces actions ne fait jamais `reset --hard` ni
   `clean -fd` : ce registre reste uniquement accessible via `executer` en
   toutes lettres, jamais un defaut ici.

REGLES

- Si le depot vise n'est pas present sur le disque de la machine qui execute
  ARENA (par exemple le serveur permanent quand le PC est eteint), utilise
  github_lister/github_lire/github_chercher/github_branche_creer/github_ecrire. Pour modifier
  un fichier existant, lis-le d'abord : son SHA est obligatoire a l'ecriture.
  Ecris toujours sur une branche de travail, jamais directement sur main.
  Les tests de la PR sont ensuite la preuve d'execution quand aucun terminal
  persistant n'est disponible.
- Le resultat reel de chaque action t'est rendu ; travaille sur ce resultat,
  jamais sur ce que tu supposes.
- Pour du code venu de GitHub : clone, installe, lance. Tout est permis, rien
  n'est bloque — mais lis avant de lancer, et dis-lui ce que tu as vu.
- Quand tu changes le code d'un depot, travaille sur une branche a toi.
- Quand le travail est fait, ou quand tu es bloque, reponds `ACTION: terminer`
  et dis la verite sur ce qui a marche et ce qui n'a pas marche. Un travail a
  moitie fait se dit ; il ne se presente pas comme fini."""


CONSIGNE_GITHUB_DISTANT = """Tu es Dioumtoukay en mode GitHub distant.
Le PC du proprietaire et Ollama peuvent etre eteints. Le depot local visible
sur ce serveur est une image de deploiement ephemere : tu ne l utilises PAS
comme espace de travail Git. Tu travailles uniquement avec le depot GitHub
distant annonce dans les reperes.

Tu reponds par UNE SEULE action et rien d autre. Actions autorisees ici :

ACTION: github_lister
CHEMIN: apps/pwa
REF: main

ACTION: github_lire
CHEMIN: apps/pwa/src/App.tsx
REF: main

ACTION: github_chercher
TEXTE: def calculer_total
CHEMIN: apps

ACTION: github_diff
BASE: main
TETE: fix-exemple

ACTION: github_branche_creer
NOM: fix-exemple
DEPUIS: main

ACTION: github_ecrire
BRANCHE: fix-exemple
CHEMIN: apps/backend/config.py
SHA: sha rendu par github_lire si le fichier existe
MESSAGE: fix: corrige la configuration
CONTENU:
le contenu COMPLET du fichier
FIN

ACTION: github_remplacer
BRANCHE: fix-exemple
CHEMIN: apps/backend/config.py
SHA: sha rendu par github_lire
MESSAGE: fix: corrige la configuration
ANCIEN:
le passage exact et unique lu dans le fichier
FIN
NOUVEAU:
le passage qui le remplace
FIN

ACTION: ouvrir_pr
TETE: fix-exemple
BASE: main
TITRE: Corrige le probleme
CONTENU:
ce que le correctif change
FIN

ACTION: etat_ci
REF: fix-exemple

ACTION: commentaires_pr
NUMERO: 123

ACTION: terminer
CONTENU:
ce que tu as verifie ou modifie, en francais simple
FIN

REGLES :
- github_lister/github_lire/github_chercher servent a explorer le depot distant.
- github_diff compare la branche de travail a main : utilise-le avant une PR
  ou apres plusieurs ecritures pour verifier l'ensemble du changement.
- commentaires_pr lit les retours de revue : traite les remarques avant de conclure.
- Avant de modifier un fichier existant, lis-le sur la branche cible et reutilise
  exactement le SHA rendu. Un SHA absent ou perime est refuse par le connecteur.
- Pour une correction locale dans un fichier existant, PREFERE github_remplacer :
  envoie le passage ANCIEN exact et unique + le NOUVEAU. Le connecteur reconstruit
  le fichier complet lui-meme. github_ecrire sert surtout a creer un fichier ou
  quand l'ensemble de son contenu doit reellement changer.
- Cree une branche de travail avant toute ecriture. Jamais d ecriture directe sur main.
- Apres modification, verifie le fichier ou le diff. Si une CI existe, seul
  resume: succes est une preuve positive : en_cours, en_attente et echec ne
  veulent jamais dire que le travail est termine.
- Ouvre ensuite une PR quand la politique de confirmation le permet et utilise
  sa CI comme preuve supplementaire.
- Le resultat reel de chaque action fait foi. N invente jamais une lecture,
  une modification, une CI ou un succes.
- Si tu es bloque, termine et nomme exactement le blocage.
"""


PROTOCOLE_QUALITE = """STANDARD DE TRAVAIL — VALABLE DANS TOUS LES DOMAINES

- Commence par comprendre l'objectif concret et la preuve qui permettra de
  dire que c'est termine. Ne transforme pas une demande simple en audit geant.
- Mesure avant de conclure. Un fichier, une commande, une API, une image, une
  CI ou un document reel vaut plus qu'une supposition.
- Quand il y a un probleme, cherche la cause racine avant de corriger le
  symptome. Change le minimum coherent, pas un cas special qui masque le bug.
- Une modification n'est pas une preuve. Apres la DERNIERE mutation, verifie
  le resultat avec l'outil adapte au domaine : test/diff/CI pour du code,
  relecture pour un document, inspection pour des fichiers, etat reel pour un
  service.
- Si une methode de specialiste est fournie plus bas, applique-la comme une
  discipline de travail, pas comme un personnage. Pour un domaine non couvert,
  garde les memes principes : evidence, cause, changement minimal, verification.
- Ne fabrique jamais une capacite absente. Si un outil manque ou une donnee
  n'est pas accessible, nomme exactement la limite.
- Le compte-rendu final est pour un humain : resultat d'abord, preuves utiles
  ensuite. Pas de dictionnaires Python, de payloads internes, de SHA ou de
  metadonnees brutes sauf si elles servent vraiment a la decision.
- N'annonce jamais « termine », « corrige », « vert » ou « fonctionne » sans
  preuve executee dans cette tache.
"""

@dataclass
class Action:
    """Une action demandée par le modèle, telle qu'elle a été lue."""

    nom: str
    champs: Dict[str, str] = field(default_factory=dict)
    blocs: Dict[str, str] = field(default_factory=dict)

    @property
    def contenu(self) -> str:
        """Le bloc `CONTENU:`, celui qu'écrivent `ecrire` et `terminer`."""
        return self.blocs.get("CONTENU", "")

    def signature(self) -> tuple:
        """Identité de l'action pour la garde anti-répétition.

        Deux actions ont la même signature quand elles feraient exactement le
        même geste — même nom, mêmes champs, mêmes blocs. Un `ecrire` sur le
        même CHEMIN mais avec un CONTENU différent n'est PAS une répétition :
        les blocs entrent dans la signature pour ça.
        """
        return (self.nom, tuple(sorted(self.champs.items())),
                tuple(sorted(self.blocs.items())))


def _lire_bloc(nom: str, texte: str) -> Optional[str]:
    """Le contenu d'un bloc `NOM:` … `FIN`, tel qu'il a été écrit.

    Rien n'est nettoyé au-delà du saut de ligne d'ouverture : l'indentation
    d'un bloc de code EST le code, et la retirer casserait un fichier Python.
    """
    motif = re.compile(rf"^\s*{nom}\s*:[ \t]*\n(.*?)(?:\n[ \t]*FIN[ \t]*$|\Z)",
                       re.IGNORECASE | re.MULTILINE | re.DOTALL)
    trouve = motif.search(texte)
    return trouve.group(1) if trouve else None


def analyser_action(texte: str) -> Optional[Action]:
    """Lit l'action dans la réponse du modèle. `None` si elle est illisible.

    Déterministe : aucun second appel au modèle pour comprendre le premier. Une
    réponse mal formée est une réponse mal formée, et le lui dire vaut mieux que
    deviner ce qu'il voulait.
    """
    etiquette = _ETIQUETTE.search(texte or "")
    if not etiquette:
        return None
    nom = etiquette.group(1).lower()
    if nom not in ACTIONS:
        return None

    champs = {cle.upper(): valeur.strip()
              for cle, valeur in _CHAMP.findall(texte)}
    blocs = {}
    for bloc in BLOCS:
        lu = _lire_bloc(bloc, texte)
        if lu is not None:
            blocs[bloc] = lu
    return Action(nom=nom, champs=champs, blocs=blocs)


class DioumtoukayAgent(BaseAgent):
    """Il entre dans les fichiers, le terminal et le dépôt, et il agit."""

    def __init__(self, provider: ModelProvider, memory: Optional[MemoryManager] = None,
                 atelier: Optional[Atelier] = None,
                 memoire_longue: Optional[MemoirePersonnelle] = None,
                 analyste: Optional[Any] = None, chercheur_de_bug: Optional[Any] = None,
                 connecteur_github: Optional[Any] = None,
                 connecteur_file_conversion: Optional[Any] = None,
                 connecteur_file_organization: Optional[Any] = None,
                 connecteur_pdf: Optional[Any] = None,
                 connecteur_case: Optional[Any] = None,
                 reprises: Optional[JournalDeReprise] = None,
                 depot_github_defaut: Optional[str] = None):
        super().__init__(
            name="DioumtoukayAgent",
            description="Agent qui travaille reellement sur les fichiers, "
                        "le terminal et les depots git du proprietaire.",
            provider=provider,
            memory=memory,
        )
        self.atelier = atelier or Atelier()
        # `memory` est le fil de la conversation ; `memoire_longue` est ce dont
        # on se souvient d'une semaine sur l'autre. Ce sont deux objets
        # differents dans ce projet, et les confondre reviendrait a n'ecrire
        # nulle part.
        self.memoire_longue = memoire_longue
        # DEC-0073 : deux specialistes en lecture seule, consultes en cours de
        # tache plutot que d'etre deux portes separees. Optionnels — sans eux,
        # `analyser`/`diagnostiquer` repondent qu'ils manquent, comme toute
        # capacite non branchee ailleurs dans ARENA.
        self.analyste = analyste
        self.chercheur_de_bug = chercheur_de_bug
        # Le connecteur GitHub (core/connectors/github.py) : la creation de PR
        # y passe par la meme confirmation que toute autre ecriture externe —
        # Dioumtoukay ne contourne rien en l'appelant, il herite de la garde.
        self.connecteur_github = connecteur_github
        # Depot distant a utiliser quand le serveur permanent n'a pas le depot
        # du proprietaire sur son propre disque. Il vient de la configuration,
        # jamais d'un nom code en dur dans l'agent.
        self.depot_github_defaut = (depot_github_defaut or "").strip()
        # Le connecteur de conversion de fichiers (DEC-0074) : meme discipline
        # que le connecteur GitHub — Dioumtoukay ne sait pas quel moteur
        # tourne derriere, il herite juste de la garde (confirmation, coupe-
        # circuit WRITE_FILES) deja portee par le connecteur lui-meme.
        self.connecteur_file_conversion = connecteur_file_conversion
        # Le connecteur de classement de fichiers (DEC-0075, mission « AI
        # File Sorter ») : meme discipline encore — un plan se propose,
        # SE VALIDE (le connecteur, jamais Dioumtoukay), et ne s'applique
        # que sur son identifiant deja valide, sous confirmation.
        self.connecteur_file_organization = connecteur_file_organization
        # Le connecteur PDF (DEC-0076, mission « PDFx ») : fusionner/
        # scinder/pages/manifeste. Chaque operation ecrit un fichier NEUF,
        # jamais la source — aucune ne demande de confirmation pour cette
        # raison meme.
        self.connecteur_pdf = connecteur_pdf
        # Le connecteur Case (DEC-0092, mission ARENA x CASE) : un ordinateur
        # Linux ISOLE et persistant, distinct de la machine du proprietaire
        # (Atelier reste le seul chemin vers celle-ci, DEC-0038 inchange).
        # Utile pour un test qui doit tourner sur Linux, un paquet qu'on ne
        # veut pas installer sur la vraie machine, un navigateur qui garde
        # son identite entre deux sessions. `creer`/`executer_commande`/
        # `ecrire_fichier`/`naviguer` sont ALLOWED (risque MEDIUM,
        # config/permissions_services.yaml) — un effet reel, mais contenu
        # dans un conteneur qu'ARENA gere elle-meme. `detruire` seul demande
        # confirmation : il supprime des donnees persistantes sans retour.
        self.connecteur_case = connecteur_case
        # Le journal DURABLE de ce qu'il a deja fait (DEC-0072). La memoire
        # longue garde un RESUME de chaque travail ; celui-ci garde les ETAPES,
        # pour qu'une tache arretee a la 12e action reprenne a la 13e au lieu
        # de tout refaire. Les deux ne font pas double emploi : l'une sert a se
        # souvenir, l'autre a continuer.
        self.reprises = reprises if reprises is not None else JournalDeReprise()

    def _workspace_github_distant(self) -> bool:
        """Vrai quand le serveur n a pas de checkout Git utilisable."""
        if not self.depot_github_defaut or self.connecteur_github is None:
            return False
        etat = self.atelier.executer(["git", "rev-parse", "--is-inside-work-tree"])
        return not etat.ok

    def _chemin_github(self, chemin: str) -> str:
        """Transforme un chemin de l image serveur en chemin relatif GitHub."""
        brut = (chemin or ".").replace("\\", "/").strip()
        if brut in ("", "."):
            return ""
        racine = str(self.atelier.racine).replace("\\", "/").rstrip("/")
        if racine and brut == racine:
            return ""
        if racine and brut.startswith(racine + "/"):
            brut = brut[len(racine) + 1:]
        return brut.lstrip("/")

    # --- Exécution d'une action ---------------------------------------------------

    async def _consulter(self, specialiste: Optional[Any], nom_specialiste: str,
                         question: str) -> Resultat:
        """Interroge un specialiste en lecture seule (RepoEngineerAgent ou
        SWEAgent) et rend ce qu'il a repondu comme un `Resultat` ordinaire.

        DEC-0041 : ces deux agents ne modifient jamais rien eux-memes — c'est
        pour ca qu'ils sont surs a appeler en cours de boucle, sans passer par
        les autres actions de l'atelier. Un appel qui leve (le modele n'a pas
        repondu, par exemple) devient un echec rapporte, jamais une exception
        qui casserait la tache entiere de Dioumtoukay pour la faute d'un
        outil consulte en chemin.
        """
        if not question:
            return Resultat(False, "Le champ TEXTE (la question) est vide.")
        if specialiste is None:
            return Resultat(False, f"{nom_specialiste} n'est pas branche sur cette machine.")
        try:
            reponse = await specialiste.run(question)
        except Exception as erreur:  # noqa: BLE001 — un outil consulte ne casse pas la tache
            return Resultat(False, f"{nom_specialiste} n'a pas repondu : "
                                   f"{type(erreur).__name__}: {erreur}")
        if reponse.get("status") not in ("success", None):
            return Resultat(False, reponse.get("response") or
                            f"{nom_specialiste} a echoue sans detail.")
        return Resultat(True, f"{nom_specialiste} a repondu.",
                        sortie=reponse.get("response", ""))

    @staticmethod
    def _detail_lisible(detail: Dict[str, Any]) -> str:
        """Transforme une structure imbriquee en texte stable, jamais en repr Python."""
        lignes: List[str] = []

        def ajouter(nom: str, valeur: Any, niveau: int = 0, puce: bool = False) -> None:
            indentation = "  " * niveau
            prefixe = "- " if puce else ""
            etiquette = f"{nom}: " if nom else ""

            if isinstance(valeur, (bytes, bytearray)):
                lignes.append(
                    f"{indentation}{prefixe}{etiquette}{len(valeur)} octet(s)"
                )
                return

            if isinstance(valeur, dict):
                if nom:
                    lignes.append(f"{indentation}{prefixe}{nom}:")
                elif puce:
                    lignes.append(f"{indentation}-")
                for cle, sous_valeur in valeur.items():
                    ajouter(str(cle), sous_valeur, niveau + 1)
                return

            if isinstance(valeur, (list, tuple)):
                if nom:
                    lignes.append(f"{indentation}{prefixe}{nom}:")
                elif puce:
                    lignes.append(f"{indentation}-")
                if not valeur:
                    lignes.append(f"{indentation}  aucun")
                    return
                for item in valeur:
                    if isinstance(item, (dict, list, tuple)):
                        ajouter("", item, niveau + 1, puce=True)
                    elif isinstance(item, (bytes, bytearray)):
                        lignes.append(
                            f"{'  ' * (niveau + 1)}- {len(item)} octet(s)"
                        )
                    else:
                        lignes.append(f"{'  ' * (niveau + 1)}- {item}")
                return

            if valeur not in ("", None):
                lignes.append(f"{indentation}{prefixe}{etiquette}{valeur}")

        for cle, valeur in (detail or {}).items():
            ajouter(str(cle), valeur)
        return "\n".join(lignes)

    @classmethod
    def _detail_github_lisible(cls, capacite: str, detail: Dict[str, Any]) -> str:
        """Vue utile de GitHub pour le MODELE, sans bruit d'API.

        Une lecture garde le contenu + SHA car l'ecriture optimiste en a besoin.
        Un listing, en revanche, n'a aucune raison de transporter 11 SHA et
        tailles : les chemins et types suffisent pour choisir l'etape suivante.
        """
        if capacite == "lister":
            entrees = detail.get("entrees") or []
            lignes = []
            for entree in entrees:
                if not isinstance(entree, dict):
                    continue
                chemin = entree.get("chemin") or entree.get("nom") or ""
                if not chemin:
                    continue
                genre = "dossier" if entree.get("type") == "dir" else "fichier"
                lignes.append(f"- {chemin} ({genre})")
            return "\n".join(lignes)

        if capacite == "lire_fichier":
            contenu = str(detail.get("contenu") or "")
            sha = str(detail.get("sha") or "")
            ref = str(detail.get("ref") or "")
            entete = []
            if ref:
                entete.append(f"ref: {ref}")
            if sha:
                entete.append(f"sha: {sha}")
            entete.append("CONTENU:")
            entete.append(contenu)
            return "\n".join(entete)

        if capacite == "chercher_code":
            occurrences = detail.get("occurrences") or []
            lignes = []
            for occurrence in occurrences:
                if not isinstance(occurrence, dict):
                    continue
                chemin = occurrence.get("chemin") or ""
                if chemin:
                    lignes.append(f"- {chemin}")
            return "\n".join(lignes)

        if capacite == "comparer":
            lignes = [
                f"statut: {detail.get('statut', 'inconnu')}",
                f"avance: {detail.get('ahead_by', 0)}",
                f"retard: {detail.get('behind_by', 0)}",
                "fichiers modifies:",
            ]
            for fichier in detail.get("fichiers") or []:
                if not isinstance(fichier, dict):
                    continue
                chemin = fichier.get("chemin") or ""
                statut = fichier.get("statut") or ""
                ajouts = fichier.get("ajouts", 0)
                suppressions = fichier.get("suppressions", 0)
                lignes.append(f"- {chemin} ({statut}, +{ajouts}/-{suppressions})")
                patch = str(fichier.get("patch") or "").strip()
                if patch:
                    lignes.append(patch)
            return "\n".join(lignes)

        if capacite == "commentaires_pr":
            lignes = []
            for commentaire in detail.get("commentaires") or []:
                if not isinstance(commentaire, dict):
                    continue
                auteur = commentaire.get("auteur") or "?"
                genre = commentaire.get("genre") or "commentaire"
                chemin = commentaire.get("chemin") or ""
                corps = str(commentaire.get("corps") or "").strip()
                suffixe = f" sur {chemin}" if chemin else ""
                lignes.append(f"- {genre} de {auteur}{suffixe}: {corps}")
            return "\n".join(lignes)

        if capacite == "etat_ci":
            lignes = [f"resume: {detail.get('resume', 'inconnu')}"]
            for verification in detail.get("verifications") or []:
                if not isinstance(verification, dict):
                    continue
                nom = verification.get("nom") or "verification"
                statut = verification.get("conclusion") or verification.get("statut") or "inconnu"
                lignes.append(f"- {nom}: {statut}")
            return "\n".join(lignes)

        return cls._detail_lisible(detail)

    def _via_github(self, capacite: str, **parametres: Any) -> Resultat:
        """Appelle le connecteur GitHub et rend son `ResultatAction` comme un
        `Resultat` ordinaire — Dioumtoukay ne voit qu'un seul type de resultat,
        quelle que soit la source.

        **La confirmation n'est pas contournee ici.** `connecteur.executer()`
        est le meme point d'entree que `/connectors/github/...` : une capacite
        `CONFIRMATION` (creer_pull_request) rend `A_CONFIRMER` sans avoir
        touche le reseau, exactement comme si le propriétaire l'avait demande
        depuis l'interface. `A_CONFIRMER` est rapporte comme un succes
        PARTIEL — l'action a bien ete deposee, mais rien n'est encore parti.
        """
        if self.connecteur_github is None:
            return Resultat(False, "Le connecteur GitHub n'est pas branche sur cette machine.")
        try:
            resultat = self.connecteur_github.executer(capacite, **parametres)
        except Exception as erreur:  # noqa: BLE001 — un connecteur qui leve ne casse pas la tache
            return Resultat(False, f"GitHub n'a pas repondu : {type(erreur).__name__}: {erreur}")

        if resultat.statut in (Statut.SUCCES, Statut.PARTIEL, Statut.A_CONFIRMER):
            detail = self._detail_github_lisible(capacite, resultat.detail or {})
            return Resultat(True, resultat.message, sortie=detail)
        return Resultat(False, resultat.message)

    def _via_file_conversion(self, capacite: str, **parametres: Any) -> Resultat:
        """Meme pont que `_via_github`, vers le connecteur `file_conversion`
        (DEC-0074) — un seul type de resultat pour Dioumtoukay, quelle que
        soit la source."""
        if self.connecteur_file_conversion is None:
            return Resultat(False, "Le connecteur de conversion n'est pas branche sur cette machine.")
        try:
            resultat = self.connecteur_file_conversion.executer(capacite, **parametres)
        except Exception as erreur:  # noqa: BLE001 — un connecteur qui leve ne casse pas la tache
            return Resultat(False, f"Conversion impossible : {type(erreur).__name__}: {erreur}")

        if resultat.statut in (Statut.SUCCES, Statut.PARTIEL, Statut.A_CONFIRMER):
            detail = self._detail_lisible(resultat.detail or {})
            return Resultat(True, resultat.message, sortie=detail)
        return Resultat(False, resultat.message)

    def _via_file_organization(self, capacite: str, **parametres: Any) -> Resultat:
        """Meme pont, vers le connecteur `file_organization` (DEC-0075)."""
        if self.connecteur_file_organization is None:
            return Resultat(False, "Le connecteur de classement n'est pas branche sur cette machine.")
        try:
            resultat = self.connecteur_file_organization.executer(capacite, **parametres)
        except Exception as erreur:  # noqa: BLE001 — un connecteur qui leve ne casse pas la tache
            return Resultat(False, f"Classement impossible : {type(erreur).__name__}: {erreur}")

        if resultat.statut in (Statut.SUCCES, Statut.PARTIEL, Statut.A_CONFIRMER):
            detail = self._detail_lisible(resultat.detail or {})
            return Resultat(True, resultat.message, sortie=detail)
        return Resultat(False, resultat.message)

    @staticmethod
    def _lire_operations(contenu: str) -> Optional[List[Dict[str, str]]]:
        """`type|source|destination|raison` par ligne, `destination` vide
        pour `supprimer`. `None` si une ligne est illisible — jamais une
        supposition sur ce qu'elle voulait dire."""
        operations = []
        for ligne in (contenu or "").splitlines():
            ligne = ligne.strip()
            if not ligne:
                continue
            morceaux = ligne.split("|")
            if len(morceaux) < 2:
                return None
            morceaux += [""] * (4 - len(morceaux))
            type_op, source, destination, raison = (m.strip() for m in morceaux[:4])
            if not type_op or not source:
                return None
            operations.append({"type": type_op, "source": source,
                              "destination": destination, "raison": raison})
        return operations or None

    def _via_pdf(self, capacite: str, **parametres: Any) -> Resultat:
        """Meme pont, vers le connecteur `pdf` (DEC-0076)."""
        if self.connecteur_pdf is None:
            return Resultat(False, "Le connecteur PDF n'est pas branche sur cette machine.")
        try:
            resultat = self.connecteur_pdf.executer(capacite, **parametres)
        except Exception as erreur:  # noqa: BLE001 — un connecteur qui leve ne casse pas la tache
            return Resultat(False, f"Operation PDF impossible : {type(erreur).__name__}: {erreur}")

        if resultat.statut in (Statut.SUCCES, Statut.PARTIEL, Statut.A_CONFIRMER):
            detail = self._detail_lisible(resultat.detail or {})
            return Resultat(True, resultat.message, sortie=detail)
        return Resultat(False, resultat.message)

    def _via_case(self, capacite: str, confirmee: bool = False,
                  **parametres: Any) -> Resultat:
        """Meme pont, vers le connecteur `case` (DEC-0092) — un ordinateur
        Linux isole, jamais la machine du proprietaire.

        A la difference des autres ponts : le detail peut porter des octets
        bruts (`png`, `contenu` d'un fichier lu) — les melanger tels quels
        dans `sortie` produirait du texte illisible ou invalide. Ils sont
        donc decrits (taille), jamais recopies.
        """
        if self.connecteur_case is None:
            return Resultat(False, "Le connecteur Case n'est pas branche sur cette machine.")
        try:
            appel = (self.connecteur_case.executer_confirmee if confirmee
                     else self.connecteur_case.executer)
            resultat = appel(capacite, **parametres)
        except Exception as erreur:  # noqa: BLE001 — un connecteur qui leve ne casse pas la tache
            return Resultat(False, f"Case injoignable : {type(erreur).__name__}: {erreur}")

        if resultat.statut in (Statut.SUCCES, Statut.PARTIEL, Statut.A_CONFIRMER):
            detail = self._detail_lisible(resultat.detail or {})
            return Resultat(True, resultat.message, sortie=detail)
        return Resultat(False, resultat.message)

    @staticmethod
    def _lire_fichiers(contenu: str) -> Optional[List[str]]:
        """Un chemin de fichier par ligne, tel quel — `None` si vide."""
        fichiers = [ligne.strip() for ligne in (contenu or "").splitlines() if ligne.strip()]
        return fichiers or None

    @staticmethod
    def _lire_pages(texte: str) -> Optional[List[int]]:
        """`"3,4,5"` -> `[3, 4, 5]`. `None` si un seul element n'est pas un entier."""
        if not (texte or "").strip():
            return None
        try:
            return [int(p.strip()) for p in texte.split(",") if p.strip()]
        except ValueError:
            return None

    async def _executer_action(self, action: Action,
                               github_distant: Optional[bool] = None) -> Resultat:
        """Fait ce que l'action demande, via l'atelier — ou un specialiste."""
        champs = action.champs
        if github_distant is None:
            github_distant = self._workspace_github_distant()

        if github_distant and action.nom == "lister":
            return self._via_github(
                "lister", depot=self.depot_github_defaut,
                chemin=self._chemin_github(champs.get("CHEMIN", ".")), ref="")
        if github_distant and action.nom == "lire":
            chemin = self._chemin_github(champs.get("CHEMIN", ""))
            if not chemin:
                return Resultat(False, "Il manque CHEMIN pour lire le depot GitHub distant.")
            return self._via_github(
                "lire_fichier", depot=self.depot_github_defaut, chemin=chemin, ref="")
        if github_distant and action.nom == "chercher":
            terme = champs.get("TEXTE", "")
            if not terme:
                return Resultat(False, "Il manque TEXTE pour chercher dans le depot distant.")
            return self._via_github(
                "chercher_code", depot=self.depot_github_defaut, terme=terme,
                chemin=self._chemin_github(champs.get("CHEMIN", ".")))
        if github_distant and action.nom in {"ecrire", "remplacer", "deplacer"}:
            return Resultat(
                False,
                "Le serveur n a pas de checkout Git durable. Utilise "
                "github_branche_creer, github_lire puis github_ecrire sur une branche.")

        if action.nom == "lire":
            return self.atelier.lire(champs.get("CHEMIN", ""))
        if action.nom == "ecrire":
            return self.atelier.ecrire(champs.get("CHEMIN", ""), action.contenu)
        if action.nom == "remplacer":
            # Un remplacement sans `ANCIEN:` reecrirait au hasard. L'absence du
            # bloc est dite ; elle n'est pas comblee par une supposition.
            if "ANCIEN" not in action.blocs:
                return Resultat(False, "Il manque le bloc ANCIEN: … FIN, "
                                       "le passage exact a remplacer.")
            return self.atelier.remplacer(champs.get("CHEMIN", ""),
                                          action.blocs["ANCIEN"],
                                          action.blocs.get("NOUVEAU", ""))
        if action.nom == "chercher":
            return self.atelier.chercher(champs.get("TEXTE", ""),
                                         champs.get("CHEMIN", "."))
        if action.nom == "lister":
            return self.atelier.lister(champs.get("CHEMIN", "."))
        if action.nom == "deplacer":
            return self.atelier.deplacer(champs.get("SOURCE", ""),
                                         champs.get("DESTINATION", ""))
        if action.nom == "isoler":
            nom = champs.get("NOM", "")
            if not nom:
                return Resultat(False, "Il manque NOM — le nom de la branche/worktree a creer.")
            return self.atelier.isoler(nom, base=champs.get("BASE") or "HEAD")
        if action.nom == "nettoyer_worktree":
            nom = champs.get("NOM", "")
            if not nom:
                return Resultat(False, "Il manque NOM — le worktree a retirer.")
            return self.atelier.nettoyer_worktree(nom)
        if action.nom == "ordinateur_lister":
            return self._via_case("lister")
        if action.nom == "ordinateur_creer":
            return self._via_case("creer", nom=champs.get("NOM", ""))
        if action.nom == "ordinateur_etat":
            cid = champs.get("COMPUTER_ID", "")
            if not cid:
                return Resultat(False, "Il manque COMPUTER_ID.")
            return self._via_case("etat", computer_id=cid)
        if action.nom == "ordinateur_dormir":
            cid = champs.get("COMPUTER_ID", "")
            if not cid:
                return Resultat(False, "Il manque COMPUTER_ID.")
            return self._via_case("dormir", computer_id=cid)
        if action.nom == "ordinateur_reveiller":
            cid = champs.get("COMPUTER_ID", "")
            if not cid:
                return Resultat(False, "Il manque COMPUTER_ID.")
            return self._via_case("reveiller", computer_id=cid)
        if action.nom == "ordinateur_executer":
            cid, commande = champs.get("COMPUTER_ID", ""), champs.get("COMMANDE", "")
            if not cid or not commande:
                return Resultat(False, "Il manque COMPUTER_ID ou COMMANDE.")
            return self._via_case("executer_commande", computer_id=cid, commande=commande)
        if action.nom == "ordinateur_lire_fichier":
            cid, chemin = champs.get("COMPUTER_ID", ""), champs.get("CHEMIN", "")
            if not cid or not chemin:
                return Resultat(False, "Il manque COMPUTER_ID ou CHEMIN.")
            return self._via_case("lire_fichier", computer_id=cid, chemin=chemin)
        if action.nom == "ordinateur_ecrire_fichier":
            cid, chemin = champs.get("COMPUTER_ID", ""), champs.get("CHEMIN", "")
            if not cid or not chemin:
                return Resultat(False, "Il manque COMPUTER_ID ou CHEMIN.")
            return self._via_case("ecrire_fichier", computer_id=cid, chemin=chemin,
                                  contenu=action.contenu)
        if action.nom == "ordinateur_naviguer":
            cid, url = champs.get("COMPUTER_ID", ""), champs.get("URL", "")
            if not cid or not url:
                return Resultat(False, "Il manque COMPUTER_ID ou URL.")
            return self._via_case("naviguer", computer_id=cid, url=url)
        if action.nom == "ordinateur_capture_ecran":
            cid = champs.get("COMPUTER_ID", "")
            if not cid:
                return Resultat(False, "Il manque COMPUTER_ID.")
            return self._via_case("capture_ecran", computer_id=cid)
        if action.nom == "ordinateur_detruire":
            cid = champs.get("COMPUTER_ID", "")
            if not cid:
                return Resultat(False, "Il manque COMPUTER_ID.")
            return self._via_case("detruire", computer_id=cid)
        if action.nom == "git_statut":
            return self.atelier.git_statut(dossier=champs.get("DOSSIER") or None)
        if action.nom == "git_diff":
            chemin = champs.get("CHEMIN", "")
            return self.atelier.git_diff(
                cible=champs.get("CIBLE") or "travail",
                chemins=[chemin] if chemin else None,
                dossier=champs.get("DOSSIER") or None)
        if action.nom == "git_checkpoint":
            return self.atelier.git_checkpoint(dossier=champs.get("DOSSIER") or None)
        if action.nom == "git_restaurer":
            identifiant = champs.get("IDENTIFIANT", "")
            if not identifiant:
                return Resultat(False, "Il manque IDENTIFIANT — celui rendu par git_checkpoint.")
            return self.atelier.git_restaurer(identifiant)
        if action.nom == "git_stager":
            chemins = self._lire_fichiers(action.contenu) or (
                [champs["CHEMIN"]] if champs.get("CHEMIN") else None)
            if not chemins:
                return Resultat(False, "Il manque CHEMIN, ou un bloc CONTENU: … FIN "
                                       "avec un chemin par ligne.")
            return self.atelier.git_stager(
                chemins, identifiant_operation=champs.get("IDENTIFIANT_OPERATION") or None,
                dossier=champs.get("DOSSIER") or None)
        if action.nom == "git_desindexer":
            chemins = self._lire_fichiers(action.contenu) or (
                [champs["CHEMIN"]] if champs.get("CHEMIN") else None)
            if not chemins:
                return Resultat(False, "Il manque CHEMIN, ou un bloc CONTENU: … FIN "
                                       "avec un chemin par ligne.")
            return self.atelier.git_desindexer(
                chemins, identifiant_operation=champs.get("IDENTIFIANT_OPERATION") or None,
                dossier=champs.get("DOSSIER") or None)
        if action.nom == "git_commettre":
            message = action.contenu or champs.get("MESSAGE", "")
            if not message.strip():
                return Resultat(False, "Il manque le message de commit "
                                       "(bloc CONTENU: … FIN, ou MESSAGE).")
            amend = champs.get("AMEND", "").strip().lower() in ("oui", "true", "yes")
            return self.atelier.git_commettre(
                message, amend=amend, tete_attendue=champs.get("TETE_ATTENDUE") or None,
                identifiant_operation=champs.get("IDENTIFIANT_OPERATION") or None,
                dossier=champs.get("DOSSIER") or None)
        if action.nom == "git_branches_lister":
            return self.atelier.git_branches_lister(dossier=champs.get("DOSSIER") or None)
        if action.nom == "git_branche_creer":
            nom = champs.get("NOM", "")
            if not nom:
                return Resultat(False, "Il manque NOM — le nom de la branche a creer.")
            basculer = champs.get("BASCULER", "oui").strip().lower() in ("oui", "true", "yes")
            return self.atelier.git_branche_creer(
                nom, depuis=champs.get("DEPUIS") or "HEAD", basculer=basculer,
                identifiant_operation=champs.get("IDENTIFIANT_OPERATION") or None,
                dossier=champs.get("DOSSIER") or None)
        if action.nom == "git_basculer":
            cible = champs.get("CIBLE", "")
            if not cible:
                return Resultat(False, "Il manque CIBLE — la branche ou le commit vise.")
            return self.atelier.git_basculer(
                cible, identifiant_operation=champs.get("IDENTIFIANT_OPERATION") or None,
                dossier=champs.get("DOSSIER") or None)
        if action.nom == "git_recuperer":
            return self.atelier.git_recuperer(
                distant=champs.get("DISTANT") or "origin",
                identifiant_operation=champs.get("IDENTIFIANT_OPERATION") or None,
                dossier=champs.get("DOSSIER") or None)
        if action.nom == "git_tirer":
            rebase = champs.get("REBASE", "").strip().lower() in ("oui", "true", "yes")
            return self.atelier.git_tirer(
                distant=champs.get("DISTANT") or "origin", rebase=rebase,
                identifiant_operation=champs.get("IDENTIFIANT_OPERATION") or None,
                dossier=champs.get("DOSSIER") or None)
        if action.nom == "git_pousser":
            force_avec_bail = champs.get("FORCE_AVEC_BAIL", "").strip().lower() in ("oui", "true", "yes")
            return self.atelier.git_pousser(
                distant=champs.get("DISTANT") or "origin", branche=champs.get("BRANCHE") or None,
                force_avec_bail=force_avec_bail,
                identifiant_operation=champs.get("IDENTIFIANT_OPERATION") or None,
                dossier=champs.get("DOSSIER") or None)
        if action.nom == "git_fusionner":
            branche = champs.get("BRANCHE", "")
            if not branche:
                return Resultat(False, "Il manque BRANCHE — la branche a fusionner.")
            return self.atelier.git_fusionner(
                branche, tete_attendue=champs.get("TETE_ATTENDUE") or None,
                identifiant_operation=champs.get("IDENTIFIANT_OPERATION") or None,
                dossier=champs.get("DOSSIER") or None)
        if action.nom == "git_rebaser":
            sur = champs.get("SUR", "")
            if not sur:
                return Resultat(False, "Il manque SUR — la reference sur laquelle rebaser.")
            return self.atelier.git_rebaser(
                sur, tete_attendue=champs.get("TETE_ATTENDUE") or None,
                identifiant_operation=champs.get("IDENTIFIANT_OPERATION") or None,
                dossier=champs.get("DOSSIER") or None)
        if action.nom == "git_cherry_pick":
            commit = champs.get("COMMIT", "")
            if not commit:
                return Resultat(False, "Il manque COMMIT — le commit a picorer.")
            return self.atelier.git_cherry_pick(
                commit, tete_attendue=champs.get("TETE_ATTENDUE") or None,
                identifiant_operation=champs.get("IDENTIFIANT_OPERATION") or None,
                dossier=champs.get("DOSSIER") or None)
        if action.nom == "git_revert":
            commit = champs.get("COMMIT", "")
            if not commit:
                return Resultat(False, "Il manque COMMIT — le commit a annuler.")
            return self.atelier.git_revert(
                commit, tete_attendue=champs.get("TETE_ATTENDUE") or None,
                identifiant_operation=champs.get("IDENTIFIANT_OPERATION") or None,
                dossier=champs.get("DOSSIER") or None)
        if action.nom == "git_tag_creer":
            nom = champs.get("NOM", "")
            if not nom:
                return Resultat(False, "Il manque NOM — le nom du tag.")
            return self.atelier.git_tag_creer(
                nom, cible=champs.get("CIBLE") or "HEAD", message=champs.get("MESSAGE") or None,
                identifiant_operation=champs.get("IDENTIFIANT_OPERATION") or None,
                dossier=champs.get("DOSSIER") or None)
        if action.nom == "git_remiser":
            inclure = champs.get("INCLURE_NON_SUIVIS", "").strip().lower() in ("oui", "true", "yes")
            return self.atelier.git_remiser(
                message=champs.get("MESSAGE") or None, inclure_non_suivis=inclure,
                identifiant_operation=champs.get("IDENTIFIANT_OPERATION") or None,
                dossier=champs.get("DOSSIER") or None)
        if action.nom == "git_remise_appliquer":
            index_brut = champs.get("INDEX", "0").strip()
            index = int(index_brut) if index_brut.isdigit() else 0
            garder = champs.get("GARDER", "").strip().lower() in ("oui", "true", "yes")
            return self.atelier.git_remise_appliquer(
                index=index, garder=garder,
                identifiant_operation=champs.get("IDENTIFIANT_OPERATION") or None,
                dossier=champs.get("DOSSIER") or None)
        if action.nom == "git_conflit_lire":
            chemin = champs.get("CHEMIN", "")
            if not chemin:
                return Resultat(False, "Il manque CHEMIN — le fichier en conflit a lire.")
            return self.atelier.git_conflit_lire(chemin, dossier=champs.get("DOSSIER") or None)
        if action.nom == "git_continuer":
            return self.atelier.git_continuer(
                identifiant_operation=champs.get("IDENTIFIANT_OPERATION") or None,
                dossier=champs.get("DOSSIER") or None)
        if action.nom == "git_abandonner":
            return self.atelier.git_abandonner(
                identifiant_operation=champs.get("IDENTIFIANT_OPERATION") or None,
                dossier=champs.get("DOSSIER") or None)
        if action.nom == "analyser":
            return await self._consulter(self.analyste, "RepoEngineerAgent",
                                         champs.get("TEXTE", ""))
        if action.nom == "diagnostiquer":
            return await self._consulter(self.chercheur_de_bug, "SWEAgent",
                                         champs.get("TEXTE", ""))
        if action.nom == "github_lister":
            depot = champs.get("DEPOT") or self.depot_github_defaut
            if not depot:
                return Resultat(False, "Il manque DEPOT (owner/repo).")
            return self._via_github(
                "lister", depot=depot, chemin=champs.get("CHEMIN", ""),
                ref=champs.get("REF", ""))
        if action.nom == "github_lire":
            depot = champs.get("DEPOT") or self.depot_github_defaut
            chemin = champs.get("CHEMIN", "")
            if not depot or not chemin:
                return Resultat(False, "Il manque DEPOT (owner/repo) ou CHEMIN.")
            return self._via_github(
                "lire_fichier", depot=depot, chemin=chemin, ref=champs.get("REF", ""))
        if action.nom == "github_chercher":
            depot = champs.get("DEPOT") or self.depot_github_defaut
            terme = champs.get("TEXTE", "")
            if not depot or not terme:
                return Resultat(False, "Il manque DEPOT (owner/repo) ou TEXTE.")
            return self._via_github(
                "chercher_code", depot=depot, terme=terme,
                chemin=self._chemin_github(champs.get("CHEMIN", ".")))
        if action.nom == "github_diff":
            depot = champs.get("DEPOT") or self.depot_github_defaut
            base, tete = champs.get("BASE") or "main", champs.get("TETE", "")
            if not depot or not tete:
                return Resultat(False, "Il manque DEPOT (owner/repo) ou TETE.")
            return self._via_github("comparer", depot=depot, base=base, tete=tete)
        if action.nom == "github_branche_creer":
            depot = champs.get("DEPOT") or self.depot_github_defaut
            nom = champs.get("NOM", "")
            if not depot or not nom:
                return Resultat(False, "Il manque DEPOT (owner/repo) ou NOM.")
            return self._via_github(
                "creer_branche", depot=depot, nom_branche=nom,
                depuis=champs.get("DEPUIS") or "main")
        if action.nom == "github_ecrire":
            depot = champs.get("DEPOT") or self.depot_github_defaut
            chemin, branche = champs.get("CHEMIN", ""), champs.get("BRANCHE", "")
            if not depot or not chemin or not branche:
                return Resultat(
                    False, "Il manque DEPOT (owner/repo), CHEMIN ou BRANCHE.")
            return self._via_github(
                "ecrire_fichier", depot=depot, chemin=chemin, branche=branche,
                contenu=action.contenu, sha_attendu=champs.get("SHA", ""),
                message=champs.get("MESSAGE", ""))
        if action.nom == "github_remplacer":
            depot = champs.get("DEPOT") or self.depot_github_defaut
            chemin, branche = champs.get("CHEMIN", ""), champs.get("BRANCHE", "")
            if not depot or not chemin or not branche:
                return Resultat(
                    False, "Il manque DEPOT (owner/repo), CHEMIN ou BRANCHE.")
            if "ANCIEN" not in action.blocs:
                return Resultat(
                    False, "Il manque le bloc ANCIEN: … FIN, le passage exact a remplacer.")
            return self._via_github(
                "remplacer_dans_fichier",
                depot=depot,
                chemin=chemin,
                branche=branche,
                sha_attendu=champs.get("SHA", ""),
                ancien=action.blocs["ANCIEN"],
                nouveau=action.blocs.get("NOUVEAU", ""),
                message=champs.get("MESSAGE", ""),
            )
        if action.nom == "ouvrir_pr":
            depot, tete = champs.get("DEPOT") or self.depot_github_defaut, champs.get("TETE", "")
            if not depot or not tete:
                return Resultat(False, "Il manque DEPOT (owner/repo) ou TETE (la branche source).")
            return self._via_github(
                "creer_pull_request", depot=depot, titre=champs.get("TITRE", "Sans titre"),
                tete=tete, base=champs.get("BASE") or "main", corps=action.contenu)
        if action.nom == "etat_ci":
            depot, ref = champs.get("DEPOT") or self.depot_github_defaut, champs.get("REF", "")
            if not depot or not ref:
                return Resultat(False, "Il manque DEPOT (owner/repo) ou REF (SHA ou branche).")
            return self._via_github("etat_ci", depot=depot, ref=ref)
        if action.nom == "commentaires_pr":
            depot = champs.get("DEPOT") or self.depot_github_defaut
            numero_brut = champs.get("NUMERO", "").strip()
            if not depot or not numero_brut.isdigit():
                return Resultat(False, "Il manque DEPOT (owner/repo) ou NUMERO de PR valide.")
            return self._via_github(
                "commentaires_pr", depot=depot, numero=int(numero_brut))
        if action.nom == "convertir":
            chemin, format_cible = champs.get("CHEMIN", ""), champs.get("FORMAT", "")
            if not chemin or not format_cible:
                return Resultat(False, "Il manque CHEMIN (le fichier a convertir) ou "
                                       "FORMAT (l'extension cible, sans le point).")
            return self._via_file_conversion(
                "convertir", entree=chemin, format_cible=format_cible)
        if action.nom == "organiser_inspecter":
            return self._via_file_organization(
                "inspecter", dossier=champs.get("DOSSIER", "."), avec_contenu=True)
        if action.nom == "organiser_planifier":
            operations = self._lire_operations(action.contenu)
            if operations is None:
                return Resultat(False, "Il manque le bloc CONTENU: … FIN avec au moins une "
                                       "ligne `type|source|destination|raison`.")
            return self._via_file_organization(
                "planifier", dossier=champs.get("DOSSIER", "."), operations=operations)
        if action.nom == "organiser_appliquer":
            plan_id = champs.get("PLAN_ID", "")
            if not plan_id:
                return Resultat(False, "Il manque PLAN_ID — l'identifiant rendu par organiser_planifier.")
            confirmer_suppression = champs.get("CONFIRMER_SUPPRESSION", "").strip().lower() in (
                "oui", "true", "yes")
            return self._via_file_organization(
                "appliquer", plan_id=plan_id, confirmer_suppression=confirmer_suppression)
        if action.nom == "organiser_annuler":
            plan_id = champs.get("PLAN_ID", "")
            if not plan_id:
                return Resultat(False, "Il manque PLAN_ID — l'identifiant d'un plan deja applique.")
            return self._via_file_organization("annuler", plan_id=plan_id)
        if action.nom == "pdf_fusionner":
            fichiers = self._lire_fichiers(action.contenu)
            if fichiers is None:
                return Resultat(False, "Il manque le bloc CONTENU: … FIN avec un chemin de fichier par ligne.")
            format_pdfx = champs.get("FORMAT_PDFX", "").strip().lower() in ("oui", "true", "yes")
            return self._via_pdf("fusionner", fichiers=fichiers, titre=champs.get("TITRE", ""),
                                 format_pdfx=format_pdfx)
        if action.nom == "pdf_demonter":
            chemin = champs.get("CHEMIN", "")
            if not chemin:
                return Resultat(False, "Il manque CHEMIN — le fichier PDF/PDFx à démonter.")
            return self._via_pdf("demonter", fichier=chemin)
        if action.nom == "pdf_pages":
            chemin, operation = champs.get("CHEMIN", ""), champs.get("OPERATION", "")
            pages = self._lire_pages(champs.get("PAGES", ""))
            if not chemin or operation not in (
                    "reordonner", "supprimer_pages", "extraire_pages", "pivoter_pages"):
                return Resultat(False, "Il manque CHEMIN, ou OPERATION n'est pas l'une de : "
                                       "reordonner, supprimer_pages, extraire_pages, pivoter_pages.")
            if pages is None:
                return Resultat(False, "Il manque PAGES — une liste d'index séparés par des virgules, à partir de 0.")
            champ_pages = "ordre" if operation == "reordonner" else "pages"
            parametres_pdf = {"fichier": chemin, champ_pages: pages}
            if operation == "pivoter_pages":
                try:
                    parametres_pdf["degres"] = int(champs.get("DEGRES", "90"))
                except ValueError:
                    return Resultat(False, "DEGRES doit être un nombre (multiple de 90).")
            return self._via_pdf(operation, **parametres_pdf)
        if action.nom == "pdf_extraire_texte":
            chemin = champs.get("CHEMIN", "")
            if not chemin:
                return Resultat(False, "Il manque CHEMIN — le fichier PDF à lire.")
            return self._via_pdf("extraire_texte", fichier=chemin)
        # `executer` : la ligne devient une LISTE d'arguments. Ce n'est pas une
        # restriction de ce qu'il peut lancer — c'est ce qui empeche un nom de
        # fichier contenant une espace ou un `;` de devenir deux commandes.
        ligne = champs.get("COMMANDE", "")
        try:
            morceaux = shlex.split(ligne)
        except ValueError as erreur:
            return Resultat(False, f"Commande illisible ({erreur}) : {ligne}")
        return self.atelier.executer(morceaux, dossier=champs.get("DOSSIER") or None)

    # --- La boucle -------------------------------------------------------------------

    async def run(self, user_input: str, context: Optional[Dict[str, Any]] = None
                  ) -> Dict[str, Any]:
        """Travaille jusqu'à ce que ce soit fait, puis rend ce qui s'est passé."""
        if not await self.provider.is_available():
            # Sans modele, il n'y a pas de travail a rapporter. Le dire est la
            # seule reponse honnete : un compte-rendu vide se lirait comme un
            # travail termine.
            return {
                "status": "NOT_CONFIGURED",
                "agent": self.name,
                "actions": [],
                "response": (
                    "Dioumtoukay ne peut pas travailler : aucun moteur n'est "
                    "joignable. Il faut lancer Ollama sur ton PC (`ollama serve`) "
                    "ou configurer un service distant."
                ),
            }

        # Le mode d espace de travail est mesure UNE fois. Sur Railway, les
        # fichiers de /app sont une image de deploiement, pas un checkout Git.
        github_distant = self._workspace_github_distant()
        reperes = self._reperes(user_input, github_distant=github_distant)

        # La methode d'un specialiste (`debugging`/`tests`/`architecture`...,
        # `core/specialistes/catalogue.py`) n'atteignait jamais Dioumtoukay :
        # ATELIER etait meme absent de l'audit qui verifie que chaque
        # intention utile a une methode ou une raison ecrite. Calculee une
        # fois, comme les reperes : la demande ne change pas en cours de
        # travail.
        methode = bloc_de_methode(choisir(user_input, "ATELIER"))
        base_consigne = CONSIGNE_GITHUB_DISTANT if github_distant else CONSIGNE
        consigne = f"{base_consigne}\n\n{PROTOCOLE_QUALITE}"
        if methode:
            consigne += f"\n\n{methode}"

        # Une tache interrompue reprend ici, avec ses etapes deja faites en
        # guise de journal de depart : le modele voit ce qui a tourne et
        # enchaine, au lieu de relire et rechercher ce qu'il avait deja lu.
        tache = self.reprises.ouvrir(user_input)
        journal_du_travail: List[str] = list(tache.deja_fait())
        reprise = bool(journal_du_travail)
        # Vue structuree des etapes d'un passage precedent. Le journal texte
        # suffit au modele, mais pas aux gardes de preuve : apres un redemarrage,
        # ils doivent encore savoir QUEL fichier/branche a ete modifie puis
        # verifie, au lieu de repartir avec un tableau `rendu` vide.
        rendu_precedent: List[Dict[str, Any]] = (
            tache.actions_confirmees() if reprise else []
        )
        if reprise:
            logger.info("Reprise de la tache %s : %d etapes deja faites.",
                        tache.identifiant, len(journal_du_travail))
        rendu: List[Dict[str, Any]] = []
        conclusion = ""
        arrete_par_lui_meme = False
        debut = time.monotonic()
        illisibles_consecutives = 0
        derniere_signature: Optional[tuple] = None
        repetitions_consecutives = 0
        derniere_observation_suivi: Optional[tuple] = None
        repetitions_suivi_inchange = 0
        echecs_consecutifs = 0
        terminaisons_sans_verification = 0

        tours_max = TOURS_MAX_GITHUB_DISTANT if github_distant else TOURS_MAX

        for tour in range(1, tours_max + 1):
            ecoule = time.monotonic() - debut
            if ecoule >= DUREE_MAX_SECONDES:
                conclusion = (
                    f"Arrete apres {int(ecoule // 60)} minutes sans avoir conclu. "
                    "Ce qui a ete fait est ci-dessous ; la suite reste a faire.")
                break

            invite = self._invite(reperes, user_input, journal_du_travail)
            try:
                reponse = await self.provider.generate(prompt=invite, system_prompt=consigne)
            except Exception as erreur:  # noqa: BLE001 — l'echec se nomme
                logger.warning("Dioumtoukay : le moteur n'a pas repondu : %s", erreur)
                conclusion = f"Le moteur n'a pas repondu au tour {tour} : {erreur}"
                break

            action = analyser_action(reponse)
            if action is None:
                illisibles_consecutives += 1
                journal_du_travail.append(
                    "Reponse illisible : il faut UNE action au format demande.")
                if illisibles_consecutives >= ILLISIBLES_CONSECUTIVES_MAX:
                    conclusion = (
                        f"Arrete apres {illisibles_consecutives} reponses illisibles "
                        "d'affilee : le moteur ne produit pas le format demande.")
                    break
                continue
            illisibles_consecutives = 0

            if action.nom == "terminer":
                mutations = self._mutations_non_verifiees(rendu_precedent + rendu)
                if mutations:
                    terminaisons_sans_verification += 1
                    cibles = []
                    for mutation in mutations[:5]:
                        champs_mutation = mutation.get("champs") or {}
                        cible = (
                            champs_mutation.get("CHEMIN")
                            or champs_mutation.get("DESTINATION")
                            or "la modification"
                        )
                        cibles.append(f"{mutation['action']} sur {cible}")
                    suffixe = (
                        f" (+{len(mutations) - 5} autre(s))"
                        if len(mutations) > 5 else ""
                    )
                    journal_du_travail.append(
                        "VERIFICATION OBLIGATOIRE : "
                        f"{len(mutations)} mutation(s) reussie(s) n'ont encore aucune "
                        "preuve pertinente executee apres elles : "
                        + "; ".join(cibles) + suffixe
                        + ". Utilise une verification qui couvre reellement chacune "
                        "avant de terminer (relecture ciblee, diff, tests ou CI verte)."
                    )
                    if terminaisons_sans_verification >= 2:
                        conclusion = (
                            "Arrete : le moteur essaie de conclure alors que "
                            f"{len(mutations)} modification(s) restent non verifiees. "
                            "Les changements ont ete faits, mais ils ne sont pas tous prouves."
                        )
                        break
                    continue
                conclusion = action.contenu.strip() or reponse.strip()
                arrete_par_lui_meme = True
                break

            # Garde anti-repetition. Pour une action ordinaire, la MEME action
            # est bloquee avant d'etre rejouee une fois de trop. Pour une
            # action de suivi (CI / ordinateur distant), l'appel identique est
            # legitime tant que le RESULTAT evolue ; son garde est applique
            # apres l'execution, sur l'observation reelle.
            signature = action.signature()
            if action.nom in ACTIONS_DE_SUIVI_EVOLUTIF:
                derniere_signature = None
                repetitions_consecutives = 0
            else:
                derniere_observation_suivi = None
                repetitions_suivi_inchange = 0
                if signature == derniere_signature:
                    repetitions_consecutives += 1
                else:
                    repetitions_consecutives = 1
                    derniere_signature = signature
                if repetitions_consecutives >= ACTIONS_IDENTIQUES_CONSECUTIVES_MAX:
                    conclusion = (
                        f"Arrete apres {repetitions_consecutives} '{action.nom}' identiques "
                        "d'affilee : ca ne changera rien de la rejouer. Ce qui a ete fait "
                        "est ci-dessous ; la suite reste a faire.")
                    break

            # Amorcee AVANT que l'action ne tourne, pas apres : une tache tuee
            # PENDANT l'ecriture d'un fichier ou une commande longue doit
            # laisser la preuve qu'elle a ete TENTEE, jamais un journal muet
            # qui laisserait croire qu'elle n'a jamais commence (mission
            # ARENA x TRANS4MERS §14 « write-ahead state » / §47).
            cible = str(action.champs.get("CHEMIN") or action.champs.get("MOTIF") or "")
            etape = self.reprises.amorcer(
                tache, action.nom, cible=cible, champs=action.champs)
            debut_action = time.monotonic()
            resultat = await self._executer_action(action, github_distant=github_distant)
            duree_ms = int((time.monotonic() - debut_action) * 1000)
            rendu.append({"action": action.nom, "champs": action.champs,
                          **resultat.to_dict()})
            journal_du_travail.append(self._compte_rendu(action, resultat))
            # Confirmee MAINTENANT : ce que l'action a vraiment donne remplace
            # l'amorce. Une tache tuee entre les deux lignes ci-dessus laisse
            # l'etape amorcee, non confirmee — `deja_fait()` la rapporte comme
            # ETAT INCONNU au lieu de la faire passer pour un echec ou une
            # reussite qu'elle n'a peut-etre pas eu.
            self.reprises.confirmer(
                tache, etape, ok=resultat.ok,
                resume=self._compte_rendu(action, resultat),
                duree_ms=duree_ms,
                sortie=resultat.sortie or "")

            # Les actions de suivi sont comparees APRES execution : deux appels
            # identiques dont la sortie change sont du progres, pas une boucle.
            # On ne coupe que si l'action ET l'observation restent inchangees.
            if action.nom in ACTIONS_DE_SUIVI_EVOLUTIF:
                observation = (
                    signature,
                    resultat.ok,
                    resultat.message,
                    resultat.sortie,
                    resultat.erreur,
                    resultat.code,
                )
                if observation == derniere_observation_suivi:
                    repetitions_suivi_inchange += 1
                else:
                    derniere_observation_suivi = observation
                    repetitions_suivi_inchange = 1
                if repetitions_suivi_inchange >= ACTIONS_IDENTIQUES_CONSECUTIVES_MAX:
                    conclusion = (
                        f"Arrete apres {repetitions_suivi_inchange} observations "
                        f"identiques de '{action.nom}' : l'etat externe n'evolue plus. "
                        "Ce qui a ete fait est ci-dessous ; la suite reste a faire.")
                    break

            # Garde anti-echecs : la meme garantie que ci-dessus, mais pour une
            # action qui CHANGE a chaque tour tout en echouant a chaque fois.
            # La derniere tentative reste dans `rendu` : rien n'est cache.
            if resultat.ok:
                echecs_consecutifs = 0
            else:
                echecs_consecutifs += 1
                if echecs_consecutifs >= ECHECS_CONSECUTIFS_MAX:
                    conclusion = (
                        f"Arrete apres {echecs_consecutifs} echecs d'execution "
                        "d'affilee : cette approche ne marche pas. Ce qui a ete "
                        "fait est ci-dessous ; la suite reste a faire.")
                    break

        if not arrete_par_lui_meme and not conclusion:
            # La borne est atteinte. Le dire : un rapport qui s'arrete sans
            # raison se lit comme un travail fini.
            conclusion = (
                f"Arrete apres {tours_max} actions sans avoir conclu. "
                "Ce qui a ete fait est ci-dessous ; la suite reste a faire."
            )

        self._retenir(user_input, conclusion, rendu)

        # Terminee, ou interrompue donc REPRENABLE. C'est cette distinction qui
        # fait la difference entre « la suite reste a faire » (une phrase) et
        # « la suite reprendra ici » (un etat).
        if arrete_par_lui_meme:
            self.reprises.terminer(tache, conclusion)
        else:
            self.reprises.interrompre(tache, conclusion)

        return {
            "status": "success" if arrete_par_lui_meme else "partial",
            "agent": self.name,
            "moteur": self._moteur_utilise(),
            "actions": rendu,
            "fichiers_modifies": self.fichiers_touches(rendu),
            "response": self._rapport(
                conclusion, rendu, termine=arrete_par_lui_meme),
            "tache": tache.journal(),
            "reprise": reprise,
        }

    # --- Ce qu'il voit, et ce qu'il rend ---------------------------------------------

    def _reperes(self, demande: str, github_distant: Optional[bool] = None) -> str:
        """Où il est, et ce qu'il y a autour. Mesuré, jamais supposé.

        Sans ça, le premier tour partait à l'aveugle : le modèle dépensait deux
        ou trois actions à découvrir un dossier qu'une seule mesure lui donne.
        Sur douze tours, deux tours perdus au départ comptent.

        Rien n'est inventé ici : un dépôt git absent ne produit aucune ligne,
        et l'absence se lit comme une absence.
        """
        lignes = [f"Racine du travail : {self.atelier.racine}"]
        if self.depot_github_defaut:
            lignes.append(
                "Depot GitHub distant par defaut : "
                f"{self.depot_github_defaut}. Les actions github_* travaillent "
                "sur ce depot sans dependre du disque de cette machine."
            )

        if github_distant is None:
            github_distant = self._workspace_github_distant()

        if github_distant:
            lignes.append(
                "AUCUN checkout git local dans cette execution. Mode GitHub distant ACTIF : "
                "github_lister, github_lire, github_chercher, github_branche_creer et "
                "github_ecrire travaillent sur le depot durable. Les fichiers de /app "
                "sont seulement l image de deploiement et ne sont pas le workspace Git."
            )
        else:
            branche = self.atelier.executer(["git", "rev-parse", "--abbrev-ref", "HEAD"])
            if branche.ok:
                lignes.append(f"Depot git, sur la branche : {branche.sortie.strip()}")
                etat = self.atelier.executer(["git", "status", "--short"])
                if etat.ok:
                    modifies = etat.sortie.strip()
                    lignes.append("Fichiers modifies non commites :\n" + modifies
                                  if modifies else "Aucun fichier modifie.")

        if not github_distant:
            autour = self.atelier.lister(".")
            if autour.ok:
                lignes.append("Ce que contient la racine :\n" + autour.sortie)

        # Mission ARENA x OPENCONTEXT (10/09/2026) : avant, seuls la racine,
        # la branche et le contenu du dossier etaient mesures ici -- jamais
        # PROJECT_MEMORY/, que CLAUDE.md demande a un humain de lire en
        # premier. `instantane()` ne lit que des fichiers deja ecrits, ne
        # remplace aucune memoire existante, et rend une chaine vide si
        # `self.atelier.racine` n'a ni PROJECT_MEMORY/ ni docs/DECISIONS.md
        # (un autre projet, ou le tmp_path d'un test) -- jamais invente.
        etat_projet = instantane(self.atelier.racine)
        if not etat_projet.vide:
            lignes.append(etat_projet.texte)

        # Mission ARENA x AUTOSKILLS (10/09/2026) : avant, Dioumtoukay recevait
        # soit rien du tout sur la pile technique du projet, soit (via
        # `analyser`) tout le depot d'un coup. `instantane_competences()`
        # detecte les technologies REELLEMENT presentes (jamais devinees),
        # et ne retient que les competences que LA DEMANDE appelle vraiment
        # -- zero si rien ne correspond, jamais un catalogue entier pose
        # dans le prompt par reflexe (mission §5, §7).
        bloc_competences = instantane_competences(self.atelier.racine, demande)
        if bloc_competences:
            lignes.append(bloc_competences)

        return "\n".join(lignes)

    @staticmethod
    def _preuve_positive(
        mutation: Dict[str, Any], verification: Dict[str, Any]
    ) -> bool:
        """Une verification qui prouve CETTE mutation, pas juste une action verte.

        Avant ce garde, lire n'importe quel autre fichier — ou demander une CI
        encore rouge — suffisait a deverrouiller `terminer`. C'etait une preuve
        de quelque chose, mais pas de la modification que l'agent venait de faire.
        """
        if not verification.get("ok"):
            return False
        action = verification.get("action")
        if action not in ACTIONS_DE_VERIFICATION:
            return False

        champs_mutation = mutation.get("champs") or {}
        champs_verif = verification.get("champs") or {}
        cible = champs_mutation.get("CHEMIN") or champs_mutation.get("DESTINATION") or ""
        sortie = str(verification.get("sortie") or "")

        # Une CI lue avec succes n'est positive que si son VERDICT est vert.
        if action == "etat_ci":
            if not re.search(r"(?m)^resume:\s*succes\s*$", sortie):
                return False
            branche = champs_mutation.get("BRANCHE", "")
            ref = champs_verif.get("REF", "")
            return not branche or not ref or branche == ref

        if mutation.get("action") in {"github_ecrire", "github_remplacer"}:
            branche = champs_mutation.get("BRANCHE", "")
            if action == "github_lire":
                return (
                    bool(cible)
                    and champs_verif.get("CHEMIN") == cible
                    and champs_verif.get("REF") == branche
                )
            if action == "github_diff":
                return (
                    bool(branche)
                    and champs_verif.get("TETE") == branche
                    and (not cible or cible in sortie)
                )
            return False

        if mutation.get("action") == "ordinateur_ecrire_fichier":
            if action == "ordinateur_lire_fichier":
                return (
                    champs_verif.get("COMPUTER_ID") == champs_mutation.get("COMPUTER_ID")
                    and champs_verif.get("CHEMIN") == cible
                )
            return action == "ordinateur_executer"

        if mutation.get("action") == "deplacer":
            destination = champs_mutation.get("DESTINATION", "")
            if action == "lire":
                return bool(destination) and champs_verif.get("CHEMIN") == destination
            if action == "lister":
                dossier = champs_verif.get("CHEMIN", ".").rstrip("/")
                return bool(destination) and (
                    dossier in ("", ".") or destination.startswith(dossier + "/")
                )

        # Fichier local : relire le meme fichier, regarder son diff/statut ou
        # executer une vraie commande de test sont des preuves observables.
        if mutation.get("action") in {"ecrire", "remplacer"}:
            if action == "lire":
                return bool(cible) and champs_verif.get("CHEMIN") == cible
            if action == "git_diff":
                chemin_diff = champs_verif.get("CHEMIN", "")
                return not chemin_diff or chemin_diff == cible
            return action in {"git_statut", "executer"}

        return action in {"executer", "git_diff", "git_statut", "ordinateur_executer"}

    @classmethod
    def _mutations_non_verifiees(
        cls, rendu: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Toutes les mutations reussies qui n'ont pas encore de preuve pertinente.

        Verifier seulement la DERNIERE mutation laissait un trou important :
        modifier A puis B, relire uniquement B, et conclure rendait A invisible.
        Une preuve globale (tests, diff GitHub, CI verte) peut naturellement
        couvrir plusieurs mutations ; une simple relecture ne couvre que sa cible.
        """
        non_verifiees: List[Dict[str, Any]] = []
        for index, mutation in enumerate(rendu):
            if not mutation.get("ok") or mutation.get("action") not in ACTIONS_A_VERIFIER:
                continue
            verifiee = any(
                cls._preuve_positive(mutation, acte)
                for acte in rendu[index + 1:]
            )
            if not verifiee:
                non_verifiees.append(mutation)
        return non_verifiees

    @classmethod
    def _mutation_non_verifiee(
        cls, rendu: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Compatibilite interne : la premiere mutation encore sans preuve."""
        non_verifiees = cls._mutations_non_verifiees(rendu)
        return non_verifiees[0] if non_verifiees else None

    @staticmethod
    def _journal_pour_modele(journal_du_travail: List[str]) -> str:
        """Contexte borne : recent complet, ancien resume.

        Le journal durable n'est jamais tronque. Seule la COPIE remise au
        modele a chaque tour est compacte pour eviter qu'une longue tache
        repaye tous ses octets a chaque appel cloud.
        """
        if not journal_du_travail:
            return ""
        complet = "\n\n".join(journal_du_travail)
        if len(complet) <= JOURNAL_MODELE_MAX_CARACTERES:
            return complet

        budget_recent = JOURNAL_MODELE_MAX_CARACTERES - JOURNAL_MODELE_RESUME_MAX_CARACTERES
        recentes_inversees: List[str] = []
        utilises = 0
        index_premiere_recente = len(journal_du_travail)
        for index in range(len(journal_du_travail) - 1, -1, -1):
            etape = journal_du_travail[index]
            cout = len(etape) + 2
            if recentes_inversees and utilises + cout > budget_recent:
                break
            recentes_inversees.append(etape)
            utilises += cout
            index_premiere_recente = index

        anciennes = journal_du_travail[:index_premiere_recente]
        resumes = []
        caracteres = 0
        for etape in anciennes:
            premiere = (etape.splitlines() or [""])[0].strip()
            if not premiere:
                continue
            ligne = f"- {premiere}"
            if caracteres + len(ligne) + 1 > JOURNAL_MODELE_RESUME_MAX_CARACTERES:
                resumes.append("- ... etapes plus anciennes omises du contexte actif ...")
                break
            resumes.append(ligne)
            caracteres += len(ligne) + 1

        blocs = []
        if resumes:
            blocs.append("Etapes plus anciennes (resumees) :\n" + "\n".join(resumes))
        blocs.append("Etapes recentes (sortie complete) :\n"
                     + "\n\n".join(reversed(recentes_inversees)))
        return "\n\n".join(blocs)

    @classmethod
    def _invite(cls, reperes: str, demande: str, journal_du_travail: List[str]) -> str:
        """La demande, plus un contexte de travail borne et factuel."""
        blocs = [reperes, f"Demande du proprietaire : {demande}"]
        journal = cls._journal_pour_modele(journal_du_travail)
        if journal:
            blocs.append("Ce qui s'est passe jusqu'ici :\n" + journal)
        blocs.append("Action suivante :")
        return "\n\n".join(blocs)

    @staticmethod
    def _compte_rendu(action: Action, resultat: Resultat) -> str:
        """Ce que l'action a vraiment donné, tel quel — jamais résumé."""
        lignes = [f"> ACTION {action.nom} : {resultat.message}"]
        if resultat.sortie:
            lignes.append(f"SORTIE:\n{resultat.sortie}")
        if resultat.erreur:
            lignes.append(f"ERREUR:\n{resultat.erreur}")
        return "\n".join(lignes)

    @staticmethod
    def fichiers_touches(rendu: List[Dict[str, Any]]) -> List[str]:
        """Les fichiers réellement modifiés, localement ou sur GitHub.

        Une action tentée puis échouée ne compte pas : dire « fichier modifié »
        d'un fichier intact serait la pire ligne du rapport. Pour github_ecrire,
        ok signifie que GitHub a rendu un commit : la modification distante est
        donc aussi une preuve réelle, pas une intention.
        """
        touches = []
        for acte in rendu:
            if not acte["ok"] or acte["action"] not in ACTIONS_QUI_MODIFIENT:
                continue
            champs = acte.get("champs") or {}
            ou = champs.get("CHEMIN") or champs.get("DESTINATION")
            if ou and ou not in touches:
                touches.append(ou)
        return touches

    @staticmethod
    def _sortie_pour_rapport(acte: Dict[str, Any], limite: int = 6_000) -> str:
        """Preuve lisible pour l'humain, jamais un dump de structure interne."""
        sortie = str(acte.get("sortie") or "").strip()
        if not sortie:
            return ""
        if len(sortie) <= limite:
            return sortie
        moitie = limite // 2
        manque = len(sortie) - limite
        return (sortie[:moitie]
                + f"\n[… {manque} caracteres techniques masques …]\n"
                + sortie[-moitie:])

    @classmethod
    def _rapport(
        cls, conclusion: str, rendu: List[Dict[str, Any]], *, termine: bool = True
    ) -> str:
        """Compte-rendu humain : resultat d'abord, preuves ensuite.

        La trace complete reste dans `actions` et le journal durable. La bulle
        de chat n'est pas un log : elle ne doit pas commencer par des SHA,
        tailles ou repr Python avant de dire ce qui a ete obtenu.
        """
        parties: List[str] = []
        conclusion_propre = (conclusion or "").strip()
        if conclusion_propre:
            parties.append(conclusion_propre)

        touches = cls.fichiers_touches(rendu)
        if touches:
            parties.append(
                "**Fichiers modifiés**\n"
                + "\n".join(f"- `{chemin}`" for chemin in touches)
            )

        echecs = [a for a in rendu if not a.get("ok")]
        if echecs:
            parties.append(
                "**À corriger**\n"
                + "\n".join(
                    f"- `{a.get('action', '?')}` — {a.get('message', 'échec')}"
                    for a in echecs
                )
            )

        preuves = []
        for acte in rendu:
            if not acte.get("ok") or acte.get("action") not in ACTIONS_QUI_ANALYSENT:
                continue
            sortie = cls._sortie_pour_rapport(acte)
            if sortie:
                preuves.append(f"**{acte['action']}**\n{sortie}")
        # Une lecture/listing est deja digeree dans la conclusion par le
        # modele. On ne la recopie que si le modele n'a PAS pu conclure (429,
        # coupure, limite de tours) afin de ne pas perdre la preuve obtenue.
        if not termine:
            for acte in rendu:
                if (not acte.get("ok")
                        or acte.get("action") not in ACTIONS_PREUVES_DE_REPLI):
                    continue
                sortie = cls._sortie_pour_rapport(acte)
                if sortie:
                    preuves.append(f"**Résultat disponible**\n{sortie}")

        if preuves:
            parties.append("**Résultats vérifiés**\n\n" + "\n\n".join(preuves))

        # Une lecture simple reussie n'a pas besoin d'une ligne administrative
        # « 1 action, aucune en echec ». Le statut redevient utile quand il y a
        # eu plusieurs etapes, une mutation ou un echec.
        if rendu and (len(rendu) > 1 or touches or echecs):
            succes = sum(1 for acte in rendu if acte.get("ok"))
            statut = (
                f"{succes}/{len(rendu)} action(s) exécutée(s) avec succès, "
                f"{len(echecs)} en echec"
                if echecs else f"{len(rendu)} action(s) exécutée(s), aucune en échec"
            )
            parties.append(f"*Vérification : {statut}.*")

        return "\n\n".join(parties).strip()

    def _moteur_utilise(self) -> Dict[str, Any]:
        """Le fournisseur qui a reellement servi CE Dioumtoukay.

        La passerelle PWA utilisait historiquement le fournisseur du chat
        rapide pour toutes les reponses specialisees. Dioumtoukay utilise le
        routeur codeur : annoncer le fast provider donnait « local/qwen » alors
        que les logs montraient Groq. On remonte donc la mesure du provider qui
        a effectivement produit les actions de cette tache.
        """
        fournisseur = getattr(self.provider, "fournisseur_en_service", None)
        modele = getattr(self.provider, "model_name", None)
        choix = getattr(self.provider, "dernier_choix", None)
        meta: Dict[str, Any] = {}
        if fournisseur:
            meta["provider"] = fournisseur
        if modele:
            meta["model"] = modele
        raison = getattr(choix, "raison", "") if choix is not None else ""
        if raison:
            meta["raison"] = raison
        return meta

    def _retenir(self, demande: str, conclusion: str, rendu: List[Dict[str, Any]]) -> None:
        """Garde une trace de ce travail dans la mémoire longue.

        Le journal dit ce qui a tourné, action par action ; la mémoire retient
        ce qui a été fait et pourquoi, pour que « reprends ce que tu faisais
        hier sur mon site » veuille dire quelque chose. Elle ne retient un
        travail que s'il a **modifié** quelque chose : se souvenir d'une lecture
        ne sert personne.

        Ne lève jamais : une mémoire en panne ne doit pas emporter le rapport.
        """
        touches = self.fichiers_touches(rendu)
        if self.memoire_longue is None or not touches:
            return
        try:
            retenir_l_echange(
                self.memoire_longue,
                f"[Dioumtoukay] {demande}",
                f"Fichiers modifies : {', '.join(touches)}. {conclusion}".strip(),
                source=f"travail de Dioumtoukay du {date.today().isoformat()}")
        except Exception as erreur:  # noqa: BLE001 — le rapport passe avant la memoire
            logger.warning("Travail non retenu en memoire : %s", erreur)
