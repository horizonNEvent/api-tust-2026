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

class AssuRobot(BaseRobot):
    def __init__(self):
        # Inicializa o robô chamando o BaseRobot com a flag "assu"
        super().__init__("assu")
        self.session = requests.Session()
        self.base_url = "https://faturamentoassu.cesbe.com.br"
        self.headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "accept-language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            "cache-control": "max-age=0",
            "content-type": "application/x-www-form-urlencoded",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
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
    def _obter_dados_nota_recente(self, cod_ons):
        self.logger.info("  -> Extraindo referências da Nota Fiscal mais recente...")
        response = self.session.get(f"{self.base_url}/Home/Notas?iCodEmp=18&iCodOns={cod_ons}", headers=self.headers, timeout=20)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            tabela = soup.find('table', {'class': 'tableGrid'})
            if tabela:
                linhas = tabela.find_all('tr', {'class': 'dif'})
                if linhas:
                    # A última linha é a nota mais recente
                    ultima_linha = linhas[-1]
                    dados = {}
                    colunas = ultima_linha.find_all('td')
                    dados['chave_nfe'] = colunas[3].text.strip()
                    
                    # Extrai a chave NFe do link do XML
                    link_xml = ultima_linha.find('a', href=True, string='Xml')
                    if link_xml:
                        href = link_xml['href']
                        if 'sChvDoe=' in href:
                            dados['chave_nfe'] = href.split('sChvDoe=')[1]
                    return dados
        return None

    # === Camada de Resiliência: Tenacity Retry Logic ===
    @retry(
        stop=stop_after_attempt(5), 
        wait=wait_exponential(multiplier=1.5, min=2, max=15), 
        retry=retry_if_exception_type((requests.exceptions.ConnectionError, requests.exceptions.Timeout)), 
        reraise=True
    )
    def _obter_dados_boleto_recente(self, cod_ons):
        self.logger.info("  -> Extraindo Query Params do Boleto mais recente...")
        response = self.session.get(f"{self.base_url}/Home/Boletos?iCodEmp=18&iCodOns={cod_ons}", headers=self.headers, timeout=20)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            tabela = soup.find('table', {'class': 'tableGrid'})
            if tabela:
                linhas = tabela.find_all('tr', {'class': 'dif'})
                if linhas:
                    linha = linhas[-1]
                    link_download = linha.find('a', href=True)
                    if link_download:
                        href = link_download['href']
                        if '?' in href:
                            params = {}
                            for param in href.split('?')[1].split('&'):
                                if '=' in param:
                                    key, value = param.split('=')
                                    params[key] = value.replace('%20', ' ').replace('%2F', '/').replace('%3A', ':')
                            
                            # Parse dos dados essenciais
                            dados_boleto = {
                                "CodEmp": params.get('CodEmp', '18'),
                                "CodFil": params.get('CodFil', '2'),
                                "NumTit": params.get('NumTit', ''),
                                "CodTpt": params.get('CodTpt', 'DP'),
                                "VlrAbe": params.get('VlrAbe', ''),
                                "CodPor": params.get('CodPor', '341'),
                                "CodCrt": params.get('CodCrt', 'SI'),
                                "TitBan": params.get('TitBan', ''),
                                "CgcCpf": params.get('CgcCpf', '33485728000100'),
                                "CodPar": params.get('CodPar', '1'),
                                "CodOns": cod_ons,
                                "CodSel": params.get('CodSel', '1'),
                                "RecUnn": params.get('RecUnn', ''),
                                "ModBlo": params.get('ModBlo', 'FRCR223.BLO'),
                                "NomBan": params.get('NomBan', 'BANCO ITAU S.A.')
                            }
                            return dados_boleto
        return None

    @retry(
        stop=stop_after_attempt(5), 
        wait=wait_exponential(multiplier=1.5, min=2, max=15), 
        retry=retry_if_exception_type((requests.exceptions.ConnectionError, requests.exceptions.Timeout)), 
        reraise=True
    )
    def baixar_fatura(self, cod_ons, empresa_nome, nome_ons):
        # Jitter de gentileza para não travar firewall alvo
        time.sleep(random.uniform(1.0, 3.0))
        self.logger.info(f"[{empresa_nome}] Iniciando extração do ONS {cod_ons} ({nome_ons})...")
        
        # 1. Login inicial POST
        response = self.session.post(
            f"{self.base_url}/",
            data={"CodOns": cod_ons, "CodEmp": "18"},
            headers=self.headers,
            timeout=30
        )
        
        if response.status_code != 200:
            self.logger.warning(f"❌ Erro na autenticação (HTTP {response.status_code}) para ONS {cod_ons}")
            return False

        # Cria pasta usando método nativo Cloud Native herdado
        output_path = os.path.join(self.get_output_path(), empresa_nome, str(cod_ons))
        os.makedirs(output_path, exist_ok=True)
        sucesso_geral = False

        # 2. Buscar/Baixar Nota Fiscal Eletrônica (XML)
        dados_nota = self._obter_dados_nota_recente(cod_ons)
        if dados_nota and dados_nota.get('chave_nfe'):
            params_xml = {"sCodEmp": "18", "sChvDoe": dados_nota['chave_nfe']}
            
            # Baixa XML
            resp_xml = self.session.get(f"{self.base_url}/Home/WsDownloadXml", params=params_xml, headers=self.headers, timeout=30)
            if resp_xml.status_code == 200:
                xml_path = os.path.join(output_path, f"NFe_{nome_ons}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xml")
                with open(xml_path, 'wb') as f:
                    f.write(resp_xml.content)
                self.logger.info(f"✅ XML baixado com sucesso: {xml_path}")
                sucesso_geral = True

            # Baixa Documento DANFE (PDF)
            resp_danfe = self.session.get(f"{self.base_url}/Home/WsDownloadDanfe", params=params_xml, headers=self.headers, timeout=30)
            if resp_danfe.status_code == 200:
                danfe_path = os.path.join(output_path, f"DANFE_{nome_ons}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")
                with open(danfe_path, 'wb') as f:
                    f.write(resp_danfe.content)
                self.logger.info(f"✅ DANFE baixada com sucesso: {danfe_path}")

        # 3. Buscar/Baixar Boleto Final (PDF)
        dados_boleto = self._obter_dados_boleto_recente(cod_ons)
        if dados_boleto:
            resp_boleto = self.session.get(f"{self.base_url}/Home/DownloadBoleto", params=dados_boleto, headers=self.headers, timeout=30)
            if resp_boleto.status_code == 200:
                boleto_path = os.path.join(output_path, f"Boleto_{nome_ons}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")
                with open(boleto_path, 'wb') as f:
                    f.write(resp_boleto.content)
                self.logger.info(f"✅ Boleto baixado com sucesso: {boleto_path}")
                sucesso_geral = True
                
        return sucesso_geral

    def run(self):
        """Orquestrador base do robô seguindo a estrutura herdada"""
        ref_empresas = self.carregar_referencia_empresas()
        agentes_alvo = self.get_agents()
        
        for empresa_nome, codigos_dict in ref_empresas.items():
            # Filtro da classe pai (Empresa / Base)
            if self.args.empresa and self.args.empresa.strip().upper() != empresa_nome.strip().upper():
                continue

            for codigo_ons, nome_ons in codigos_dict.items():
                # Filtro da classe pai (Agentes)
                if agentes_alvo and str(codigo_ons).strip() not in agentes_alvo:
                    continue
                
                # Check Graceful Shutdown do KEDA
                self.check_shutdown()
                
                try:
                    self.baixar_fatura(codigo_ons, empresa_nome, nome_ons)
                except Exception as e:
                    self.logger.error(f"💥 Erro FATAL absoluto em ASSU ({codigo_ons}) pós retentativas: {e}")

if __name__ == "__main__":
    bot = AssuRobot()
    bot.run()
