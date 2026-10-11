# Préparation sémantique v2

Réutiliser backend/semantic-pilot.json.gz. Aucun nouvel export nécessaire.

```powershell
.\.venv-semantic\Scripts\python.exe .\tools\semantic\test_prepare_text.py
.\.venv-semantic\Scripts\python.exe .\tools\semantic\score_pilot.py `
    .\backend\semantic-pilot.json.gz `
    --device cpu `
    --compare .\semantic-results\scores.csv `
    --output .\semantic-results-v2
Start-Process .\semantic-results-v2\report.html
```

Les résultats v1 restent dans semantic-results. La colonne Ancien rang E5 permet
de comparer chaque voisin à son classement v1. Tous les voisins restent dans le CSV.

Changements : modèles courants de date, siècle, langue, nombres et mise en forme
préservés ; contenu des formules math conservé en texte (LaTeX, sans interprétation
mathématique) ; introduction de moins de 400 caractères complétée avec de la prose
jusqu'à environ 1 200 caractères ou la fin du contenu disponible. Les sections de
références et listes reconnues sont ignorées. Le modèle tronque toujours à 512 tokens.

texts.jsonl conserve l'introduction, le texte complété, les modèles inconnus omis,
les indicateurs de complément et d'homonymie. Les pages d'homonymie sont signalées,
sans pénalité de score afin de comparer d'abord le nettoyage seul.

Ce n'est pas un moteur MediaWiki : les modèles inconnus sont encore supprimés.
Contrôler les textes avant de généraliser. Les huit tests couvrent des cas construits,
pas tous les modèles Wikipédia ni les 334 textes originaux.

La révision du modèle est récupérée depuis config.json en cache et utilisée
explicitement au chargement. À défaut de cache, téléchargement de la configuration.
Elle est inscrite dans metadata.json. L'essai v1 n'ayant pas enregistré son hash,
l'identité exacte de sa révision ne peut pas être prouvée par ses métadonnées.
