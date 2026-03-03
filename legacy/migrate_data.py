import sqlite3
import os
from database import SessionLocal, engine, Base
from models import Empresa, Transmissora

def migrate():
    # Ensure tables exist
    Base.metadata.create_all(bind=engine)
    
    old_db_path = "Tust-AETE/sql_app.db"
    if not os.path.exists(old_db_path):
        print(f"Old database not found at {old_db_path}")
        return

    old_conn = sqlite3.connect(old_db_path)
    old_cursor = old_conn.cursor()

    new_db = SessionLocal()

    try:
        # Migrate Empresas
        print("Migrating Empresas...")
        old_cursor.execute("SELECT id, codigo_ons, nome_empresa, cnpj, base, ativo FROM empresas")
        for row in old_cursor.fetchall():
            emp = Empresa(
                # id=row[0], # Let SQLALchemy handle IDs if possible, or force them
                codigo_ons=row[1],
                nome_empresa=row[2],
                cnpj=row[3],
                base=row[4],
                ativo=bool(row[5])
            )
            # Check if exists
            exists = new_db.query(Empresa).filter(Empresa.codigo_ons == row[1]).first()
            if not exists:
                new_db.add(emp)

        # Migrate Transmissoras
        print("Migrating Transmissoras...")
        # Note: Original table might be named 'transmissora' (singular)
        try:
            old_cursor.execute("SELECT id, cnpj, codigo_ons, sigla, nome, grupo, dados_json, ultima_atualizacao FROM transmissora")
            for row in old_cursor.fetchall():
                trans = Transmissora(
                    cnpj=row[1],
                    codigo_ons=row[2],
                    sigla=row[3],
                    nome=row[4],
                    grupo=row[5],
                    dados_json=row[6]
                    # ultima_atualizacao handling...
                )
                exists = new_db.query(Transmissora).filter(Transmissora.cnpj == row[1]).first()
                if not exists:
                    new_db.add(trans)
        except sqlite3.OperationalError:
            print("Table 'transmissora' not found or has different schema in old DB.")

        new_db.commit()
        print("Migration completed successfully.")

    except Exception as e:
        print(f"Error during migration: {e}")
        new_db.rollback()
    finally:
        old_conn.close()
        new_db.close()

if __name__ == "__main__":
    migrate()
