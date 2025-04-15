from sqlmodel import SQLModel, create_engine

sqlite_url = "sqlite:///data/sqlite/scheduler.db"
engine = create_engine(sqlite_url, echo=True)

def init_db():
    SQLModel.metadata.create_all(engine)
