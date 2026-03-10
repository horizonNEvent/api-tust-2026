from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
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

endpoint_url = "http://localhost:4566" if os.getenv("USE_LOCALSTACK", "true").lower() == "true" else None
req_args = {
    "region_name": os.getenv("AWS_REGION", "us-east-1"),
    "endpoint_url": endpoint_url,
}
if endpoint_url:
    req_args["aws_access_key_id"] = "test"
    req_args["aws_secret_access_key"] = "test"

sqs_client = boto3.client('sqs', **req_args)

if endpoint_url:
    SQS_QUEUE_URL = f"http://sqs.us-east-1.localhost.localstack.cloud:4566/000000000000/TUST-Inbound-Queue"
    SQS_QUEUE_URL_OCR = f"http://sqs.us-east-1.localhost.localstack.cloud:4566/000000000000/TUST-Queue-OCR"
else:
    SQS_QUEUE_URL = os.getenv("SQS_QUEUE_URL", "FAKE_URL")
    SQS_QUEUE_URL_OCR = os.getenv("SQS_QUEUE_URL_OCR", "FAKE_URL_OCR")

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

# Configuração de Templates
templates = Jinja2Templates(directory="api/templates")

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
    return {"message": "Bem-vindo à API Tust KEDA 2026. Acesse /admin/ para gerenciar robôs."}

# --- Interface Administrativa (HTML) ---

@app.get("/admin/", response_class=HTMLResponse)
def admin_page(request: Request, db: Session = Depends(get_db)):
    configs = db.query(RobotConfig).all()
    # Converte para dict para facilitar o tojson no template
    configs_list = [c.__dict__ for c in configs]
    # Remove estados internos do SQLAlchemy que podem quebrar o JSON
    for c in configs_list:
        c.pop('_sa_instance_state', None)
        
    return templates.TemplateResponse("index.html", {"request": request, "configs": configs_list})

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

@app.put("/configs/{config_id}", response_model=RobotConfigResponse)
def update_config(config_id: int, config_data: RobotConfigCreate, db: Session = Depends(get_db)):
    db_config = db.query(RobotConfig).filter(RobotConfig.id == config_id).first()
    if not db_config:
        raise HTTPException(status_code=404, detail="Configuração não encontrada")
    
    for key, value in config_data.model_dump().items():
        setattr(db_config, key, value)
    
    db.commit()
    db.refresh(db_config)
    return db_config

@app.delete("/configs/{config_id}")
def delete_config(config_id: int, db: Session = Depends(get_db)):
    db_config = db.query(RobotConfig).filter(RobotConfig.id == config_id).first()
    if not db_config:
        raise HTTPException(status_code=404, detail="Configuração não encontrada")
    
    db.delete(db_config)
    db.commit()
    return {"message": "Configuração removida com sucesso"}

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
        
        # --- ROTEAMENTO INTELIGENTE (DUAL QUEUE) ---
        # Robôs pesados vão para a fila OCR. Robôs leves vão para a fila Padrão.
        if config.robot_type.lower() in ['light']:
            target_queue = SQS_QUEUE_URL_OCR
        else:
            target_queue = SQS_QUEUE_URL
            
        try:
            sqs_client.send_message(
                QueueUrl=target_queue,
                MessageBody=json.dumps(payload)
            )
        except Exception as e:
            print(f"Erro ao postar na Fila SQS: {e}")
            raise HTTPException(status_code=500, detail="Erro de infraestrutura SQS")
            
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
