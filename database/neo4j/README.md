# Graphe Neo4j

Les pages portent le label Page et sont identifiées par page_id.
Les relations orientées utilisent le type LINKS_TO.
La propriété semantic_score permet de classer les voisins sortants.

## Utilisation

Démarrage : docker compose up -d neo4j
Interface locale : http://localhost:7474
Connexion du backend : bolt://neo4j:7687
Mot de passe : variable NEO4J_PASSWORD dans .env.

## Stockage

Le volume neo4j_wikipedia_data contient la base.
Le dossier database/neo4j/import contient les fichiers à importer.
Les données et sauvegardes ne sont pas versionnées.

Attention : docker compose down -v supprime les volumes et leurs données.
