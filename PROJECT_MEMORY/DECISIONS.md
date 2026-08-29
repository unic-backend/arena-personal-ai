# DÉCISIONS — index

*`docs/DECISIONS.md` reste **l'autorité**. Ce fichier est son index : il évite
d'ouvrir le document entier quand on cherche juste « a-t-on déjà tranché ça ? ».*

*Mise à jour : 2026-08-28.*

| # | Décision | Conséquence opérationnelle |
|---|---|---|
| **DEC-0001** | arborescence unifiée dès la phase 0 | ne pas réorganiser les dossiers |
| **DEC-0002** | local-first strict — **amendée par DEC-0009** | vaut toujours pour les services tiers qu'on intègre (leur `llm_provider` doit être `ollama`) ; pour ARENA lui-même, lire DEC-0009 |
| **DEC-0003** | sécurité des publications | rien ne se publie sans confirmation |
| **DEC-0004** | **sans bac à sable, l'exécution de code est refusée** | Docker absent ⇒ ARENA refuse, il ne dégrade pas |
| **DEC-0005** | licence propriétaire | pas d'ouverture du code |
| **DEC-0006** | GalsenAPI est la source des données du Sénégal | l'attribution voyage avec **chaque** chiffre |
| **DEC-0007** | **LibreChat et Open WebUI retirés** | 4 des 5 clés fuitées sont mortes. Ne jamais les remettre — un test le tient |
| **DEC-0008** | **un projet tiers tourne À CÔTÉ** | ni son code, ni ses clés, ni ses dépendances n'entrent ici. ARENA lui parle par son API |
| **DEC-0010** | d'un dépôt de prompts, on extrait la **méthode** | les règles deviennent du code qui compte ; les fichiers ne sont pas copiés |
| **DEC-0011** | **`grok-bot-0.18-reconstructed` refusé** | aucune licence, code extrait de binaires propriétaires. Le manque réel (état d'une tâche multi-étapes) est écrit sans emprunt |
| **DEC-0009** | **ARENA devient hybride — DEC-0002 amendée** | rien de **sensible** ne part au cloud ; un secret ne sort **jamais** ; Ollama reste défaut et repli ; `AI_LOCAL_ONLY=true` referme tout |
| **DEC-0012** | **OpenTakeoff — métré de plan PDF, à côté** | second transport MCP (stdio, `core/mcp/stdio_transport.py`) ; sous-ensemble réel des outils (rien qui devine une coordonnée) ; un périmètre de pièce n'est jamais présenté comme une surface de cloisons |
| **DEC-0013** | **DeepSeek Harness — crochets, pas Cordis** | `core/execution/hooks.py` (avant/après exécution, ajoutés apres les 4 contrôles verrouillés) + `core/execution/disjoncteur.py` (coupe court après des échecs consécutifs réels) ; Cordis (bus de plugins entier) refusé — résout un problème qu'ARENA n'a pas |
| **DEC-0014** | **Live-SWE-agent — aucun code d'agent, gardien construit à côté** | `core/guardian/` (diagnostics + file de maintenance persistante + cycle), `GET/POST /api/gardien/*` ; aucune modification autonome du dépôt (violerait « la PR est l'endroit où il voit ce qui entre ») ; aucun travailleur distant (exige compte/budget du propriétaire) |
| **DEC-0015** | **Hell-Grind-AIGC-Skill — un auditeur de prompt, pas un moteur** | `tools/video/prompt_audit.py` (12 modules, 10 catégories de problème, méthode extraite, motifs retraduits fr/en) ; `VideoAnalyzerAgent.planifier_scene()` — premier appelant réel de `wan2gp.generer`, bloqué tant que l'audit n'est pas `pret` ; le Skill Codex et le schéma 14 tables (dimensionné pour un film) ne sont pas portés |
| **DEC-0016** | **GitHub Spec Kit — refusé, rien câblé** | son cycle « implement » signifie écrire/modifier du code de façon autonome — exactement ce que DEC-0014 a déjà refusé (« la PR est l'endroit où il voit ce qui entre ») ; « développer d'autres projets logiciels » n'est pas le métier d'ARENA ; aucun `.specify/` copié dans le dépôt |
| **DEC-0017** | **Agent-Reach — rien à intégrer, `DeepResearcherAgent` corrigé à la place** | c'est une sonde/installateur pour agent de codage (yt-dlp, feedparser, Jina Reader, Exa) — rien d'unique à récupérer ; `FreshInfoAgent` déjà le plus abouti (parallèle, sourcé, jamais inventé) ; vrai défaut trouvé et corrigé : `DeepResearcherAgent` lançait ses 3 recherches en séquence, maintenant en parallèle (`asyncio.gather`) |
| **DEC-0018** | **Consolidation des modèles — rien à fusionner** | inventaire réel : 1 modèle par groupe (léger/profond = paliers de coût documentés dans `voies.py`, pas des doublons ; Groq/DeepInfra = repli infrastructurel, pas des intelligences redondantes ; `CoderAgent` utilise déjà le modèle léger, groupes A et B déjà partagés) ; aucune vision, aucun modèle vidéo possédé par ARENA |

## Décisions de travail (hors ADR, mais qui gouvernent autant)

| Règle | Où elle est écrite |
|---|---|
| une phase = une pull request, jamais deux dans le même tour | `docs/REGLES_DE_TRAVAIL.md` |
| il n'écrit pas de code — une commande à la fois, fichier entier | idem |
| toute garantie déclarée doit avoir été **sabotée** une fois | `CLAUDE.md` |
| une capacité absente se rapporte (`NOT_CONFIGURED`), ne se simule pas | `CLAUDE.md` |
| le dépôt est **privé** depuis le 28/08/2026 | `docs/CURRENT_TASK.md` |
