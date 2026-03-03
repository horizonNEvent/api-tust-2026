import subprocess
import os
import json
import shutil
from datetime import datetime
from sqlalchemy.orm import Session
from database import SessionLocal
from models import RobotConfig, RobotExecution, DocumentRegistry
from s3_service import s3_service
from xml_utils import extract_xml_data

class RobotRunner:
    def __init__(self, robots_root, downloads_root):
        self.robots_root = robots_root
        self.downloads_root = downloads_root

    def run(self, execution_id: int):
        """Executa um robô baseado no ID de execução."""
        db = SessionLocal()
        execution = db.query(RobotExecution).filter(RobotExecution.id == execution_id).first()
        if not execution:
            db.close()
            return

        config = db.query(RobotConfig).filter(RobotConfig.id == execution.robot_config_id).first()
        
        execution.status = "RUNNING"
        execution.start_time = datetime.now()
        db.commit()

        # Isolar diretório de saída para esta execução
        run_id = f"run_{execution_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        output_dir = os.path.join(self.downloads_root, run_id)
        os.makedirs(output_dir, exist_ok=True)

        try:
            # Preparar comando
            script_path = os.path.join(self.robots_root, f"{config.robot_type.lower()}.py")
            if not os.path.exists(script_path):
                raise Exception(f"Script não encontrado: {script_path}")

            cmd = ["python", script_path, "--output_dir", output_dir]
            
            # Mapear login/senha apenas se existirem na tabela
            if config.username: cmd.extend(["--user", config.username])
            if config.password: cmd.extend(["--password", config.password])
            
            # Inteligência: Extrair apenas as chaves (códigos ONS) do JSON de agentes
            try:
                agents_data = json.loads(config.agents_json or "{}")
                if isinstance(agents_data, dict):
                    agents_list = list(agents_data.keys())
                elif isinstance(agents_data, list):
                    agents_list = agents_data
                else:
                    agents_list = []
                
                if agents_list:
                    cmd.extend(["--agente", ",".join(agents_list)])
            except Exception as e:
                print(f"Alerta: Erro ao processar agents_json para a execução {execution_id}: {e}")

            # Future: add --competencia if passed

            print(f"Executing: {' '.join(cmd)}")
            
            # Run robot
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )

            full_logs = []
            for line in process.stdout:
                print(line.strip())
                full_logs.append(line)
            
            process.wait()
            execution.logs = "".join(full_logs)

            if process.returncode != 0:
                raise Exception(f"O robô falhou com código de saída {process.returncode}")

            # Pós-processamento: Organizar e fazer upload para o S3
            self._process_results(db, execution, output_dir)

            execution.status = "SUCCESS"
        except Exception as e:
            execution.status = "FAILED"
            execution.error_message = str(e)
        finally:
            execution.end_time = datetime.now()
            db.commit()
            db.close()
            # Opcional: limpeza do output_dir se necessário
            # shutil.rmtree(output_dir, ignore_errors=True)

    def _process_results(self, db, execution, output_dir):
        """
        Escaneia o output_dir em busca de arquivos, extrai metadados de XMLs, 
        e faz o upload para o S3 na estrutura desejada.
        """
        for root, dirs, files in os.walk(output_dir):
            for filename in files:
                file_path = os.path.join(root, filename)
                
                # Extração de metadados (especialmente para XMLs)
                metadata = {}
                if filename.lower().endswith(".xml"):
                    metadata = extract_xml_data(file_path, db_session=db)
                    
                    # Verificação de duplicidade por HASH (Idempotência)
                    file_hash = metadata.get("hash")
                    if file_hash:
                        existing = db.query(DocumentRegistry).filter(DocumentRegistry.file_hash == file_hash).first()
                        if existing:
                            print(f"Alerta: Documento {filename} ignorado. HASH já existente no banco ({file_hash[:12]}...)")
                            continue
                
                # Determinar estrutura S3: [Competência] / [Agente] / [Pasta Transmissora] / [Arquivo]
                # Fallbacks padrão se a extração de metadados falhar ou não for XML
                competence = metadata.get("competencia", "unknown_competence")
                agent = metadata.get("agent_name", "unknown_agent")
                transmissora = metadata.get("transmissora", "unknown_transmissora")

                s3_url = s3_service.upload_file(
                    file_path, 
                    competence, 
                    agent, 
                    transmissora, 
                    filename
                )

                if s3_url:
                    doc = DocumentRegistry(
                        execution_id=execution.id,
                        filename=filename,
                        s3_url=s3_url,
                        file_hash=metadata.get("hash"),
                        cnpj_extracted=metadata.get("cnpj"),
                        competence_extracted=competence,
                        invoice_value=metadata.get("valor"),
                        ons_code=metadata.get("ons_code"),
                        agent_name=agent
                    )
                    db.add(doc)
        db.commit()

# Inicializar executor (caminhos do .env ou padrões locais)
runner = RobotRunner(
    robots_root=os.getenv("ROBOTS_ROOT_PATH", "./Robots"),
    downloads_root=os.getenv("DOWNLOADS_ROOT_PATH", "./downloads")
)
