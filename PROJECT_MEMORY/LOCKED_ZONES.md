# ZONES VERROUILLÉES — ne pas remanier sans raison

*Mise à jour : 2026-08-28.*

Un système verrouillé n'est pas intouchable : il est **protégé**. On ne le
réécrit pas, on ne le renomme pas, on ne le « améliore » pas parce qu'on
préférerait une autre implémentation.

## Quand on a le droit d'y toucher

1. la tâche en cours en dépend directement ;
2. une intégration l'exige ;
3. un bug confirmé existe ;
4. un test montre qu'il est affecté ;
5. une API dont il dépend a changé ;
6. **le propriétaire le demande**.

Même alors : chercher le plus petit changement possible, et adapter le nouveau
système autour du stable plutôt que l'inverse.

---

## Verrouillés

| Zone | Pourquoi | Ce qui casse si on y touche |
|---|---|---|
| `core/actions/resultat.py` | 7 statuts, invariant « pas de succès sans preuve » | **tous** les connecteurs, et la garantie centrale du projet |
| `core/actions/journal.py` | 9 champs, masquage des secrets | la traçabilité, et le suivi vidéo qui y lit l'identifiant |
| `core/actions/attente.py` | confirmer deux fois n'exécute qu'une fois | l'e-mail, le devis PDF, l'agenda, la génération vidéo |
| `core/permissions/` + `config/permissions*.yaml` | deux couches, la plus stricte gagne | **toutes** les confirmations. Un `ALLOWED` de trop et un e-mail part seul |
| `core/connectors/base.py` | l'ordre contrôle → confirmation → santé → quota → **crochets** (DEC-0013, ajoutés APRÈS, jamais avant) → exécution | l'impossibilité structurelle d'envoyer sans demander |
| `core/security/trust.py` | frontière donnée / consigne | la protection contre un e-mail ou un document hostile |
| `config/metier.yaml` | **ses prix réels**, tirés de ses devis | un devis faux part chez un client |
| `agents/plaquiste/calcul_materiaux.py` | vérifié contre le devis `UC-2026-0804-FG2` | ses quantités |
| `core/memory/personnelle.py` | schéma SQLite + migration qui n'efface rien | ses souvenirs, définitivement |

## Ne pas toucher pour une autre raison

| Zone | Raison |
|---|---|
| `apps/pwa/` (dist compilé) | son interface ; **jamais regardée par l'assistant** — on ne modifie pas à l'aveugle ce qu'on ne peut pas voir |
| `tests/` marqués `integration` | ils décrivent ce qui doit être vérifié chez lui. Ne pas les affaiblir pour les faire passer |

## Interdits permanents (CLAUDE.md, non négociables)

- jamais de secret, jamais de `.env` versionné ;
- jamais de push direct sur `master` — branche + pull request ;
- jamais un `[OK]`, un `SUCCESS` ou un chiffre qui n'a pas été mesuré ;
- jamais désactiver ou affaiblir un test pour obtenir du vert.
