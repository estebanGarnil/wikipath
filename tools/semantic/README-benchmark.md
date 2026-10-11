# Pilote élargi de Wikipath

Ce correctif ajoute uniquement la commande `export_semantic_benchmark`.
Il utilise les commandes et scripts du pilote et de la comparaison déjà installés.
Il ne change ni l'API ni les données PostgreSQL/Neo4j.

## Sources

Antoine Meillet, Algèbre linéaire, Algèbre générale (points de comparaison),
France, Python (langage), Photosynthèse, Révolution française, Impressionnisme,
Marie Curie et Football.

Les identifiants sont résolus par titres exacts dans PostgreSQL puis vérifiés
dans Neo4j. Une source manquante interrompt le traitement : elle n'est jamais
remplacée par un résultat de recherche approximatif.

Tous les voisins sortants distincts sont exportés. Le plafond de 20 000 pages
uniques protège ce pilote : s'il est dépassé, l'export échoue sans sélectionner
arbitrairement un sous-ensemble. On peut alors augmenter `--max-pages` ou
séparer les sources avec `--titles`.

## Exécution depuis la racine du projet (PowerShell)

```powershell
docker compose exec backend python manage.py export_semantic_benchmark --output /app/semantic-benchmark.json.gz
```

Attendre la réussite de l'export avant de lancer :

```powershell
.\.venv-semantic\Scripts\python.exe .\tools\semantic\compare_variants.py `
    .\backend\semantic-benchmark.json.gz `
    --reference-metadata .\semantic-results-v2\metadata.json `
    --device cpu `
    --output .\semantic-benchmark-results

if ($LASTEXITCODE -eq 0) {
    Start-Process .\semantic-benchmark-results\report.html
}
```

Les chemins de sortie doivent être nouveaux pour préserver les essais précédents.
Le modèle et sa révision restent identiques à ceux du pilote V2. V3 est notre
référence provisoire, mais V1/V2 sont conservées pour vérifier cette décision.
Le script déduplique les textes identiques entre variantes avant l'encodage.
Sur CPU, cette sélection sera plus longue que le premier essai : le nombre réel
de pages exportées et la longueur des textes déterminent le coût.

## Évaluation

Le rapport affiche les 60 premiers voisins par variante. `scores.csv` contient
le classement complet de tous les voisins : aucun plafond de 20 ou 60 n'est
appliqué au calcul des scores.

Premier contrôle : examiner les rangs 1–20 et 21–40 de V3, puis comparer V1/V2.
Dans `evaluation.csv`, remplir `pertinence_0_1_2` et éventuellement `commentaire` :

- 2 : voisin directement pertinent pour explorer le sujet ;
- 1 : voisin intéressant mais secondaire ;
- 0 : voisin peu utile dans ce contexte.

Une case vide signifie « non évalué », jamais zéro. Une même paire source/cible
ne reçoit qu'une note, commune aux trois variantes. Pour comparer équitablement
leurs vingt premiers résultats, noter l'union des voisins dont `rank_v1`,
`rank_v2` ou `rank_v3` est inférieur ou égal à 20. Comparer aussi chaque domaine
séparément : une bonne moyenne peut cacher un mauvais classement en biologie.

Ne pas noter la qualité à partir de la valeur du score E5 et ne pas supprimer
systématiquement toutes les dates : leur pertinence dépend de la page source.

Les exports, résultats et environnement Python sont locaux : ne pas les ajouter
au dépôt Git. Seuls les scripts et cette documentation sont à versionner.
