from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from core.database import Base


class Empresa(Base):
    __tablename__ = 'empresas'
    
    id = Column(Integer, primary_key=True, index=True)
    codigo_ons = Column(String, unique=True, index=True)
    nome_empresa = Column(String)
    cnpj = Column(String, nullable=True)
    base = Column(String, default="AETE")
    ativo = Column(Boolean, default=True)

class Transmissora(Base):
    __tablename__ = 'transmissoras'
    
    id = Column(Integer, primary_key=True, index=True)
    cnpj = Column(String, unique=True, index=True)
    codigo_ons = Column(String, index=True)
    sigla = Column(String)
    nome = Column(String)
    grupo = Column(String)
    dados_json = Column(String) 
    ultima_atualizacao = Column(DateTime, server_default=func.now())

class RobotConfig(Base):
    __tablename__ = 'robot_configs'
    
    id = Column(Integer, primary_key=True, index=True)
    robot_type = Column(String)
    base = Column(String, index=True) 
    label = Column(String)
    username = Column(String)
    password = Column(String)
    agents_json = Column(String) 
    active = Column(Boolean, default=True)
    schedule_time = Column(String, nullable=True) # HH:MM

class RobotExecution(Base):
    __tablename__ = 'robot_executions'
    
    id = Column(Integer, primary_key=True, index=True)
    robot_config_id = Column(Integer, ForeignKey('robot_configs.id'), index=True)
    start_time = Column(DateTime, server_default=func.now())
    end_time = Column(DateTime, nullable=True)
    status = Column(String)  # "PENDING", "RUNNING", "SUCCESS", "FAILED"
    logs = Column(String, nullable=True)
    error_message = Column(String, nullable=True)
    trigger_type = Column(String)  # "MANUAL" (Manual) ou "SCHEDULED" (Agendado)
    s3_path = Column(String, nullable=True)

class DocumentRegistry(Base):
    __tablename__ = 'document_registry'
    
    id = Column(Integer, primary_key=True, index=True)
    execution_id = Column(Integer, ForeignKey('robot_executions.id'), index=True)
    filename = Column(String)
    s3_url = Column(String)
    file_hash = Column(String, index=True)
    cnpj_extracted = Column(String, index=True)
    competence_extracted = Column(String, index=True)
    invoice_value = Column(String, nullable=True)
    ons_code = Column(String, nullable=True)
    agent_name = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
