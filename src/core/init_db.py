from sqlmodel import SQLModel, create_engine
from loguru import logger
import os
from core.models import WorkloadSchedule

db_dir = os.path.join("data/sqlite")
db_file = "scheduler.db"
db_path = os.path.join(db_dir, db_file)
sqlite_url = f"sqlite:///{db_path}"
engine = create_engine(sqlite_url, echo=True)

def init_db():
    # Vérification et création des dossiers si nécessaire
    if not os.path.exists(db_dir):
        logger.info(f"Création des dossiers: {db_dir}")
        os.makedirs(db_dir, exist_ok=True)
    else:
        logger.info(f"Le dossier {db_dir} existe déjà")

    logger.info(f"Chemin de la base de données: {db_path}")

    # Création des tables
    logger.info("Initialisation de la base de données")
    try:
        SQLModel.metadata.create_all(engine)
        logger.info(f"Base de données {WorkloadSchedule.__tablename__} initialisée avec succès")
    except Exception as e:
        logger.error(f"Erreur lors de l'initialisation de la base de données: {e}")

if __name__ == "__main__":
    init_db()