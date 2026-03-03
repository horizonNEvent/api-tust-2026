import os
import time
import json
from dotenv import load_dotenv
from core.database import SessionLocal, engine, Base
from core.models import RobotConfig, RobotExecution, DocumentRegistry
from legacy.robot_runner import runner

load_dotenv(override=True)

# Inicializa o banco (Garante que as tabelas existem)
Base.metadata.create_all(bind=engine)

def cleanup_db():
    db = SessionLocal()
    # Limpa registros antigos para o teste ficar limpo
    db.query(DocumentRegistry).delete()
    db.query(RobotExecution).delete()
    db.query(RobotConfig).filter(RobotConfig.robot_type == "cnt").delete()
    db.commit()
    db.close()

def setup_cnt_config():
    db = SessionLocal()
    agents_re = {
        "4313": "BRJA", "4314": "BRJB", "3430": "CECA", "3431": "CECB",
        "3432": "CECC", "4415": "CECD", "4315": "CECE", "4316": "CECF",
        "3502": "ITA1", "3497": "ITA2", "3503": "ITA3", "3530": "ITA4",
        "3498": "ITA5", "3531": "ITA6", "3532": "ITA7", "3537": "ITA8", "3538": "ITA9"
    }
    
    config = RobotConfig(
        robot_type="cnt",
        label="Robô CNT - Base RE",
        base="RE",
        agents_json=json.dumps(agents_re),
        active=True
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    config_id = config.id
    db.close()
    return config_id

import json

def run_test():
    print("--- INICIANDO TESTE DE PIPELINE INTELIGENTE (CHECK DE HASH) ---")
    cleanup_db()
    config_id = setup_cnt_config()
    db = SessionLocal()

    # 1. PRIMEIRA EXECUÇÃO (Deve baixar e salvar tudo)
    print("\n1. Primeira Rodada: Capturando documentos pela primeira vez...")
    execution1 = RobotExecution(robot_config_id=config_id, status="PENDING", trigger_type="MANUAL")
    db.add(execution1)
    db.commit()
    db.refresh(execution1)
    
    runner.run(execution1.id)
    
    docs_after_1 = db.query(DocumentRegistry).count()
    print(f"\nResultado 1: Foram registrados {docs_after_1} novos documentos no banco.")

    # 2. SEGUNDA EXECUÇÃO (Deve detectar duplicidade de HASH e pular tudo)
    print("\n2. Segunda Rodada: Rodando novamente para testar a detecção de duplicidade...")
    execution2 = RobotExecution(robot_config_id=config_id, status="PENDING", trigger_type="MANUAL")
    db.add(execution2)
    db.commit()
    db.refresh(execution2)
    
    runner.run(execution2.id)
    
    docs_after_2 = db.query(DocumentRegistry).count()
    print(f"\nResultado 2: Total de documentos no banco: {docs_after_2}")
    print("--- TESTE FINALIZADO ---")
    
    if docs_after_1 == docs_after_2:
        print("\nSUCESSO: A Idempotência funcionou! Nenhum arquivo duplicado foi inserido.")
    else:
        print("\nFALHA: O sistema inseriu arquivos duplicados.")

    db.close()

if __name__ == "__main__":
    run_test()
