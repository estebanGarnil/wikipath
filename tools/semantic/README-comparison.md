# Comparaison contrôlée v1 / v2 / v3

Pré-requis : pilote initial et correctif v2 déjà installés. Ce patch utilise
prepare_text.py de la v2 et ne remplace ni ce fichier ni score_pilot.py.

- V1 : préparation initiale, introduction seule.
- V2 : nettoyage corrigé, introduction complétée quand elle est courte.
- V3 : même nettoyage corrigé, introduction seule.

Les trois variantes sont recalculées avec la révision exacte enregistrée dans
semantic-results-v2/metadata.json. Si celle-ci manque, le programme s'arrête avec
un message explicite. Le même export est utilisé ; aucun changement des bases.
Les entrées textuelles identiques sont encodées une seule fois et partagées.

```powershell
.\.venv-semantic\Scripts\python.exe .\tools\semantic\test_compare_variants.py
.\.venv-semantic\Scripts\python.exe .\tools\semantic\compare_variants.py `
    .\backend\semantic-pilot.json.gz `
    --reference-metadata .\semantic-results-v2\metadata.json `
    --device cpu `
    --output .\semantic-comparison
if ($LASTEXITCODE -eq 0) {
    Start-Process .\semantic-comparison\report.html
}
```

V1 → V3 mesure l'effet du nettoyage. V3 → V2 mesure l'effet du complément.
Les scores restent bruts : aucune pénalité sur les dates ou homonymies.
Comparer la pertinence des titres, pas les scores absolus entre variantes.

report.html montre les rangs 1 à 60 côte à côte ; scores.csv contient tous les
voisins dans les trois versions. evaluation.csv permet de noter chaque voisin
(0 = accessoire, 1 = utile, 2 = central) selon un critère fixé à l'avance, et sans
prendre les scores du modèle comme référence. texts.jsonl permet de contrôler
les textes utilisés. metadata.json indique notamment la troncature à 512 tokens.
Les temps d'encodage sont communs aux trois variantes (textes dédupliqués), pas
un benchmark individuel de vitesse par variante.

Ne pas généraliser la conclusion à toute Wikipédia sur ces trois sources,
dont deux sont mathématiques. Ajouter ensuite des thèmes distincts en validation.
Les anciens résultats sont préservés. Le dossier de sortie doit être nouveau.
