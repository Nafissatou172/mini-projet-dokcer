# Rapport mini projet Docker — Conteneurisation du gestionnaire de tâches

## Prénom et nom : Nafissatou SOW
## Master MSEBDE

J'ai choisi l'option B, une application de gestion de tâches. Elle utilise trois services : Flask pour l'application, PostgreSQL pour la base et Nginx en reverse proxy devant. J'ai ajouté une fonctionnalité qui n'était pas demandée : chaque tâche a une **priorité** (basse, normale ou haute). La liste est triée automatiquement avec les tâches importantes en haut, et on peut filtrer par statut (à faire / faites) et par priorité, dans l'interface comme dans l'API.

Toutes les mesures ont été prises sur mon Mac (puce Apple, arm64), avec Docker Engine 28.5.2 et Compose v2.40.3. Les sorties complètes sont dans le dossier `mesures/`.

## 1. Image de base

Pour l'application, j'ai choisi `python:3.12.7-slim-bookworm`. Je voulais un tag précis : avec `python:latest` ou même `python:3.12`, l'image peut changer d'une semaine à l'autre, et deux personnes n'auraient plus forcément le même résultat.

J'ai d'abord comparé avec la version complète `python:3.12.7-bookworm`. Elle contient tout ce qu'il faut pour compiler (gcc, les en-têtes, git…), mais je n'en ai pas besoin : toutes mes dépendances existent déjà en version précompilée, y compris le driver Postgres (`psycopg[binary]`). Résultat : **1,49 GB** pour la complète, contre **241 MB** pour la slim.

J'ai écarté Alpine parce qu'elle utilise musl au lieu de glibc. Beaucoup de paquets Python ne sont pas précompilés pour musl, donc pip doit les compiler, et il faut alors réinstaller un compilateur dans l'image. On perd du temps de build pour gagner peu de place. La slim me paraît le meilleur compromis.

Pour Nginx, en revanche, j'ai pris `nginx:1.27.2-alpine` : je ne fais que lui donner un fichier de config, il n'y a rien à compiler, donc Alpine ne pose aucun problème.

## 2. Cache

Voici l'ordre de mon Dockerfile :

```
FROM python:3.12.7-slim-bookworm
ENV ...                                 # réglages Python
WORKDIR /app
RUN useradd ... appuser                 # utilisateur non-root
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY --chown=appuser:appuser . .        # le code
USER appuser
CMD ["gunicorn", ...]
```

L'idée est de mettre en haut ce qui ne bouge presque jamais et en bas ce qui change tout le temps. Docker réutilise chaque couche tant que rien n'a changé au-dessus. Quand je modifie une ligne de code, seule la dernière `COPY` est différente : tout ce qui précède, y compris le `pip install`, est repris du cache. Les dépendances ne sont réinstallées que si je touche à `requirements.txt`. Si j'avais copié tout le code avant le `pip install`, la moindre modification aurait relancé l'installation complète.

**Premier build, sans cache (`--no-cache`) : 30,0 s**
```
#10 [5/6] RUN pip install -r requirements.txt
#10 2.256 Successfully installed Flask-3.0.3 ... gunicorn-23.0.0 ... psycopg-3.2.3 psycopg-binary-3.2.3
#10 DONE 2.3s
#11 [6/6] COPY --chown=appuser:appuser . .
#11 DONE 0.0s
docker compose build --no-cache --progress=plain web  0.24s user 0.22s system 1% cpu 30.022 total
```

**Deuxième build, après avoir changé le titre dans `templates/index.html` : 0,56 s**
```
#7 [2/6] WORKDIR /app
#7 CACHED
#8 [3/6] RUN useradd --create-home --uid 1000 appuser
#8 CACHED
#9 [4/6] COPY requirements.txt .
#9 CACHED
#10 [5/6] RUN pip install -r requirements.txt
#10 CACHED
#11 [6/6] COPY --chown=appuser:appuser . .
#11 DONE 0.0s
docker compose build --progress=plain web  0.15s user 0.09s system 42% cpu 0.564 total
```

On voit bien que seule l'étape 6/6 a été refaite. Les 30 secondes du premier build viennent surtout du téléchargement de l'image de base. Pour comparer, un build sans aucune modification prend 1,1 s.

## 3. Taille

```
$ docker image ls tasks-web:1.0
IMAGE           ID             DISK USAGE   CONTENT SIZE
tasks-web:1.0   3eb8bccfcf5d        241MB         52.1MB
```

Mon image fait **241 MB** sur le disque (52,1 MB compressée). Avec l'image Python complète, elle faisait **1,49 GB**, soit environ 6 fois plus.

L'essentiel du gain vient du passage à la slim. Deux autres réglages jouent à plus petite échelle :
- `PIP_NO_CACHE_DIR=1` : pip ne garde pas de copie des paquets téléchargés, et la couche d'installation ne pèse que 22,9 MB.
- `.dockerignore` : les fichiers `__pycache__`, `.venv`, `.env` et `.git` ne sont pas envoyés au build. La couche du code ne fait que 28,7 kB.

```
28.7kB  COPY --chown=appuser:appuser . .
22.9MB  RUN pip install -r requirements.txt
12.3kB  COPY requirements.txt .
69.6kB  RUN useradd --create-home --uid 1000 appuser
```

## 4. Persistance

Postgres range ses fichiers dans `/var/lib/postgresql/data`. J'y ai monté un volume nommé, `db-data`, que Docker appelle `tasks_db-data` parce qu'il ajoute le nom du projet devant.

Pour tester, j'ai créé une tâche « Rendre le mini-projet » via l'API, puis :

- **`docker compose restart`** : les conteneurs sont seulement redémarrés, pas recréés. La tâche est toujours là, ce qui n'a rien de surprenant.
- **`docker compose down` puis `up`** : c'est le test intéressant. `down` supprime les conteneurs et le réseau, mais **ne touche pas aux volumes nommés**. Au `up`, Docker crée un nouveau conteneur Postgres et lui rebranche le même volume. Postgres voit que ses données existent déjà et ne réinitialise rien. Côté application, le `CREATE TABLE IF NOT EXISTS` ne fait rien puisque la table existe. La tâche était bien toujours là.
- **`docker compose down -v`** : le `-v` supprime aussi le volume. Au redémarrage, Postgres repart d'un dossier vide : il recrée la base avec les identifiants du `.env`, puis l'application recrée la table vide. L'API renvoyait alors une liste vide `[]`.

La sortie complète de ces tests est dans `mesures/persistance.txt`.

## 5. Difficultés

### Docker ne répondait pas

Ma toute première commande `docker compose build` a échoué tout de suite : Docker disait qu'il n'arrivait pas à se connecter à son socket. Au début, j'ai cru à un problème d'installation, mais `docker --version` fonctionnait. Le client était donc bien là, c'est le démon qui ne tournait pas. Sur Mac, il vit dans Docker Desktop, et je ne l'avais simplement pas lancé. J'ai ouvert Docker Desktop, attendu que `docker info` affiche la version du serveur, et tout est reparti.

### Lancement sans fichier `.env`

Pour me mettre à la place de quelqu'un qui découvre le projet, j'ai copié le dossier ailleurs et lancé `docker compose up` sans créer le `.env`. Compose s'est arrêté immédiatement en disant que `POSTGRES_DB` n'avait pas de valeur. C'est normal : le `.env` est dans le `.gitignore`, donc il n'existe pas quand on récupère le projet.

Ce comportement est voulu. Dans le `compose.yaml`, j'ai écrit les variables sous la forme `${POSTGRES_DB:?message}`, qui oblige Compose à s'arrêter avec un message clair si la variable manque. Avec un simple `${POSTGRES_DB}`, Compose aurait juste affiché un avertissement et lancé la base avec des identifiants vides, et l'erreur serait apparue plus loin, sans lien évident avec la cause. Pour que personne ne tombe dessus, j'ai mis `cp .env.example .env` en première ligne du README.

### Mot de passe changé après coup

J'ai essayé de changer le mot de passe de la base alors que le volume existait déjà. Le conteneur `web` ne passait plus jamais en « healthy », et dans ses logs, Postgres refusait la connexion pour mauvais mot de passe. C'était déroutant, parce que le service `db` était marqué « healthy » : le problème ne venait donc ni du réseau ni de la base elle-même.

En cherchant, j'ai compris que l'image Postgres ne lit le mot de passe **qu'à la toute première initialisation**, quand le volume est vide. Ensuite, le mot de passe est enregistré dans les données, et la variable d'environnement n'est plus lue. L'application utilisait le nouveau mot de passe, alors que la base attendait toujours l'ancien. Pour réparer, soit on remet l'ancien mot de passe, soit on fait `docker compose down -v` pour repartir de zéro, mais on perd les données. J'ai ajouté un avertissement à ce sujet dans le README. Les logs m'ont aussi confirmé que l'application joignait bien la base par son nom : on y voit l'adresse IP que Docker a associée à `db`.

### Nginx qui renvoyait des erreurs 502

Pour tester ma config Nginx toute seule, j'ai lancé le proxy sans l'application derrière. Je m'attendais à ce que Nginx refuse de démarrer, puisque le service `web` n'existait pas. Au contraire, il démarrait sans problème, mais chaque page renvoyait une erreur 502 (Bad Gateway).

Dans les logs, j'ai vu que Nginx essayait de joindre `web` sur une adresse bizarre, `127.0.53.53`, qui n'est celle d'aucun conteneur. J'ai vérifié depuis le conteneur comment le nom `web` était résolu, et c'était bien cette adresse. J'ai compris que, quand un nom ne correspond à aucun service du réseau, Docker transmet la question au DNS de mon ordinateur. Or `.web` est une vraie extension de nom de domaine, comme `.com`, et `127.0.53.53` est une adresse spéciale renvoyée pour signaler ce genre de conflit de noms. Nginx envoyait donc les requêtes vers une adresse où rien n'écoute.

Je retiens qu'un nom de service absent ou mal écrit ne donne pas forcément une erreur claire du type « host not found » : il faut regarder vers quelle adresse partent vraiment les requêtes. Dans le projet normal, ce cas ne se produit pas, car Nginx attend que `web` soit démarré et en bonne santé avant de se lancer (`depends_on` avec `condition: service_healthy`). C'est d'ailleurs ce même mécanisme qui évite à l'application de démarrer avant que Postgres soit prêt.
