# Wikipath — pilote sémantique portable

Cet essai exporte quelques sources et TOUS leurs voisins sortants distincts,
puis classe chaque voisinage par similarité du titre et de l'introduction.
Aucune écriture dans PostgreSQL ou Neo4j et aucune modification de l'API.
Les scores sont destinés à être examinés avant leur intégration sur les relations.

## 1. Sur l'ordinateur qui héberge Wikipath

Extraire l'archive à la racine de wikitest, puis :

```powershell
docker compose exec backend python manage.py export_semantic_pilot --page-ids 3 7 9 --output /app/semantic-pilot.json.gz
```

Le fichier se trouve dans backend/semantic-pilot.json.gz sur Windows (backend est
monté dans /app). Les sources proposées sont Antoine Meillet, Algèbre linéaire et
Algèbre générale. Remplacer ou compléter les IDs pour comparer d'autres thèmes.
Le garde-fou est 20 000 pages distinctes : en cas de dépassement, la commande
s'arrête sans exporter un échantillon tronqué. Les boucles vers soi sont exclues.
Ne pas modifier le graphe pendant l'export.

## 2. Sur l'ordinateur de calcul (Windows, Python 3.11 ou 3.12)

Copier tools/semantic/ et semantic-pilot.json.gz dans un dossier de travail.
Depuis ce dossier contenant score_pilot.py et requirements.txt :

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
```

GPU : installer la version CUDA de PyTorch indiquée par le sélecteur officiel
https://pytorch.org/get-started/locally/ (Windows / Pip / Python / CUDA).
Remplacer `pip3` dans la commande fournie par `.\.venv\Scripts\python.exe -m pip`.
Le pilote NVIDIA doit être compatible avec la version CUDA choisie.
Puis :

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -c "import torch; print('CUDA:', torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')"
.\.venv\Scripts\python.exe score_pilot.py semantic-pilot.json.gz --device cuda --output results-gpu
Start-Process .\results-gpu\report.html
```

Si Python 3.11 est installé, remplacer -3.12 par -3.11.
Pour essayer sur CPU : installer requirements.txt puis utiliser --device cpu.
En cas de mémoire GPU insuffisante, réduire --batch-size à 8 puis 4.
Utiliser un nouveau nom de dossier de résultats après un essai interrompu.

Internet est nécessaire pour installer les dépendances et télécharger le modèle
au premier lancement. Les articles sont traités localement, sans API d'inférence.
Aucun serveur Django, PostgreSQL ou Neo4j requis sur l'ordinateur de calcul.

## Résultats

- report.html : comparaison ordre par ID / ordre sémantique, rangs 1 à 60.
- scores.csv : TOUS les liens exportés avec score, rang et titre.
- embeddings.npz : un vecteur normalisé par page et la correspondance page_id.
- texts.jsonl : introductions effectivement préparées pour contrôler le nettoyage.
- metadata.json : modèle, révision disponible, révisions des articles, matériel et temps.

Le modèle multilingual-e5-small est utilisé avec le préfixe query: des deux côtés
pour la similarité symétrique. Texte limité à 512 tokens par le modèle ; les
introductions sont préparées à concurrence de 6 000 caractères avant tokenisation.
Les modèles du wikicode ne sont pas développés : des informations peuvent manquer.
Les articles absents ou sans introduction sont signalés et utilisent le titre seul.
Un score élevé n'est pas une probabilité de pertinence.

L'encodage de A et B donne le même score dans les deux sens. Une pertinence
orientée dépendant de la phrase où le lien apparaît serait une autre étape.

Examiner plusieurs thèmes et les rangs 21–40, pas seulement les tout premiers.
Le test ne permet pas encore de mesurer la vitesse de pagination dans Neo4j.
Après validation : importer les scores avec leur version sur les seules relations
concernées, puis ajouter une pagination stable (score décroissant, page_id croissant).
Ne pas extrapoler directement le temps de cet échantillon à toute Wikipédia.
Ne pas committer les exports, vecteurs ou résultats volumineux dans Git.
