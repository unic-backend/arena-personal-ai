# Raisonnement approfondi — mode approfondie

> Mis en place le 13/09/2026. Ce document explique quand le mode approfondie se declenche, ce qu il fait, ce qu il coute, et comment le deboguer.

## En une phrase

Le mode approfondie ajoute une critique independante et, si la critique dit KO, une revision de la reponse. Il coute deux appels de modele en plus et detecte les reponses qui affirment des choses non verifiees.

## Quand se declenche-t-il ?

Automatiquement, dans apps/backend/reasoning_bridge.py, via profondeur_pour(). Deux regles deterministes, aucun appel de modele :

1. Un mot de verification dans la demande -> approfondie. Liste dans MOTS_VERIFICATION : verifie, prouve, corrige, critique, rigoureux, es-tu sur.

2. Une demande longue (>200 caracteres) -> approfondie. Une question longue porte souvent plusieurs contraintes.

Sinon : mode standard (comportement historique, deux appels de modele).

## Ce que fait chaque etape

| Etape | standard | approfondie |
|-------|----------|-------------|
| plan | oui | oui |
| calcul (bac a sable) | oui (facultatif) | oui (facultatif) |
| synthese | oui | oui |
| critique | non | oui (facultatif) |
| revision | non | oui (facultatif) |

Facultatif signifie : si l etape echoue ou rend un resultat inexploitable, la tache continue. Une critique muette ou une revision vide ne peut jamais emporter une reponse deja produite.

## Format du verdict de critique

VERDICT: OK ou KO
RAISON: une phrase courte
CONFIANCE: un nombre entre 0 et 1

Si le format n est pas respecte, ok vaut None et l etape est abandonnee silencieusement.

## L invariant deterministe (le point cle)

Un LLM suit une regle absolue la plupart du temps, pas toujours. Mesure le 13/09/2026 : deux runs identiques, une critique OK puis KO, sur le meme etat de calcul echoue.

Garde-fou dans critiquer() : si le calcul a echoue ET que la critique a dit OK, le verdict est force a KO avec force_ko=True. Le modele propose, le Python dispose.

## Ce que ca coute

| Mode | Appels modele | Temps |
|------|---------------|-------|
| standard | 2 | 5-15 s |
| approfondie (OK) | 3 | 10-20 s |
| approfondie (KO) | 4 | 15-30 s |

Le mode approfondie est plus sur, pas meilleur. Il rend une reponse honnete sur ce qui a ete verifie.

## Comment le deboguer

Verifier que le mode se declenche : chercher Raisonnement profond en mode approfondie dans les logs.

Voir le verdict : dans la reponse JSON de /api/chat, chercher critique. Les cles profondeur et critique n apparaissent pas en mode standard.

Verifier l invariant : si la reponse contient l avertissement de relecture ET que le log montre correction deterministe, le garde-fou a fonctionne.

## Fichiers concernes

| Fichier | Role |
|---------|------|
| core/reasoning/reasoning_engine.py | Moteur : critiquer(), reviser(), invariant |
| apps/backend/reasoning_bridge.py | Pont : profondeur_pour(), notes |
| apps/backend/routers/chat.py | Appel de resoudre_profondement() |
| tests/core/test_reasoning.py | Tests du moteur |
| tests/test_reasoning_bridge.py | Tests du pont |

## Decisions liees

- Opt-in strict : le mode standard reste le defaut.
- Facultatif par defaut : critique et revision sont facultative=True.
- Rien de muet : une critique inexploitable est abandonnee sans avertissement.

## Voir aussi

- core/execution/coordination.py : les six etats d une etape.
- docs/ARCHITECTURE.md : vue d ensemble.
- docs/DECISIONS.md : la decision du 13/09/2026.
