import requests
from bs4 import BeautifulSoup
import json
import re
import os
import sys
from datetime import datetime
import time
import random
import pdfkit
import logging

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Adiciona o diretório raiz ao path para encontrar a classe pai base_robot
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from base_robot import BaseRobot

# Configuração do PDFKit (wkhtmltopdf)
WKHTMLTOPDF_PATH = r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe"
PDFKIT_CONFIG = None
if os.path.exists(WKHTMLTOPDF_PATH):
    PDFKIT_CONFIG = pdfkit.configuration(wkhtmltopdf=WKHTMLTOPDF_PATH)

class EvoltzRobot(BaseRobot):
    def __init__(self):
        # Inicializa o robô chamando o BaseRobot com a flag "evoltz"
        super().__init__("evoltz")
        self.session = requests.Session()
        self.base_url = "https://www2.nbte.com.br"
        
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Content-Type': 'application/x-www-form-urlencoded'
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
    def login(self, cod_ons, nome_ons):
        self.logger.info(f"  [LOGIN] Iniciando login para {nome_ons} ({cod_ons})...")
        
        # GET inicial para cookies
        self.session.get(self.base_url, headers=self.headers, timeout=20)
        
        # POST Login
        payload = {"cod-ons-login": cod_ons, "AcaoClick": "doLogin", "idChave": ""}
        response = self.session.post(self.base_url, data=payload, headers=self.headers, timeout=30)
        
        if "Painel de Fatura" in response.text or "Sair" in response.text:
            self.logger.info(f"  [OK] Login bem-sucedido para {cod_ons}.")
            return True
        else:
            self.logger.warning(f"  [FAIL] Falha no login para {cod_ons}.")
            return False

    # === Camada de Resiliência: Tenacity Retry Logic ===
    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1.5, min=2, max=15),
        retry=retry_if_exception_type((requests.exceptions.ConnectionError, requests.exceptions.Timeout)),
        reraise=True
    )
    def get_faturas(self):
        response = self.session.get(self.base_url, headers=self.headers, timeout=30)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Detecta competência (primeira opção do select filtro_mesano)
        filtro_mesano = ""
        select = soup.find('select', {'name': 'filtro_mesano'})
        if select and select.find('option'):
            option = select.find('option')
            filtro_mesano = option.get('value', '')
            self.logger.info(f"  [INFO] Competência detectada: {option.text.strip()}")
        
        table = soup.find('table', {'id': '_dataTable'}) or soup.find('table')
        if not table:
            self.logger.warning("  [WARN] Tabela de faturas não encontrada.")
            return [], ""
        
        faturas = []
        rows = table.find('tbody').find_all('tr') if table.find('tbody') else table.find_all('tr')[1:]
        
        for row in rows:
            cols = row.find_all('td')
            if len(cols) >= 6:
                transmissora = cols[0].text.strip()
                # Links estão no formato callAcaoClick('Acao', 'Target', 'IdChave')
                links = {
                    'fatura': self.extract_id(cols[1].find('a')),
                    'boleto': self.extract_id(cols[3].find('a')),
                    'danfe': self.extract_id(cols[4].find('a')),
                    'xml': self.extract_id(cols[5].find('a'), xml=True)
                }
                num_fatura = cols[1].text.strip()
                
                faturas.append({
                    'transmissora': transmissora,
                    'numero': num_fatura,
                    'links': links
                })
        
        return faturas, filtro_mesano

    def extract_id(self, a_tag, xml=False):
        if not a_tag: return None
        html = str(a_tag)
        # Regex para pegar o último parâmetro do callAcaoClick
        match = re.search(r"callAcaoClick\('.*?','.*?','(\d+)'\)", html)
        if match:
            return match.group(1)
        return None

    # === Camada de Resiliência: Tenacity Retry Logic ===
    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1.5, min=2, max=15),
        retry=retry_if_exception_type((requests.exceptions.ConnectionError, requests.exceptions.Timeout)),
        reraise=True
    )
    def baixar_documento(self, acao, id_chave, filtro_mesano, nome_arquivo, pasta_transmissora):
        caminho_final = os.path.join(pasta_transmissora, nome_arquivo)
        
        # Se for PDF/XML e já existe, pula
        if os.path.exists(caminho_final):
            return
        # Se for HTML que vira PDF e o PDF já existe, pula
        if nome_arquivo.endswith('.html') and os.path.exists(caminho_final.replace('.html', '.pdf')):
            return

        payload = {
            'filtro_mesano': filtro_mesano,
            'AcaoClick': acao,
            'idChave': id_chave,
            'id': ''
        }
        
        response = self.session.post(self.base_url, data=payload, headers=self.headers, timeout=45)
        if response.status_code == 200:
            content_type = response.headers.get('Content-Type', '').lower()
            
            # XML ou PDF direto
            if 'xml' in content_type or 'pdf' in content_type or nome_arquivo.endswith('.xml') or nome_arquivo.endswith('.pdf'):
                with open(caminho_final, 'wb') as f:
                    f.write(response.content)
                self.logger.info(f"    [OK] Baixado: {nome_arquivo}")
            
            # HTML para converter em PDF (Boleto / Fatura)
            elif 'html' in content_type:
                # Corrige encoding e base URL
                html_content = response.text.replace('<head>', f'<head><base href="{self.base_url}/">')
                if PDFKIT_CONFIG:
                    pdf_path = caminho_final.replace('.html', '.pdf')
                    try:
                        pdfkit.from_string(html_content, pdf_path, configuration=PDFKIT_CONFIG, options={'quiet': '', 'encoding': 'UTF-8'})
                        self.logger.info(f"    [OK] PDF Gerado a partir de HTML: {os.path.basename(pdf_path)}")
                    except Exception as e:
                        # Se falhar PDF, salva HTML como fallback
                        self.logger.warning(f"    [WARN] Falha ao gerar PDF, fazendo fallback para HTML: {e}")
                        with open(caminho_final, 'w', encoding='utf-8') as f:
                            f.write(html_content)
                else:
                    with open(caminho_final, 'w', encoding='utf-8') as f:
                        f.write(html_content)
                    self.logger.info(f"    [OK] HTML Salvo (wkhtmltopdf ausente): {nome_arquivo}")

    def processar_faturas(self, cod_ons, empresa_nome, nome_ons):
        # Jitter de gentileza para não travar firewall alvo
        time.sleep(random.uniform(1.0, 3.0))
        self.logger.info(f"[{empresa_nome}] Iniciando extração do ONS {cod_ons} ({nome_ons})...")
        
        # 1. Login
        if not self.login(cod_ons, nome_ons):
            return False
            
        # 2. Busca lista de faturas do Mês/Ano recente
        faturas, comp = self.get_faturas()
        if not faturas:
            self.logger.info(f"  Nenhuma fatura encontrada para {nome_ons}.")
            return False
            
        self.logger.info(f"  Encontradas {len(faturas)} faturas para {nome_ons}.")
        
        # Cria a base do dir: /downloads/EVOLTZ/BASE/ONS/
        output_base_ons = os.path.join(self.get_output_path(), empresa_nome, str(cod_ons))
        
        sucesso_geral = False
        
        # 3. Baixa todos os arquivos de cada fatura
        for fat in faturas:
            t_nome = fat['transmissora']
            num = fat['numero']
            links = fat['links']
            
            # Limpa nome da transmissora para pasta final
            t_pasta = re.sub(r'[^\w\s-]', '', t_nome).strip().replace(' ', '_')
            path_dest = os.path.join(output_base_ons, t_pasta)
            os.makedirs(path_dest, exist_ok=True)
            
            self.logger.info(f"    > Lendo {t_nome} (Nº {num})")
            
            self.check_shutdown()
            
            try:
                if links['fatura']:
                    self.baixar_documento('Imprimir.fatura', links['fatura'], comp, f"Fatura_{num}.html", path_dest)
                    sucesso_geral = True
                
                if links['boleto']:
                    self.baixar_documento('Imprimir.boleto', links['boleto'], comp, f"Boleto_{num}.html", path_dest)
                    sucesso_geral = True
                
                if links['danfe']:
                    self.baixar_documento('Imprimir.danfe', links['danfe'], comp, f"DANFE_{num}.pdf", path_dest)
                    sucesso_geral = True
                
                if links['xml']:
                    self.baixar_documento('Exportar.xml', links['xml'], comp, f"NFe_{num}.xml", path_dest)
                    sucesso_geral = True
            except Exception as e:
                self.logger.error(f"    [ERR] Falha fatal no loop da fatura {num}: {e}")

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
                    self.processar_faturas(codigo_ons, empresa_nome, nome_ons)
                except Exception as e:
                    self.logger.error(f"💥 Erro FATAL absoluto em EVOLTZ ({codigo_ons}) pós retentativas: {e}")

if __name__ == "__main__":
    bot = EvoltzRobot()
    bot.run()
