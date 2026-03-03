from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from core.database import SessionLocal
from core.models import RobotConfig, RobotExecution
from datetime import datetime


scheduler = BackgroundScheduler()

def scheduled_job(config_id: int):
    """Callback para execuções agendadas de robôs."""
    db = SessionLocal()
    try:
        execution = RobotExecution(
            robot_config_id=config_id,
            status="PENDING",
            trigger_type="SCHEDULED"
        )
        db.add(execution)
        db.commit()
        db.refresh(execution)
        
        # Executar o robô
        runner.run(execution.id)
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
