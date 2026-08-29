# DÉCISIONS — index

*`docs/DECISIONS.md` reste **l'autorité**. Ce fichier est son index : il évite
d'ouvrir le document entier quand on cherche juste « a-t-on déjà tranché ça ? ».*

*Mise à jour : 2026-08-28.*

| # | Décision | Conséquence opérationnelle |
|---|---|---|
| **DEC-0001** | arborescence unifiée dès la phase 0 | ne pas réorganiser les dossiers |
| **DEC-0002** | **local-first strict** | rien ne part chez un fournisseur d'IA. Vaut aussi pour les services tiers qu'on intègre (leur `llm_provider` doit être `ollama`) |
| **DEC-0003** | sécurité des publications | rien ne se publie sans confirmation |
| **DEC-0004** | **sans bac à sable, l'exécution de code est refusée** | Docker absent ⇒ ARENA refuse, il ne dégrade pas |
| **DEC-0005** | licence propriétaire | pas d'ouverture du code |
| **DEC-0006** | GalsenAPI est la source des données du Sénégal | l'attribution voyage avec **chaque** chiffre |
| **DEC-0007** | **LibreChat et Open WebUI retirés** | 4 des 5 clés fuitées sont mortes. Ne jamais les remettre — un test le tient |
| **DEC-0008** | **un projet tiers tourne À CÔTÉ** | ni son code, ni ses clés, ni ses dépendances n'entrent ici. ARENA lui parle par son API |

## Décisions de travail (hors ADR, mais qui gouvernent autant)

| Règle | Où elle est écrite |
|---|---|
| une phase = une pull request, jamais deux dans le même tour | `docs/REGLES_DE_TRAVAIL.md` |
| il n'écrit pas de code — une commande à la fois, fichier entier | idem |
| toute garantie déclarée doit avoir été **sabotée** une fois | `CLAUDE.md` |
| une capacité absente se rapporte (`NOT_CONFIGURED`), ne se simule pas | `CLAUDE.md` |
| le dépôt est **privé** depuis le 28/08/2026 | `docs/CURRENT_TASK.md` |
