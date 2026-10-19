# Traitement sémantique

Les pages sont encodées avec multilingual-e5-small.
La similarité des vecteurs sert à classer les liens sortants dans Neo4j.

## Fichiers

- prepare_text.py : préparation du texte.
- encode_full.py : calcul des vecteurs avec reprise SQLite.
- run_full.ps1 : lancement du calcul sur GPU.
- requirements-full.txt : dépendances du traitement.
- reference-metadata.json : modèle et préparation de référence.

## Calcul

Depuis la racine du dépôt, avec les dépendances installées :

```powershell
.\.venv-semantic\Scripts\python.exe .\tools\semantic\encode_full.py `
    --nodes .\input\nodes.csv `
    --articles .\input\articles.sqlite `
    --prepare .\tools\semantic\prepare_text.py `
    --reference-metadata .\tools\semantic\reference-metadata.json `
    --output .\semantic-full-output\vectors.sqlite `
    --device cuda
```

Relancer la même commande reprend les lots validés.
Conserver les mêmes entrées, scripts et versions des dépendances.

## Import des scores

Placer le fichier terminé dans backend/semantic-full-input/vectors.sqlite.

```powershell
docker compose exec backend python manage.py import_semantic_full `
    --vectors /app/semantic-full-input/vectors.sqlite
```

La progression est enregistrée dans Neo4j pour permettre la reprise.
Les données, vecteurs et environnements Python ne sont pas versionnés.
