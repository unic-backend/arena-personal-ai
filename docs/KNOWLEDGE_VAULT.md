# Knowledge Vault ARENA

ARENA dispose maintenant d'une base de connaissance Markdown locale inspiree du motif
LLM Wiki : les sources brutes restent intactes, le wiki s'accumule au lieu d'etre
reconstruit a chaque question, et chaque passage rendu garde sa provenance.

## Les trois couches

- data/knowledge_vault/raw/ : articles, papiers, transcriptions et documents originaux.
- data/knowledge_vault/wiki/ : notes Markdown interliees, ouvrables directement dans
  Obsidian. index.md est la carte d'entree et log.md le journal append-only.
- data/knowledge_vault/output/ : graph.json et autres rapports regenerables.

Le dossier data/knowledge_vault/ est ignore par Git : les documents du proprietaire ne
doivent jamais entrer dans le depot public.

## Commandes

python scripts/knowledge_vault.py init
python scripts/knowledge_vault.py ingest chemin/vers/source.pdf
python scripts/knowledge_vault.py search "question"
python scripts/knowledge_vault.py lint
python scripts/knowledge_vault.py graph

L'ingestion reutilise tools/documents/reader.py. Elle ne resume rien de memoire : si un
PDF, DOCX, TXT, MD, CSV, XLSX ou PPTX ne peut pas etre lu, l'operation est refusee.

## Ce qui est branche dans Arena

La conversation peut rechercher automatiquement les pages pertinentes du vault. Les
extraits entrent dans le prompt comme donnees RETRIEVED, jamais comme instructions, et
chaque resultat porte le chemin de la note et sa ou ses sources.

Le vault ne remplace pas core/memory/ ni PROJECT_MEMORY/. Cela evite trois systemes qui
se disputeraient la meme responsabilite : memoire personnelle, memoire du depot et
connaissance documentaire restent separees.

## Carte et verification

Le graphe est calcule a partir des wikilinks. Le lint signale les liens casses, les
pages orphelines, les sources brutes non compilees, les pages sans provenance et les
doublons exacts de source.

## Provenance de l'idee

Le motif vient du LLM Wiki d'Andrej Karpathy et la structure raw/wiki/output a ete
comparee au starter vault public de Josh Pocock. Aucun code externe n'est copie ici ;
l'implementation respecte les contrats locaux d'ARENA et reutilise son lecteur de
documents existant.

- https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f
- https://github.com/joshpocock/karpathy-obsidian-vault

## Retrieval hybride et exploration agentique

Le moteur de recherche du vault ne repose plus sur un simple comptage de mots :

- BM25 local pour les termes exacts, identifiants, noms techniques et vocabulaire metier ;
- embeddings locaux Ollama quand ils sont disponibles et que le corpus reste dans la
  borne prevue ;
- Reciprocal Rank Fusion (RRF) pour fusionner les rangs lexicaux et semantiques sans
  moyenner des scores incompatibles ;
- repli explicite sur BM25 si le moteur dense ne rend pas de vecteur exploitable.

Le vault ne cree toujours aucune seconde base vectorielle. Les vecteurs utilises par le
chemin hybride sont temporaires ou fournis par l'infrastructure locale existante.

Trois outils read-only permettent a un agent d'explorer la connaissance au lieu de
recevoir un gros bloc de texte :

- knowledge_list : decouvrir les pages ;
- knowledge_find : trouver un passage exact avec chemin, ligne et contexte borne ;
- knowledge_read : lire une plage precise, avec confinement strict dans wiki/.

Les donnees lues restent emballees avec TrustLevel.RETRIEVED. Une instruction trouvee
dans une note ne devient jamais une instruction systeme.

## Evaluation

La qualite du retrieval peut maintenant etre mesuree sur des cas labels :

python scripts/evaluer_knowledge_vault.py evaluation.json
python scripts/evaluer_knowledge_vault.py evaluation.json --lexical-only

Le rapport calcule Recall@k et NDCG@k, avec les chemins predits et attendus. Sans jeu de
verite terrain, aucun score n'est produit.

## Inspiration AI Cookbook

Le depot public daveebbelaar/ai-cookbook (licence MIT) a ete etudie pour trois motifs
utiles : progression d'un agent par niveaux, Agentic RAG list/find/read, et retrieval
hybride BM25 + dense + RRF + evaluation. ARENA n'importe ni ses dependances cloud, ni
ses fournisseurs OpenAI/Cohere, ni son runtime Claude Agent SDK. Les motifs sont
reimplementes autour des contrats locaux existants d'ARENA.

- https://github.com/daveebbelaar/ai-cookbook
