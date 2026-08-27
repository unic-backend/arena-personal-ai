/* ─────────────────────────────────────────────────────────────
   French renderings of the corpus snippets — used when the
   conversation language is French. Source titles remain in
   their original language, like real citations.
   ───────────────────────────────────────────────────────────── */

export const CORPUS_FR: Record<string, { excerpt: string; body: string[] }> = {
  d1: {
    excerpt: 'Étude de plus de 40 systèmes de raisonnement : le calcul au moment de l’inférence dépasse désormais le simple agrandissement des modèles.',
    body: [
      'La montée en charge du calcul à l’inférence a détrôné le nombre de paramètres comme moteur principal des gains en raisonnement, avec 10 à 100× plus de jetons alloués qu’en 2024.',
      'La délibération latente — calculer sans émettre de jetons — a réduit la latence moyenne de raisonnement de 3,4× dans les déploiements étudiés.',
      'Les récompenses vérifiables (compilateurs, tests unitaires, prouveurs) restent le signal d’entraînement le plus fiable.',
    ],
  },
  d2: {
    excerpt: 'Les déploiements d’agents en entreprise ont été multipliés par 5 en un an, avec des taux de réussite supérieurs à 85 % sur les workflows à étapes multiples.',
    body: [
      'Le taux médian de complétion atteint 86 % sur des workflows de plus de 10 étapes, contre 48 % début 2025, porté par l’observabilité de l’exécution et les reprises automatiques.',
      'L’architecture dominante est désormais orchestrateur + outils spécialisés avec flux d’événements explicites.',
      'Le coût par workflow a chuté d’environ 70 % en un an grâce au routage vers de petits modèles.',
    ],
  },
  d3: {
    excerpt: 'Le rappel effectif — et non la taille brute de la fenêtre — est la vraie contrainte ; les designs hybrides retrieval+attention gagnent.',
    body: [
      'Au-delà d’environ 2M jetons, la précision de rappel reste sous 60 % pour l’attention dense ; les variantes éparses dépassent 90 % à 10M jetons.',
      'Le coût de service croît de façon super-linéaire au-delà de 4M jetons, poussant vers des mémoires à étages.',
      'Consensus des praticiens : la qualité du retrieval compte plus que la taille de fenêtre au-delà de 512K jetons.',
    ],
  },
  d4: {
    excerpt: 'Le prix des API sur 12 fournisseurs : un raisonnement de qualité équivalente coûte 40× moins cher qu’en mars 2025.',
    body: [
      'Le doublement s’opère en ~6,5 mois, porté par le décodage spéculatif, la distillation et le batching.',
      'Les modèles distillés de 8–30B égalent les flagships de 2025 sur 70 % des tâches pour moins de 0,10 $ le million de jetons.',
      'L’utilisation matérielle, pas les FLOPs, est le nouveau goulot d’étranglement.',
    ],
  },
  d5: {
    excerpt: 'Les meilleurs systèmes dépassent 78 % sur SWE-bench Verified ; l’évaluation migre vers des tâches longues avec vraie CI.',
    body: [
      'Les agents de codage résolvent 78 % des tickets SWE-bench Verified, contre 52 % il y a un an, pour un coût médian de 3,80 $ par ticket.',
      'Les nouvelles évaluations couvrent toute la chaîne : environnement, builds, itérations sur les échecs de tests, diffs relisables.',
      'Les développeurs jugent 41 % des PR d’agents prêtes à fusionner sans retouche.',
    ],
  },
  d6: {
    excerpt: 'Plus de 12 000 serveurs MCP au registre public ; schémas d’outils + streaming d’événements sont devenus le standard d’interopérabilité.',
    body: [
      'Le registre public a dépassé 12 000 serveurs MCP ; les trois grands IDE et les frameworks d’agents embarquent des clients natifs.',
      'Les événements de progression structurés sur le transport streaming sont devenus la façon standard d’afficher l’exécution des outils.',
      'Le modèle de sécurité a mûri : manifestes signés et portées de capacités appliqués par les hôtes majeurs.',
    ],
  },
  d7: {
    excerpt: 'Les systèmes répondent aux questions sur des vidéos d’une heure avec 91 % de précision, au-dessus de la base humaine mesurée (87 %).',
    body: [
      'L’ancrage temporel — retrouver le passage exact qui justifie une réponse — est passé de 34 % à 82 % IoU en un an.',
      'Le co-raisonnement audio-visuel réduit le plus les erreurs sur les réunions et cours.',
      'Échecs restants : causalité physique et comptage sous occlusion.',
    ],
  },
  d8: {
    excerpt: 'Des modèles ouverts de 3B affinés sur des traces vérifiées conservent 92 % de la qualité du maître pour 1/25e du coût.',
    body: [
      'La distillation sur traces vérifiées par outils bat les logits bruts, car la propagation d’erreurs est pénalisée à l’entraînement.',
      'Les volants de données synthétiques produisent désormais 60 à 80 % des jetons des affinages compétitifs.',
      'Garde-fou : les modèles distillés héritent des angles morts du maître — les évals adversariales restent essentielles.',
    ],
  },
  d9: {
    excerpt: 'Des juges ancrés sur des rubriques avec citations comblent l’essentiel de l’écart avec les experts humains.',
    body: [
      'Les juges citant des preuves concordent avec les panels d’experts à 93 % (κ=0,81) sur la revue de code.',
      'Les biais de position et de longueur restent mesurables mais réduits d’environ 80 % par randomisation et normalisation.',
      'Problème ouvert : juger des résultats de recherche véritablement nouveaux, sans rubrique existante.',
    ],
  },
  d10: {
    excerpt: 'Des modèles vision-langage-action entraînés sur 68 morphologies transfèrent en zéro-shot vers des bras inédits avec 64 % de réussite.',
    body: [
      'Le pré-entraînement multi-embodiements atteint 64 % de succès zéro-shot sur un bras inconnu, contre 11 % pour les baselines.',
      'Des comportements de récupération conditionnés par la langue émergent sans programmation explicite au-delà de ~10^7 épisodes.',
      'Le fossé sim-réel a surtout été réduit par le rendu randomisé avec bruit de capteurs réels.',
    ],
  },
  d11: {
    excerpt: 'Les produits exposent l’état d’exécution en direct — chronologies, cartes d’outils, flux d’événements — comme surface de confiance.',
    body: [
      'Montrer l’état réel (ce qui a tourné, échoué, ou tourne) augmente mesurablement la confiance et la complétion des tâches.',
      'Le motif « chronologie d’activité » — repliable, reprenable, persistée — domine l’UX agentique.',
      'Principe clé : ne jamais afficher une opération que le système n’a pas réellement effectuée.',
    ],
  },
  d12: {
    excerpt: 'Pour les flux d’événements d’agents à sens unique, SSE avec enveloppes typées l’emporte sur la simplicité et la reprise.',
    body: [
      'Les équipes standardisent des enveloppes typées (tool.started / progress / completed) pour que tout nouvel outil devienne observable.',
      'Les flux reprenables (Last-Event-ID) réduisent la latence perçue sur réseaux mobiles instables.',
      'La contre-pression est gérée côté client : application des événements par batch à la cadence d’animation.',
    ],
  },
};

/* ── French → English concept expansion for ranked retrieval ── */

export const FR_SYNONYMS: Record<string, string[]> = {
  'modele': ['models', 'llm'], 'modeles': ['models', 'llm'], 'modèle': ['models', 'llm'], 'modèles': ['models', 'llm'],
  'raisonnement': ['reasoning', 'chain-of-thought'],
  'ia': ['ai', 'llm'],
  'intelligence': ['ai'], 'artificielle': ['ai'],
  'agent': ['agents', 'agentic'], 'agents': ['agents', 'agentic'], 'agentique': ['agentic', 'agents'],
  'cout': ['cost', 'pricing'], 'couts': ['cost'], 'coût': ['cost'], 'coûts': ['cost'],
  'prix': ['cost', 'pricing'],
  'inference': ['inference'], 'inférence': ['inference'],
  'contexte': ['context'], 'fenetre': ['context', 'window'], 'fenêtre': ['context', 'window'],
  'memoire': ['memory'], 'mémoire': ['memory'],
  'evaluation': ['evaluation', 'benchmarks'], 'evaluations': ['evaluation', 'benchmarks'],
  'évaluation': ['evaluation', 'benchmarks'], 'benchmarks': ['benchmarks'],
  'codage': ['coding', 'software'], 'code': ['coding'],
  'developpement': ['engineering'], 'développement': ['engineering'],
  'ingenierie': ['engineering'], 'ingénierie': ['engineering'],
  'outils': ['tools'], 'outil': ['tools'],
  'recherche': ['search', 'research'],
  'interface': ['interface', 'design', 'ux'], 'interfaces': ['interface', 'ux'],
  'experience': ['ux'], 'expérience': ['ux'],
  'conception': ['design'], 'produit': ['product'],
  'streaming': ['streaming', 'real-time'], 'flux': ['streaming', 'events'],
  'evenements': ['events'], 'événements': ['events'],
  'architecture': ['architecture', 'backend'],
  'temps': ['real-time'], 'reel': ['real-time'], 'réel': ['real-time'],
  'observabilite': ['observability'], 'observabilité': ['observability'],
  'video': ['video'], 'vidéo': ['video'], 'vision': ['vision'], 'multimodal': ['multimodal'],
  'robotique': ['robotics'], 'robot': ['robotics'], 'robots': ['robotics'],
  'distillation': ['distillation'], 'petits': ['small'], 'petit': ['small'],
  'modeles de raisonnement': ['reasoning', 'models'],
  'open': ['open-source'], 'opensource': ['open-source'],
  'securite': ['standards'], 'sécurité': ['standards'],
  'protocole': ['protocol', 'mcp'], 'mcp': ['mcp'],
  'web': ['web'], 'dernier': ['latest'], 'derniere': ['latest'], 'derniers': ['latest'], 'dernières': ['latest'],
  'nouvelles': ['latest'], 'actualites': ['latest'], 'actualités': ['latest'], 'nouveautes': ['latest'], 'nouveautés': ['latest'],
};
