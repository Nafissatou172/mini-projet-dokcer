# Gestionnaire de tâches conteneurisé

Application web qui permet de créer, lister, filtrer par priorité et marquer comme faites des tâches, stockées dans PostgreSQL, servies par Flask derrière un reverse proxy Nginx.

## Prérequis

- Docker Engine **≥ 24** (ou Docker Desktop ≥ 4.25)
- Docker Compose **v2 ≥ 2.20** (commande `docker compose`, avec un espace)
- Port **8080** libre sur la machine (modifiable via `APP_PORT`)

## Démarrage

```bash
cp .env.example .env
docker compose up -d --build
```

Le premier démarrage télécharge les images et construit l'application (≈ 30 s). Compose attend que la base puis l'application soient *healthy* avant de lancer Nginx.

## Accès

| Quoi | URL |
|---|---|
| Interface web | http://localhost:8080 |
| API JSON (liste) | http://localhost:8080/api/tasks |
| Santé de l'app | http://localhost:8080/health |

Exemple d'appel API :

```bash
curl -X POST http://localhost:8080/api/tasks -H 'Content-Type: application/json' \
     -d '{"title":"Réviser Docker","priority":"haute"}'
curl "http://localhost:8080/api/tasks?status=todo&priority=haute"
curl -X PATCH  http://localhost:8080/api/tasks/1/done     # bascule faite / à faire
curl -X DELETE http://localhost:8080/api/tasks/1
```

## Services

| Service | Image | Rôle | Port publié |
|---|---|---|---|
| `proxy` | `nginx:1.27.2-alpine` | reverse proxy, seul point d'entrée | `APP_PORT` → 80 |
| `web` | construite depuis `app/Dockerfile` | application Flask (gunicorn :8000) | aucun |
| `db` | `postgres:16.4-bookworm` | base de données, volume nommé `db-data` | aucun |

## Variables d'environnement (`.env`)

| Variable | Rôle | Exemple |
|---|---|---|
| `APP_PORT` | port de l'hôte où l'application est accessible | `8080` |
| `POSTGRES_DB` | nom de la base créée au premier démarrage | `tasks` |
| `POSTGRES_USER` | utilisateur PostgreSQL (utilisé par `db` et `web`) | `tasks_user` |
| `POSTGRES_PASSWORD` | mot de passe de cet utilisateur | `change_me_please` |

> Les identifiants ne sont lus qu'à la **création** du volume. Si vous les changez après un premier démarrage, faites `docker compose down -v` (⚠ efface les données).

## Commandes utiles

```bash
docker compose ps                         # état des services
docker compose logs -f web                # suivre les logs de l'application
docker compose exec web sh                # ouvrir un shell dans le conteneur web
docker compose exec db psql -U tasks_user -d tasks   # console SQL
docker compose down                       # tout arrêter (les données sont conservées)
docker compose down -v                    # tout arrêter ET supprimer les données
```
