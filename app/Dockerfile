# Version précise pour que le build donne la même chose chez tout le monde.
# slim : assez léger, mais reste sur Debian (glibc) donc les wheels pip passent sans compiler.
FROM python:3.12.7-slim-bookworm

# Pas de fichiers .pyc, logs affichés tout de suite dans docker logs, et pip ne garde pas son cache
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Je ne veux pas que l'appli tourne en root
RUN useradd --create-home --uid 1000 appuser

# On copie d'abord juste requirements.txt : tant que je n'ajoute pas de dépendance,
# le pip install reste en cache, même si je modifie le code
COPY requirements.txt .
RUN pip install -r requirements.txt

# Le code en dernier, c'est ce qui change le plus souvent
COPY --chown=appuser:appuser . .

USER appuser
EXPOSE 8000

# Forme tableau : pas de shell intermédiaire, gunicorn reçoit directement le signal d'arrêt.
# --preload : la table est créée une seule fois, avant de lancer les 2 workers
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--preload", "--access-logfile", "-", "app:app"]
