import requests
import os
import sys
import json
from datetime import datetime
import time
import random
import urllib3

# Desativa avisos de SSL inseguro (o site da Firminopolis está com certificado expirado)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Adiciona o diretório raiz ao path para encontrar a classe pai base_robot
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from base_robot import BaseRobot

class FirminopolisRobot(BaseRobot):
    def __init__(self):
        # Inicializa o robô chamando o BaseRobot com a flag "firminopolis"
        super().__init__("firminopolis")
        self.session = requests.Session()
        self.base_url = "https://www.ltfirminopolis.com.br"
        
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/xml,text/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
            'Referer': f'{self.base_url}/pantanal.html'
        }

    def carregar_referencia_empresas(self):
        """Carrega o arquivo JSON local de de-para do ONS."""
        try:
            arquivo_json = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'Data', 'empresas.json')
            with open(arquivo_json, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"Erro ao carregar referencia de empresas: {e}")
            return {}

    # === Camada de Resiliência: Tenacity Retry Logic ===
    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1.5, min=2, max=15),
        retry=retry_if_exception_type((requests.exceptions.ConnectionError, requests.exceptions.Timeout)),
        reraise=True
    )
    def baixar_titulo(self, empresa_nome, cod_ons, nome_ons):
        # Jitter de gentileza para não dar DDoS
        time.sleep(random.uniform(1.0, 3.0))
        
        self.logger.info(f"[{empresa_nome}] Processando ONS {cod_ons} ({nome_ons})...")

        # Determina pasta de destino (Base inherited + Empresa/ONS)
        output_path = os.path.join(self.get_output_path(), empresa_nome, str(cod_ons))
        os.makedirs(output_path, exist_ok=True)
        
        url = f"{self.base_url}/download.php"
        params = {
            'tswcode': cod_ons,
            'file': f'{cod_ons}.xml'
        }
        
        try:
            # Observação: verify=False aqui porque a Firminópolis costuma ter SSL expirado
            response = self.session.get(url, params=params, headers=self.headers, verify=False, timeout=30)
            
            if response.status_code == 200 and len(response.text.strip()) > 50:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"NFe_{nome_ons}_{timestamp}.xml".replace(" ", "_")
                filepath = os.path.join(output_path, filename)
                
                with open(filepath, 'wb') as f:
                    f.write(response.content)
                
                self.logger.info(f"    [OK] XML baixado com sucesso: {filename}")
                return True
            else:
                self.logger.warning(f"    [WARN] Erro ao baixar arquivo para {nome_ons}. HTTP {response.status_code} | Tamanho: {len(response.text)}")
                return False
                
        except Exception as e:
            self.logger.error(f"    [ERROR] Erro fatal na conexão para ONS {cod_ons}: {e}")
            raise # Lança para o Tenacity capturar e fazer o Retry se for problema de conexão

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
                
                try:
                    self.baixar_titulo(empresa_nome, codigo_ons, nome_ons)
                except Exception as e:
                    self.logger.error(f"💥 Falha definitiva ao processar ONS {codigo_ons} após retentativas: {e}")

if __name__ == "__main__":
    bot = FirminopolisRobot()
    bot.run()
