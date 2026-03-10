import requests
import json
import os
import sys
import time
import random
from datetime import datetime
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Adiciona o diretório raiz ao path para encontrar a classe pai base_robot
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from base_robot import BaseRobot

class TropicaliaRobot(BaseRobot):
    """
    Robô para Portal Tropicalia, herdando do BaseRobot para integração TUST Cloud Native.
    """
    def __init__(self):
        super().__init__("tropicalia")
        
        # Headers Fixos (A API deles valida o User-Agent e a Origin)
        self.headers = {
            "accept": "*/*",
            "accept-language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            "content-type": "application/json",
            "origin": "https://nf-tropicalia-transmissora.cust.app.br",
            "referer": "https://nf-tropicalia-transmissora.cust.app.br/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        }
        self.api_url = "https://ms-site.cap-tropicalia.cust.app.br/site/usuaria"

    def carregar_referencia_empresas(self):
        """Carrega o arquivo auxiliar empresas.json."""
        try:
            arquivo_json = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'Data', 'empresas.json')
            with open(arquivo_json, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"Erro ao carregar referencia de empresas: {e}")
            return {}

    def obter_competencia_alvo(self):
        """
        No padão do Worker, a competência vem do KEDA em YYYYMM (ex: 202603).
        A Tropicalia exige: JANEIRO-2026.
        """
        if self.args.competencia:
            try:
                c = self.args.competencia.replace('/', '').replace('-', '')
                dt = datetime(year=int(c[:4]), month=int(c[4:6]), day=1)
            except:
                self.logger.warning(f"Formato de competência inválido: {self.args.competencia}. Usando atual.")
                dt = datetime.now()
        else:
            # Automático: Mês base
            dt = datetime.now()

        meses_pt = {
            1: "JANEIRO", 2: "FEVEREIRO", 3: "MARÇO", 4: "ABRIL",
            5: "MAIO", 6: "JUNHO", 7: "JULHO", 8: "AGOSTO",
            9: "SETEMBRO", 10: "OUTUBRO", 11: "NOVEMBRO", 12: "DEZEMBRO"
        }
        
        return f"{meses_pt[dt.month]}-{dt.year}"

    # === Blindagem Tenacity ===
    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1.5, min=2, max=15),
        retry=retry_if_exception_type((requests.exceptions.ConnectionError, requests.exceptions.Timeout)),
        reraise=True
    )
    def download_file(self, url, filepath):
        """Baixa arquivo e loga resultado (com exponential backoff para links caídos)."""
        try:
            r = requests.get(url, timeout=30)
            if r.status_code == 200:
                with open(filepath, 'wb') as f:
                    f.write(r.content)
                self.logger.info(f"    [OK] Salvo: {os.path.basename(filepath)}")
                return True
            else:
                self.logger.warning(f"    [WARN] Falha S3 Tropicalia HTTP {r.status_code} para url: {url}")
        except Exception as e:
            self.logger.error(f"    [ERRO] Falha conexão de download da Tropicalia: {e}")
            raise # Joga erro para a resiliência Tenacity retentar
        return False

    # === Blindagem Tenacity ===
    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1.5, min=2, max=15),
        retry=retry_if_exception_type((requests.exceptions.ConnectionError, requests.exceptions.Timeout)),
        reraise=True
    )
    def processar_ons(self, empresa_nome, ons_code, ons_name):
        """Processa um único ONS (Agente) consultando a API deles."""
        time.sleep(random.uniform(1.0, 2.5)) # Polite scraping
        self.logger.info(f"[{empresa_nome}] Consultando ONS {ons_code} ({ons_name})...")
        
        # Define pasta de destino via TUST Path Local
        path_final = os.path.join(self.get_output_path(), empresa_nome, str(ons_code))
        os.makedirs(path_final, exist_ok=True)

        params = {"numeroOns": ons_code}
        try:
            resp = requests.get(self.api_url, params=params, headers=self.headers, timeout=30)
            if resp.status_code != 200:
                self.logger.error(f"Erro na API Tropicalia: Status {resp.status_code}")
                return

            data = resp.json()
            competencia_alvo = self.obter_competencia_alvo()
            found = False

            for item in data:
                # O site retorna com tags HTML em negrito na API (!), ex: <b>MARÇO-2026</b>
                raw = item.get('periodoContabil', '')
                periodo = BeautifulSoup(raw, 'html.parser').get_text().strip().upper()

                if periodo == competencia_alvo:
                    found = True
                    self.logger.info(f"    Fatura idêntica encontrada para {periodo}")
                    
                    base_name = f"{ons_name}_{periodo.replace('-', '_')}"

                    # Baixar arquivos disponíveis (PDF, XML, DANFE)
                    if item.get('linkDanfe'):
                        self.download_file(item['linkDanfe'], os.path.join(path_final, f"DANFE_{base_name}.pdf"))
                    if item.get('linkXml'):
                        self.download_file(item['linkXml'], os.path.join(path_final, f"XML_{base_name}.xml"))
                    if item.get('linkBoleto'):
                        self.download_file(item['linkBoleto'], os.path.join(path_final, f"BOLETO_{base_name}.pdf"))

            if not found:
                self.logger.warning(f"    Nenhuma fatura encontrada API Tropicalia (Competência: {competencia_alvo})")

        except Exception as e:
            self.logger.error(f"Falha de conexão com a API Tropicalia: {e}")
            raise # Joga para o Tenacity

    def run(self):
        """Loop principal orquestrador, filtrando as entidades"""
        ref_empresas = self.carregar_referencia_empresas()
        agentes_alvo = self.get_agents()

        for empresa_nome, codigos_dict in ref_empresas.items():
            if self.args.empresa and self.args.empresa.strip().upper() != empresa_nome.strip().upper():
                continue

            for codigo_ons, nome_ons in codigos_dict.items():
                if agentes_alvo and str(codigo_ons).strip() not in agentes_alvo:
                    continue
                
                # Desligamento Gracioso embutido
                self.check_shutdown()
                
                try:
                    self.processar_ons(empresa_nome, codigo_ons, nome_ons)
                except Exception as e:
                    self.logger.error(f"💥 Falha definitiva ao varrer Tropicalia (ONS {codigo_ons}): {e}")

if __name__ == "__main__":
    bot = TropicaliaRobot()
    bot.run()
