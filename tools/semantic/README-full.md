# Wikipath : E5 V3 sur toute la base, avec reprise

## Organisation

1. Sur le PC RTX 3070 : nodes.csv + articles.sqlite -> vectors.sqlite.
2. Sur le PC qui heberge Neo4j : vectors.sqlite -> scores des liens du graphe.

Le PC GPU n'a pas besoin de Docker, PostgreSQL, Neo4j ni relationships.csv.
Le modele est telecharge une premiere fois ; les articles sont traites localement,
sans API d'inference. Les calculs de similarite sont des produits scalaires sur
CPU pendant l'import ; le GPU sert a encoder les textes, une seule fois par page.

Le script reutilise EXACTEMENT le prepare_text.py du benchmark V3, la revision du
modele referencee dans metadata.json, le prefixe query: sur les deux pages,
le titre + l'introduction nettoyee limitee a 6000 caracteres, 512 tokens et des
vecteurs normalises de 384 float32. De petits ecarts numeriques CPU/GPU restent
possibles. Aucun score n'est une probabilite.

## Avant le transfert

Sur le PC actuel, conserver :

- database/neo4j/import/nodes.csv : le fichier importe dans Neo4j.
- articles.sqlite : l'original qui a servi a alimenter PostgreSQL.
- tools/semantic/prepare_text.py : le preparateur original du benchmark.
- semantic-benchmark-results/metadata.json : metadonnees V1/V2/V3 validees.
- les scripts de cette archive.

Le SHA256 de prepare_text.py doit correspondre a preparation_sha256 dans les
metadonnees. Le script refuse de demarrer si ce n'est pas le meme preparateur.
Si le fichier manque, le recuperer dans la version ayant produit le benchmark ;
ne pas le remplacer par un nettoyage approximatif.

Utiliser une copie stable du SQLite, sans processus qui le modifie. Si le fichier
source utilise encore un journal WAL actif, faire une sauvegarde SQLite coherente
avant le transfert. L'original ferme issu de l'extraction peut etre copie tel quel.
Les pages sans article recoivent un vecteur construit avec leur titre, comme dans
le pilote. Si PostgreSQL a recu des corrections absentes du SQLite original, il
faut d'abord exporter un SQLite a jour : ne pas melanger les snapshots.

## Installation sur le PC RTX 3070 (PowerShell)

Creer un dossier wikipath-semantic, y extraire ce ZIP et copier les entrees dans
un sous-dossier input (dont prepare_text.py si souhaite). Python 3.11 convient.
Recreer le venv sur ce PC ; ne pas copier celui de l'autre ordinateur.

```powershell
py -3.11 -m venv .venv-semantic
.\.venv-semantic\Scripts\python.exe -m pip install --upgrade pip
.\.venv-semantic\Scripts\python.exe -m pip install torch --index-url https://download.pytorch.org/whl/cu126
.\.venv-semantic\Scripts\python.exe -m pip install -r .\tools\semantic\requirements-full.txt
.\.venv-semantic\Scripts\python.exe -c "import torch; print('CUDA:', torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'GPU indisponible')"
```

La derniere commande doit annoncer CUDA: True et la RTX 3070. Sinon ne pas
lancer le calcul : verifier le pilote et l'installation proposee sur
https://pytorch.org/get-started/locally/ pour Windows/Pip/CUDA.

## Premier passage : 2000 articles pour mesurer le debit

```powershell
.\.venv-semantic\Scripts\python.exe .\tools\semantic\encode_full.py `
    --nodes .\input\nodes.csv `
    --articles .\input\articles.sqlite `
    --prepare .\input\prepare_text.py `
    --reference-metadata .\input\metadata.json `
    --output .\semantic-full-output\vectors.sqlite `
    --device cuda --batch-size 16 --workers 4 --max-pages 2000
```

Ce premier passage calcule les empreintes des entrees et charge TOUS les titres,
puis encode 2000 articles. Cela permet d'estimer la duree sur cette machine, en
incluant le nettoyage CPU. Le debit initial est seulement indicatif : la taille
des articles varie. L'ETA s'affiche a chaque sauvegarde, tous les 64 articles.

Relancer EXACTEMENT la meme commande SANS --max-pages 2000 pour continuer jusqu'au
bout. Une interruption ou un redemarrage ne fait pas recalculer les lots valides.
Les empreintes des fichiers sont relues a chaque lancement (cela peut prendre
quelques minutes) pour verifier qu'on reprend le meme dump. Ne pas mettre a jour
les dependances pendant un calcul : leur version fait partie de son identite.

En cas de memoire GPU insuffisante, reprendre avec --batch-size 8, voire 4.
En cas de pression sur la RAM CPU, reprendre avec --workers 2.
--checkpoint-pages permet de choisir entre 1 et 500 articles par sauvegarde.
Un seul processus peut ecrire le fichier de sortie ; le verrou OS est libere
automatiquement apres un crash. Aucun fichier .lock n'a besoin d'etre supprime.

Attendre le message TERMINE et la fin du processus, puis copier seulement
vectors.sqlite vers backend/semantic-full-input/vectors.sqlite sur le PC Neo4j.
Ne pas copier le fichier pendant un calcul actif.

## Espace disque et duree

Pour 2 777 420 pages, les float32 seuls occupent environ 4,27 Go (3,97 Gio).
SQLite ajoute titres, index, alignement et journal : le fichier final sera plus
gros. Prevoir au moins 15 Go libres pour la sortie et une marge sur le PC GPU,
en plus des fichiers d'entree et de l'environnement Python. Le pipeline ne
cree pas de CSV contenant les 235 millions de scores.

Sur le PC Neo4j, prevoir le fichier de vecteurs et une marge importante pour les
proprietes des relations et les journaux de transactions. La taille brute des
doubles (~1,88 Go pour 235 millions) n'est PAS une estimation de la croissance
reelle de Neo4j. Mesurer celle-ci sur le premier import limite avant de generaliser.
Consulter l'espace libre du disque qui heberge Docker Desktop, pas seulement C:.
Conserver une sauvegarde recuperable de Neo4j avant la grande ecriture.

Le nettoyage, les lectures SQLite et les ecritures Neo4j peuvent etre limitants.
Ne pas extrapoler le temps total uniquement depuis la vitesse GPU ou les dix
pages du pilote. Des durées de plusieurs heures, voire jours, restent possibles.
Desactiver la mise en veille automatique pendant les traitements.

## Installation sur le PC Neo4j

Extraire egalement ce ZIP a la racine de wikitest. Le fichier graph/services.py
est adapte au stockage economique de la version sur la page. Il reste compatible
avec le pilote et sa pagination signee, a installer au prealable.

Ajouter une seule fois cette ligne a backend/requirements.txt :

```text
numpy>=1.26,<3
```

Puis reconstruire le backend pour installer numpy durablement :

```powershell
docker compose up -d --build backend
docker compose exec backend python manage.py check
docker compose exec backend python manage.py test apps.graph.tests_semantic
docker compose exec backend python manage.py test apps.articles.tests_semantic_full
```

Verifier que l'index/contrainte unique sur Page.page_id est toujours en place.
L'import l'utilise pour retrouver les pages sans balayer tout le graphe.

### Verification sans ecriture (20 premieres pages)

```powershell
docker compose exec backend python manage.py import_semantic_full `
    --vectors /app/semantic-full-input/vectors.sqlite --check-only --max-pages 20
```

### Premier import limite (1000 pages)

```powershell
docker compose exec backend python manage.py import_semantic_full `
    --vectors /app/semantic-full-input/vectors.sqlite --max-pages 1000
```

Observer le debit, l'espace libre et la croissance du stockage Docker avant de
continuer. Les 1000 pages sont choisies par ID croissant : ce n'est pas un
echantillon representatif de tous les degres du graphe.

### Import complet / reprise apres arret

```powershell
docker compose exec backend python manage.py import_semantic_full `
    --vectors /app/semantic-full-input/vectors.sqlite
```

Par defaut, 20 pages completes sont ecrites par transaction. Pour reduire la RAM
ou la duree des transactions, utiliser --pages-per-batch 5, voire 1 pour une page
avec beaucoup de voisins. Les calculs de vecteurs ne sont jamais refaits ici.

Le point de reprise est un noeud WikipathSemanticRun, valide dans la MEME
transaction que les scores et les marqueurs des pages. Si le processus tombe
apres le commit mais avant l'affichage, la prochaine execution reprend au bon
endroit. Un lot non valide est recalcule. Ne pas supprimer les noeuds de suivi.
Ne pas lancer plusieurs versions en parallele et ne pas modifier les liens
pendant l'import. Si la couverture change entre lecture et ecriture, le lot est
annule. Une page sans vecteur bloque le lot plutot que de recevoir un faux score.

Les pages deja importees deviennent immediatement utilisables par l'API. Une
exploration dont la version change doit etre rechargee (409 explicite). Les
pages non traitees conservent leur fonctionnement precedent.

Les relations multiples recoivent le meme score. Les boucles vers soi-meme et
les identifiants non positifs sont exclus, comme dans l'API actuelle. Aucun lien
n'est cree ou supprime. Les scores du pilote sont remplaces au passage de ses
pages ; la version est conservee sur la page, et non repetee sur chaque lien.

## Suivi dans Neo4j Browser

```cypher
MATCH (r:WikipathSemanticRun)
RETURN r.run_id, r.pages_done, r.edges_done, r.last_page_id,
       r.complete, r.updated_at;
```

## Git

Ignorer les donnees et le venv, conserver scripts et requirements :

```gitignore
/semantic-full-output/
/backend/semantic-full-input/
/.venv-semantic/
/input/
```

## Limites des verifications du correctif

Les tests locaux couvrent les checkpoints SQLite, vecteurs invalides/manquants,
cosinus et validation des lots/points de reprise via un pilote Neo4j simule.
Le preparateur original est fourni par l'utilisateur et protege par son SHA256.
Le calcul n'a pas ete lance ici sur la RTX 3070 ni sur les 235 millions de liens.
Le premier passage GPU et le premier import limite constituent les verifications
sur les donnees et le materiel reels.
