# Pilote local : importance des liens et contexte

Ce correctif ajoute un outil expérimental. Il ne change ni Django, ni Neo4j,
ni l'interface, et ne réécrit aucun résultat précédent.

Il compare les mêmes voisins complets dans quatre classements : E5 V3 existant,
emplacement du lien, BGE sans contexte, BGE avec contexte. Aucun classement
n'est préfiltré par les 20/60 meilleurs voisins E5.

## 1. Préparation, sans connexion réseau

Depuis la racine du projet Windows :

```powershell
.\.venv-semantic\Scripts\python.exe .\tools\semantic\context_pilot.py prepare `
    --reference .\semantic-benchmark-results `
    --export .\backend\semantic-benchmark.json.gz `
    --output .\semantic-context-input
```

L'export gzip est celui déjà créé sur les dix pages. Le script vérifie les
sources, les révisions et les ensembles de liens. Les dépendances Python du
pilote existant suffisent (`mwparserfromhell`, `transformers`, `torch`, etc.).

La sortie indique combien de liens ont été retrouvés dans l'introduction,
le corps du texte, une liste, ou n'ont pas de contexte extrait. `pairs.jsonl`
conserve tous les liens, leur V3 et leurs extraits. `metadata.json` contient
la couverture par page. `unresolved_titles.csv` liste les titres explicites
non résolus dans le dictionnaire local ; ce ne sont pas nécessairement tous
des voisins du graphe ou des redirections.

### Redirections et limites d'extraction

Les titres sont rapprochés localement (espaces/underscores, fragments, Unicode,
première lettre). Aucun rapprochement approximatif ni appel Wikipédia.
Un fichier facultatif `--aliases chemin.csv` peut fournir deux colonnes :
`alias,target_page_id`, avec la cible finale déjà résolue dans le dump.
Le script ne crée pas ce fichier à partir d'une base de staging dont le schéma
n'est pas encore connu.

Les modèles ne sont pas développés et leurs liens internes sont ignorés.
Références, tableaux, galeries et autres zones retirées peuvent également
expliquer les contextes manquants. Le script ne prétend pas identifier un
lien « uniquement dans une boîte de navigation » sans preuve.
Un contexte absent ne supprime jamais le voisin : le cross-encoder utilise
alors exactement son score sans contexte.

Extraction heuristique : au maximum deux passages par relation, priorisant
l'introduction puis le corps puis les listes. Fenêtre de 900 caractères
maximum autour de la mention. Il peut rester des imperfections de wikicode.
Le classement par emplacement place les contextes inconnus en dernier pour
le diagnostic ; ce n'est pas une décision produit validée.

## 2. Télécharger une fois le modèle

```powershell
.\.venv-semantic\Scripts\python.exe .\tools\semantic\context_pilot.py download `
    --output .\models\bge-reranker-v2-m3
```

Cette étape utilise Hugging Face pour les fichiers du modèle uniquement :
aucun titre ou article n'est transmis. Le modèle est plus volumineux que
E5-small. Sa révision exacte est enregistrée dans `wikipath_model.json`.
Ne pas exécuter cette commande si le dossier a déjà été téléchargé avec succès.

## 3. Mesurer d'abord sur une page complète (CPU)

```powershell
.\.venv-semantic\Scripts\python.exe .\tools\semantic\context_pilot.py score `
    --prepared .\semantic-context-input `
    --model-dir .\models\bge-reranker-v2-m3 `
    --device cpu --batch-size 2 --max-sources 1 `
    --output .\semantic-context-smoke

if ($LASTEXITCODE -eq 0) { Start-Process .\semantic-context-smoke\report.html }
```

La première source par ID est Antoine Meillet : tous ses 112 voisins sont
conservés. C'est un essai de durée, pas un échantillonnage des liens.
Le cross-encoder coûte un calcul par paire et par variante ; ne pas extrapoler
le temps des embeddings de titres au traitement des 235 millions de relations.

## 4. Calcul sur les dix pages

```powershell
.\.venv-semantic\Scripts\python.exe .\tools\semantic\context_pilot.py score `
    --prepared .\semantic-context-input `
    --model-dir .\models\bge-reranker-v2-m3 `
    --device cpu --batch-size 2 `
    --output .\semantic-context-results

if ($LASTEXITCODE -eq 0) { Start-Process .\semantic-context-results\report.html }
```

Sur l'autre ordinateur avec PyTorch CUDA opérationnel, remplacer `cpu` par
`cuda`, en commençant également par un lot de 2. Le mode GPU utilise FP16,
le CPU FP32 : de petites différences numériques sont possibles. Tester la
mémoire et le temps avant d'augmenter la taille du lot.

L'analyse force le mode hors ligne et `local_files_only=True`. Elle fonctionne
sans Internet une fois le modèle présent. Aucune API d'inférence ni Wikipédia.

`progress.sqlite` enregistre les scores après chaque lot. Après Ctrl+C ou
une interruption, relancer exactement la même commande pour reprendre.
On peut changer la taille des lots. Un changement de modèle, de script,
d'entrées, de dispositif ou de sélection des sources exige un nouveau dossier.

## Lire le résultat

- `report.html` : 60 premiers voisins avec extraits consultables.
- `scores.csv` : classement complet, incluant tous les voisins introuvables.
- `metadata.json` : révision, couverture, temps de la session et nombre de
  paires réellement calculées pendant cette session (pas un temps cumulé).
- `progress.sqlite` : reprise des deux variantes du cross-encoder.

L'emplacement est un ordre heuristique, pas un score appris. Les valeurs BGE
sont des logits, pas des probabilités d'importance et pas des cosinus E5.
Les classements doivent être évalués sur la pertinence des voisins.

Le modèle est entraîné pour la pertinence requête/passage, pas pour attribuer
une importance encyclopédique aux relations Wikipédia. Ajouter un extrait de
la source peut artificiellement favoriser sa similarité avec elle-même :
la variante sans contexte sert de contrôle. Aucun gain n'est garanti.

Budget de texte pour BGE : source titre/introduction 112 tokens ; cible
titre/introduction 144 tokens ; contexte supplémentaire 208 tokens ; paire
limitée à 512 tokens. Pas de préfixe E5 `query:` dans ce modèle.

Ne versionner que les scripts/documentation. Exclure `models/`,
`semantic-context-input/`, `semantic-context-smoke/`, `semantic-context-results/`
et leurs éventuelles variantes de noms du dépôt Git.

## Tests locaux

```powershell
.\.venv-semantic\Scripts\python.exe -m unittest discover `
    -s .\tools\semantic -p test_context_pilot.py
```

Le helper `compare_title_models.py` inclus est inchangé par rapport au correctif
précédent et sert à vérifier les fichiers du benchmark.
