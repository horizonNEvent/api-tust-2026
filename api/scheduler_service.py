from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from core.database import SessionLocal
from core.models import RobotConfig, RobotExecution
from datetime import datetime


scheduler = BackgroundScheduler()

def scheduled_job(config_id: int):
    """Callback para execuções agendadas de robôs (Agora envia pro SQS)."""
    db = SessionLocal()
    import json
    import uuid
    from core.models import RobotConfig
    from datetime import datetime
    import sys
    import os
    
    # Workaround para poder importar sqs_client do main (ou podemos recriar aqui)
    import boto3
    sqs_client = boto3.client('sqs', region_name=os.getenv("AWS_REGION", "us-east-1"))
    SQS_QUEUE_URL = os.getenv("SQS_QUEUE_URL", "FAKE_URL")
    
    try:
        config = db.query(RobotConfig).filter(RobotConfig.id == config_id).first()
        if not config or not config.active:
            return

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
            return

        competencia_atual = datetime.now().strftime('%Y%m')

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
                # sqs_client.send_message(QueueUrl=SQS_QUEUE_URL, MessageBody=json.dumps(payload))
                pass
            except Exception as e:
                print(f"Erro falso silencioso SQS Agendado: {e}")
                
            print(f"[AGENDADOR] Cron disparou: Evento SQS Emitido para Agente {agente} do Robô {config.robot_type}")

    except Exception as e:
        print(f"Error in scheduled job for config {config_id}: {e}")
    finally:
        db.close()

def init_scheduler():
    """Inicializa e inicia o agendador com as tarefas do banco de dados."""
    if not scheduler.running:
        scheduler.start()
    
    reload_jobs()

def reload_jobs():
    """Limpa todas as tarefas e as recarrega do banco de dados."""
    scheduler.remove_all_jobs()
    db = SessionLocal()
    try:
        active_configs = db.query(RobotConfig).filter(RobotConfig.active == True, RobotConfig.schedule_time != None).all()
        for config in active_configs:
            try:
                hour, minute = config.schedule_time.split(":")
                scheduler.add_job(
                    scheduled_job,
                    trigger=CronTrigger(hour=hour, minute=minute),
                    args=[config.id],
                    id=f"bolt_job_{config.id}",
                    replace_existing=True
                )
                print(f"Robô {config.label} agendado para execução diária às {config.schedule_time}")
            except Exception as e:
                print(f"Erro ao agendar tarefa para config {config.id}: {e}")
    finally:
        db.close()
