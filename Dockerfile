FROM python:3.9-slim

WORKDIR /app

# Installation des dépendances
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copie du code source
COPY . .

# Création des répertoires nécessaires
RUN mkdir -p data/sqlite

# Exposition du port
EXPOSE 8000

# Commande de démarrage
CMD ["python", "main.py"]
