FROM python:3.12.10-alpine
WORKDIR /app

# Installation des dépendances
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copie du code source
COPY src .

# Création des répertoires nécessaires
RUN mkdir -p data/sqlite

# Exposition du port
EXPOSE 8000

# Commande de démarrage
CMD ["python", "main.py"]
