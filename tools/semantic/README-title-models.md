# Comparer l'ancienne méthode MiniLM avec E5

Ce script ne modifie ni les bases ni l'API. Il réutilise le dossier
`semantic-benchmark-results` contenant `metadata.json`, `scores.csv` et
`texts.jsonl`. Aucun export supplémentaire n'est nécessaire.

Trois classements sur exactement les mêmes liens :

1. MiniLM `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, titres seuls,
   casse conservée, sans préfixe (comme l'ancien traitement batch).
2. E5 `intfloat/multilingual-e5-small`, titres seuls, `query: ` des deux côtés,
   révision identique au benchmark précédent.
3. E5 V3 : scores précédents réutilisés exactement, sans nouvel encodage.

La révision historique de MiniLM n'était pas enregistrée dans l'ancien backend.
Le script fixe et enregistre la révision disponible au lancement. Il reproduit
la méthode, sans prétendre reproduire bit à bit les résultats historiques.
Il conserve la limite de séquence fournie par MiniLM et fixe E5 à 512 tokens.

Les dépendances du pilote existant suffisent. Internet est nécessaire pour
résoudre la révision MiniLM et télécharger les modèles non encore présents.
Les modèles s'exécutent localement : les titres ne sont pas envoyés à une API
d'inférence distante.

## Depuis la racine du projet, dans PowerShell

```powershell
.\.venv-semantic\Scripts\python.exe .\tools\semantic\compare_title_models.py `
    .\semantic-benchmark-results `
    --device cpu `
    --output .\semantic-title-results

if ($LASTEXITCODE -eq 0) {
    Start-Process .\semantic-title-results\report.html
}
```

L'encodage utilise un lot de 32 titres par défaut, configurable par
`--batch-size`. Sur une machine avec PyTorch CUDA installé et un GPU compatible,
utiliser `--device cuda`. Aucun délai précis n'est garanti : les entrées sont
plus courtes que les introductions, mais deux modèles restent à exécuter.

Le dossier de sortie doit être nouveau. Les résultats précédents ne sont pas
écrasés. En cas d'échec, garder le dossier partiel pour diagnostic et choisir
un autre nom pour relancer ; la reprise automatique n'est pas implémentée.

## Résultats

- `report.html` : 60 premiers voisins, séparations aux rangs 21 et 41.
- `scores.csv` : tous les liens et tous les rangs pour chaque méthode.
- `evaluation.csv` : une note humaine par paire source/cible (vide = non évalué).
- `metadata.json` : révisions, temps, limites de séquence et empreintes des entrées.
- `minilm_title_embeddings.npz` et `e5_title_embeddings.npz` : vecteurs réutilisables
  et identifiants alignés (tableaux `embeddings` et `page_ids`).

Les scores affichés sont les cosinus bruts. La colonne `legacy_score_0_1`
contient aussi `(cosinus + 1) / 2` pour MiniLM, comme dans l'ancien backend.
Cette transformation ne change pas l'ordre. Une valeur plus haute d'un modèle
que d'un autre ne signifie pas que son résultat est meilleur.

Pas de filtre d'homonymie, de mélange de scores ni d'exclusion de listes : cela
permet d'isoler l'effet du modèle et du texte. Tous les voisins sont classés
avant d'afficher les 60 premiers. Les ex aequo sont départagés par page_id.

Pour vérifier sans charger les modèles :

```powershell
.\.venv-semantic\Scripts\python.exe -m unittest discover `
    -s .\tools\semantic -p test_compare_title_models.py
```

À versionner : les scripts et cette documentation. Garder localement les
exports, résultats et vecteurs, et vérifier leur exclusion dans `.gitignore`.
