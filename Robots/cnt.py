import requests
import os
import sys
from datetime import datetime
import json
import time
import random

# Biblioteca Tenacity para a resiliência corporativa
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Adiciona o diretório raiz ao path para encontrar o base_robot
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from base_robot import BaseRobot

class CNTRobot(BaseRobot):
    def __init__(self):
        # Inicializa a base com o nome 'cnt'
        super().__init__("cnt")
        
        # Só inicializamos a Session. A biblioteca Tenacity e KEDA cuidarão dos Retries
        self.session = requests.Session()
        
        self.url_principal = "https://cntgo.com.br/faturas.html"
        self.url_form = "https://cntgo.com.br/form.php"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            "Connection": "keep-alive"
        }

    def carregar_referencia_empresas(self):
        """Carrega o mapa de ONS -> Nomes para organização."""
        try:
            # Observação: Como fomos movidos para Robots/, o Data/ está 1 nível acima
            arquivo_json = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'Data', 'empresas.json')
            with open(arquivo_json, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"Erro ao carregar referencia de empresas: {e}")
            return {}

    # --- Lógica de Resiliência Isolada com Tenacity ---
    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1.5, min=2, max=15),
        retry=retry_if_exception_type((requests.exceptions.ConnectionError, requests.exceptions.Timeout)),
        reraise=True
    )
    def _requisicao_login_download(self, codigo_ons):
        """Encapsula as requisições com Circuit Breaker e Exponential Backoff"""
        # 1. Bater na home para pegar cookies
        self.logger.info("  -> Obtendo cookies da Home...")
        self.session.get(self.url_principal, headers=self.headers, timeout=20)
        
        # 2. Postar o formulário com o código ONS
        self.logger.info("  -> Submetendo requisição do Form...")
        form_data = {"code": str(codigo_ons)}
        resp = self.session.post(self.url_form, headers=self.headers, data=form_data, timeout=30)
        
        return resp

    def baixar_fatura(self, codigo_ons, empresa_base, nome_ons):
        """Lógica específica do site CNT para baixar o XML."""
        # Jitter de gentileza para não dar DDoS se rodarem 10 robôs juntos
        time.sleep(random.uniform(1.0, 3.0))
        
        try:
            self.logger.info(f"[{empresa_base}] Verificando ONS {codigo_ons} ({nome_ons})...")
            
            resp = self._requisicao_login_download(codigo_ons)
            
            if resp.status_code == 200 and len(resp.content) > 100:
                # Determina pasta de destino (Base inherited + Empresa/ONS)
                output_path = os.path.join(self.get_output_path(), empresa_base, str(codigo_ons))
                os.makedirs(output_path, exist_ok=True)
                
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"NFe_{nome_ons}_{timestamp}.xml".replace(" ", "_")
                final_file = os.path.join(output_path, filename)
                
                with open(final_file, "wb") as f:
                    f.write(resp.content)
                
                self.logger.info(f"✅ XML baixado com sucesso: {filename}")
                return True
            else:
                self.logger.warning(f"❌ Não foi possível obter fatura para ONS {codigo_ons}. (Status: {resp.status_code}, Tamanho: {len(resp.content)})")
                return False
                
        except Exception as e:
            self.logger.error(f"💥 Erro FATAL na conexão para ONS {codigo_ons} após todas as tentativas: {e}")
            return False

    def run(self):
        """Loop de execução principal baseado nos filtros recebidos."""
        ref_empresas = self.carregar_referencia_empresas()
        
        agentes_alvo = self.get_agents()
        
        for empresa_nome, codigos_dict in ref_empresas.items():
            if self.args.empresa and self.args.empresa.strip().upper() != empresa_nome.strip().upper():
                continue

            for codigo_ons, nome_ons in codigos_dict.items():
                if agentes_alvo and str(codigo_ons).strip() not in agentes_alvo:
                    continue
                
                # CHAVE MESTRA: Graceful Shutdown ativado a cada agente processado
                self.check_shutdown()
                
                self.baixar_fatura(codigo_ons, empresa_nome, nome_ons)

if __name__ == "__main__":
    bot = CNTRobot()
    bot.run()
