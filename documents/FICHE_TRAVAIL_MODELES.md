# Fiche de travail — deux défauts signalés par le propriétaire

**Ouverte le 2026-08-26**, sur deux constats faits par Usman en utilisant Usman
dans LibreChat. Les deux sont des régressions d'usage, pas des idées
d'amélioration.

---

## D-01 — Le menu propose dix modèles ; l'utilisateur en veut deux

### Ce qui a été observé

Le sélecteur de LibreChat affiche `arena-core`, `arena-coder`,
`arena-swe-agent`, `arena-repo-engineer`, `arena-deep-research`, `arena-fresh`,
`arena-rag-docs`, `arena-graphrag`, `arena-browser`, `arena-studio`.

Usman avait **réduit cette liste à deux entrées** dans son
`librechat.yaml`. Sa raison, dans ses mots :

> « les utilisateurs ne connaissent pas des modèles, eux ils ouvrent le premier
> modèle qui apparaît, ils travaillent sur ça, ils pensent que c'est ça qui fait
> tout ce qu'ils veulent »

### Cause racine

Ce n'est pas un bug : c'est **une décision produit du propriétaire qui a été
défaite**. En réunissant les deux branches, sa liste courte a été traitée comme
un oubli — `arena-fresh` « manquait » — et la liste longue a été rétablie, puis
**verrouillée par un test** (`test_librechat_montre_exactement_ce_que_l_api_sert`).

Le test est correct dans sa mécanique et faux dans son intention : il impose que
le menu montre tout ce que l'API sert. Or un menu n'est pas un inventaire.

### Ce qui doit être vrai à la fin

- Le menu ne propose que **`arena-core`**, **`arena-coder`** et
  **`arena-video`** — la troisième entrée demandée par le propriétaire le
  2026-08-26, après avoir constaté que les deux premières fonctionnaient.
- **Aucune capacité n'est perdue** : tout ce que les huit autres noms
  atteignaient doit être atteignable depuis `arena-core`, sans que l'utilisateur
  ait à choisir quoi que ce soit.
- Le garde-fou change d'intention : il ne vérifie plus que le menu montre tout,
  mais que **tout reste joignable**.

### Ce qui reste hors de cette fiche

Supprimer les noms d'agents de l'API. Ils restent servis par
`/v1/chat/completions` — un client averti peut toujours les appeler
directement. Ce qui change, c'est ce que le **menu** propose.

---

## D-02 — Une réponse vide est envoyée comme si c'était une réponse

### Ce qui a été observé

Sur `arena-deep-research`, une question a produit **une bulle entièrement
vide** dans LibreChat, sans texte ni message d'erreur, après environ trois
minutes d'attente.

### Cause racine

`apps/backend/routers/openai_gateway.py` construit la réponse ainsi :

```python
contenu = (await researcher_agent.run(last_user_msg)).get("response", "")
...
if contenu is not None:
    return _reponse_openai(contenu, model_requested, stream)
```

Si l'agent échoue et renvoie un dictionnaire sans clé `response`, `contenu`
devient la **chaîne vide**. Or `"" is not None` est vrai : la passerelle renvoie
donc une réponse valide au format OpenAI, dont le texte est vide.

Le neuf branches du bloc ont le même défaut.

C'est la faute que ce dépôt s'interdit ailleurs : *une capacité indisponible
rapporte son état, elle ne rend jamais un résultat plausible.* Une réponse vide
est pire qu'un message d'erreur — l'utilisateur ne sait même pas qu'il y a eu un
problème.

### Ce qui doit être vrai à la fin

- **Aucune réponse vide ne sort jamais de la passerelle.** Si un agent ne
  produit pas de texte, le message dit quel agent, et ce qui s'est passé.
- Le cas est tenu par un test, agent par agent.

### Ce qui n'est pas traité ici

Pourquoi `arena-deep-research` a mis trois minutes puis n'a rien produit. C'est
une question distincte, qui demande les journaux du serveur au moment de
l'appel. **Elle reste ouverte** — la corriger n'est pas la même chose que
cesser d'afficher du vide.


---

## Suivi

| Date | État |
|---|---|
| 2026-08-26 | D-01 et D-02 corrigés (`5bc33e9`). Menu ramené à 2 entrées, 5 intentions créées, plus aucune réponse vide. |
| 2026-08-26 | `arena-video` ajouté à la demande du propriétaire. Menu à 3 entrées. `arena-studio` reste accepté par l'API. |
| **ouvert** | **Pourquoi `arena-deep-research` met trois minutes et ne renvoie rien.** Demande les journaux du serveur au moment de l'appel. |
