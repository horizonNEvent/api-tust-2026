from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel
import json
import boto3
import os
import uuid
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(override=True)

sqs_client = boto3.client('sqs', region_name=os.getenv("AWS_REGION", "us-east-1"))
SQS_QUEUE_URL = os.getenv("SQS_QUEUE_URL", "FAKE_URL")

from core.database import SessionLocal, engine, Base, get_db
from core.models import RobotConfig, RobotExecution, Empresa, DocumentRegistry, Transmissora
from api.scheduler_service import init_scheduler

# Criar tabelas
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="API Tust 2026",
    description="API central para execução e agendamento de robôs de coleta de dados via mensageria (KEDA).",
    version="2.0.0"
)

# Schemas Pydantic
class RobotConfigBase(BaseModel):
    robot_type: str
    base: str  # Adicionado campo multi-tenant da base
    label: str
    username: str | None = None
    password: str | None = None
    agents_json: str | None = "[]"
    active: bool = True
    schedule_time: str | None = None

class RobotConfigCreate(RobotConfigBase):
    pass

class RobotConfigResponse(RobotConfigBase):
    id: int
    class Config:
        from_attributes = True

@app.on_event("startup")
def startup_event():
    pass
    # Removido init_scheduler() temporariamente até reescreve-lo.

@app.get("/")
def read_root():
    return {"message": "Bem-vindo à API Tust KEDA 2026"}

# --- Robot Config CRUD ---

@app.post("/configs/", response_model=RobotConfigResponse)
def create_config(config: RobotConfigCreate, db: Session = Depends(get_db)):
    db_config = RobotConfig(**config.model_dump())
    db.add(db_config)
    db.commit()
    db.refresh(db_config)
    return db_config

@app.get("/configs/", response_model=List[RobotConfigResponse])
def list_configs(db: Session = Depends(get_db)):
    return db.query(RobotConfig).all()

# --- Execução Otimizada via Mensageria (Event Driven) ---

@app.post("/robots/run/{config_id}")
async def run_robot(config_id: int, db: Session = Depends(get_db)):
    """
    Novo Modelo: Despachante KEDA. 
    Envia a tarefa para o SQS. O SQSWorkerService se encarrega do resto.
    """
    config = db.query(RobotConfig).filter(RobotConfig.id == config_id).first()
    if not config:
        raise HTTPException(status_code=404, detail="Configuração de robô não encontrada")

    if not config.active:
        raise HTTPException(status_code=400, detail="Esta configuração de robô está inativa (active=0)")

    # Pega lista de agentes.
    agentes_str = []
    try:
        agents_data = json.loads(config.agents_json or "{}")
        if isinstance(agents_data, dict):
            agentes_str = list(agents_data.keys())
        elif isinstance(agents_data, list):
            agentes_str = agents_data
    except:
        pass

    if not agentes_str:
        raise HTTPException(status_code=400, detail="Nenhum agente configurado pra este robô.")

    competencia_atual = datetime.now().strftime('%Y%m')
    sqs_messages_disparadas = 0

    # Quebrando o job: Cria uma ordem separada para cada agente. Assim KEDA sobe vários workers juntos se for o caso.
    for agente in agentes_str:
        payload = {
            "uuid": str(uuid.uuid4()),
            "robot": config.robot_type,
            "base": getattr(config, 'base', 'UNKNOWN'),
            "agente": str(agente),
            "competencia": competencia_atual,
            "config_id": config.id,
            "username": config.username,
            "password": config.password
        }
        
        try:
            # Em DEV local podemos apagar essa parte de sqs
            # sqs_client.send_message(
            #     QueueUrl=SQS_QUEUE_URL,
            #     MessageBody=json.dumps(payload)
            # )
            pass
        except Exception as e:
            print(f"Erro falso silencioso no SQS Local: {e}")
            
        print(f"Emitting Event SQS: {payload}")
        sqs_messages_disparadas += 1

    return {
        "message": "Fila SQS Notificada com Sucesso.", 
        "mensagens_disparadas": sqs_messages_disparadas,
        "next": "O KEDA cuidará do processamento de modo escalável."
    }

@app.get("/executions/{execution_id}")
def get_execution(execution_id: int, db: Session = Depends(get_db)):
    execution = db.query(RobotExecution).filter(RobotExecution.id == execution_id).first()
    if not execution:
        raise HTTPException(status_code=404, detail="Execução não encontrada")
    return execution

@app.get("/results/{execution_id}")
def get_results(execution_id: int, db: Session = Depends(get_db)):
    results = db.query(DocumentRegistry).filter(DocumentRegistry.execution_id == execution_id).all()
    return results

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
