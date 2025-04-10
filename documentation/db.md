## Architecture

- **main.py** : Point d'entrée de l'application
- **api/routes.py** : Définition des routes de l'API
- **core/models.py** : Modèles de données
- **core/db.py** : Opérations sur la base de données
- **core/init_db.py** : Initialisation de la base de données

## Modèles de données

### WorkloadSchedule

Représente une planification de charge de travail dans la base de données.

| Attribut | Type | Description | Valeur par défaut |
|----------|------|-------------|-------------------|
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
-`schedule_id` : ID de la planification à supprimer

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
uvicorn src.main:app --reload
```

L'application démarrera sur `http://0.0.0.0:8000`.

## Structure des fichiers

'''
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
'''

## Dépendances principales

- FastAPI : Framework web
- SQLModel : ORM pour la base de données
- Loguru : Gestion des logs
- Uvicorn : Serveur ASGI
