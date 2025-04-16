# Documentation du Workload Scheduler

## Getting Started

### Prérequis

Avant de commencer, assurez-vous d'avoir installé :

- Python 3.8 ou supérieur
- pip (gestionnaire de paquets Python)
- Git (optionnel, pour cloner le dépôt)

### Installation

1. **Cloner le dépôt** (ou télécharger les fichiers source)

   ```bash
   git clone https://github.com/votre-repo/workload-scheduler.git
   cd workload-scheduler
   ```

2. **Créer un environnement virtuel**

   ```bash
   python -m venv venv
   ```

3. **Activer l'environnement virtuel**

   - Sous Windows:

     ```bash
     venv\Scripts\activate
     ```

   - Sous macOS/Linux:

     ```bash
     source venv/bin/activate
     ```

4. **Installer les dépendances**

   ```bash
   pip install -r requirements.txt
   ```

   Si le fichier requirements.txt n'existe pas, créez-le avec les dépendances suivantes :

   ```

   fastapi>=0.100.0
   sqlmodel>=0.0.8
   loguru>=0.7.0
   uvicorn>=0.23.0
   python-dateutil>=2.8.2
   pydantic>=2.0.0
   kubernetes>=25.3.0
   ```

5. **Initialiser la base de données**

   ```bash
   python src/core/init_db.py
   ```

### Exécution de l'application

1. **Démarrer le serveur**

   ```bash
   task run-dev
   ```

2. **Accéder à la documentation API**
   Ouvrez votre navigateur et accédez à :

   ```
   http://localhost:8000/docs
   ```

   Cette interface Swagger vous permettra de tester toutes les fonctionnalités de l'API.

### Utilisation de l'API

1. **Créer une nouvelle planification**
   - Méthode : POST
   - Endpoint : `/schedules`
   - Corps de la requête :

     ```json
     {
       "name": "Backup Database",
       "start_time": "2025-04-20T10:00:00",
       "end_time": "2025-04-20T11:00:00",
       "status": "scheduled",
       "active": true
     }
     ```

2. **Récupérer toutes les planifications**
   - Méthode : GET
   - Endpoint : `/schedules`

3. **Supprimer une planification**
   - Méthode : DELETE
   - Endpoint : `/schedules/{schedule_id}`

### Résolution des problèmes courants

1. **Erreur d'accès à la base de données**
   - Vérifiez que le répertoire `data/sqlite` existe
   - Vérifiez les permissions du répertoire

2. **Le serveur ne démarre pas**
   - Vérifiez que le port 8000 n'est pas déjà utilisé
   - Vérifiez que toutes les dépendances sont installées correctement

## Architecture

L'application est structurée selon les principes de séparation des responsabilités :

- **main.py** : Point d'entrée de l'application
- **api/routes.py** : Définition des routes de l'API
- **core/models.py** : Modèles de données
- **core/db.py** : Opérations sur la base de données
- **core/init_db.py** : Initialisation de la base de données

## Modèles de données

### WorkloadSchedule

Représente une planification de charge de travail dans la base de données.

| Attribut | Type | Description | Valeur par défaut |
|----------|------|-------------|------------------|
| id | Optional[int] | Identifiant unique | None (auto-incrémenté) |
| name | str | Nom de la charge de travail | - |
| start_time | datetime | Date et heure de début | - |
| end_time | datetime | Date et heure de fin | - |
| status | str | Statut de la planification | "scheduled" |
| active | bool | Indique si la planification est active | True |

### WorkloadScheduleCreate

Modèle Pydantic utilisé pour la validation des données lors de la création d'une nouvelle planification.

## API Endpoints

### GET /schedules

Récupère toutes les planifications de charge de travail.
**Réponse** : Liste de `WorkloadSchedule`

### POST /schedules

Crée une nouvelle planification de charge de travail.
**Corps de la requête** : Objet `WorkloadScheduleCreate`
**Réponse** : `{"status": "created"}`

### DELETE /schedules/{schedule_id}

Supprime une planification de charge de travail par son ID.
**Paramètres de chemin** :

- `schedule_id` : ID de la planification à supprimer
**Réponse** : `{"status": "deleted"}`
**Erreur** : 404 si la planification n'existe pas

## Opérations de base de données

### add_schedule

Ajoute une nouvelle planification à la base de données.

### get_all_schedules

Récupère toutes les planifications de la base de données.

### delete_schedule

Supprime une planification par son ID.

## Configuration

### Base de données

L'application utilise SQLite avec le fichier de base de données stocké à `data/sqlite/scheduler.db`.

### Serveur

Le serveur est configuré pour s'exécuter sur le port 8000 et est accessible depuis n'importe quelle adresse IP (0.0.0.0).

## Démarrage de l'application

Pour démarrer l'application, exécutez :

```bash
python main.py
```

L'application démarrera sur `http://0.0.0.0:8000`.

## Structure des fichiers

```
.
├── main.py
├── static/
├── data/
│   └── sqlite/
│       └── scheduler.db
└── src/
    ├── api/
    │   └── routes.py
    └── core/
        ├── db.py
        ├── init_db.py
        └── models.py
```

## Dépendances principales

- FastAPI : Framework web

- SQLModel : ORM pour la base de données
- Loguru : Gestion des logs
- Uvicorn : Serveur ASGI
- Kubernetes : Client pour l'interaction avec Kubernetes (non utilisé dans l'extrait de code fourni)
