from sqlmodel import SQLModel, create_engine
from loguru import logger
import os

base_dir = "src"
db_dir = os.path.join(base_dir, "data/sqlite")
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
    
    # Création des tables
    logger.info("Initialisation de la base de données")
    SQLModel.metadata.create_all(engine)
    logger.info("Base de données initialisée avec succès")

if __name__ == "__main__":
    init_db()