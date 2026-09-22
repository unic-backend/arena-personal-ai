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
extraits entrent dans le prompt comme donnees DOCUMENT, jamais comme instructions, et
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