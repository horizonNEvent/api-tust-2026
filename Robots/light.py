import os
import requests
import re
import time
import json
import logging
import tempfile
import cv2
import traceback
import urllib.parse
from datetime import datetime
from bs4 import BeautifulSoup
from paddleocr import PaddleOCR
import urllib3
import sys

# Adiciona o diretório raiz ao path para encontrar a classe pai base_robot
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from base_robot import BaseRobot
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

class LightRobot(BaseRobot):
    def __init__(self):
        super().__init__("light")
        self.base_url = "https://nfe.light.com.br"
        
        self.session = requests.Session()
        self.session.verify = False
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        self.headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "max-age=0",
            "Connection": "keep-alive",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
            "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "Upgrade-Insecure-Requests": "1"
        }

    def carregar_referencia_empresas_light(self):
        """Carrega Data/empresas.light.json"""
        try:
            json_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'Data', 'empresas.light.json')
            with open(json_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"Erro ao carregar empresas.light.json: {e}")
            return {}

    def extrair_tokens_aspnet(self, html):
        soup = BeautifulSoup(html, 'html.parser')
        viewstate = soup.find('input', {'name': '__VIEWSTATE'})
        eventvalidation = soup.find('input', {'name': '__EVENTVALIDATION'})
        
        vs = viewstate.get('value', '') if viewstate else ''
        ev = eventvalidation.get('value', '') if eventvalidation else ''
        return vs, ev
    
    def processar_captcha(self, imagem_bytes):
        self.logger.info("Iniciando processamento de CAPTCHA...")
        try:
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                tmp.write(imagem_bytes)
                tmp_path = tmp.name
            
            self.logger.info(f"Imagem temporária salva: {tmp_path}")

            # Pré-processamento com OpenCV
            try:
                image = cv2.imread(tmp_path)
                image = cv2.resize(image, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
                
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
                clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
                gray = clahe.apply(gray)
                _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                binary_bgr = cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)
                
                processed_path = tmp_path.replace('.png', '_processed.png')
                cv2.imwrite(processed_path, binary_bgr)
                self.logger.info(f"Pré-processamento OpenCV concluído: {processed_path}")
            except Exception as cv_err:
                 self.logger.error(f"Erro no OpenCV: {cv_err}")
                 return None

            # Inicializa OCR Localmente (Isolamento total)
            self.logger.info("Inicializando PaddleOCR localmente...")
            ocr_local = PaddleOCR(use_textline_orientation=True, lang='en')
            
            # OCR no arquivo processado
            self.logger.info("Executando OCR...")
            resultado = ocr_local.ocr(processed_path)
            self.logger.info(f"Resultado OCR Bruto: {resultado}")
            
            texto = None
            if resultado and len(resultado) > 0:
                if isinstance(resultado[0], list):
                    for line in resultado[0]:
                        if isinstance(line, list) and len(line) >= 2:
                            txt_info = line[1]
                            if isinstance(txt_info, tuple):
                                texto = txt_info[0]
                                break
                elif isinstance(resultado[0], dict):
                    if 'rec_texts' in resultado[0] and resultado[0]['rec_texts']:
                        texto = resultado[0]['rec_texts'][0]

            # Limpeza
            try: 
                os.unlink(tmp_path)
                if os.path.exists(processed_path): os.unlink(processed_path)
            except: pass
            
            if texto:
                final = ''.join(c for c in texto if c.isalnum()).lower()
                self.logger.info(f"Texto extraído: {final}")
                return final
                
            self.logger.warning("OCR não retornou texto válido.")
            return None
        except Exception as e:
            self.logger.error(f"Erro CRÍTICO no processar_captcha: {e}")
            traceback.print_exc()
            return None

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1.5, min=2, max=10), reraise=True)
    def fazer_login(self, cnpj, codigo_ons, tentativas=5):
        url_login = f"{self.base_url}/Web/wfmAutenticar.aspx"
        
        try:
            resp = self.session.get(url_login, headers=self.headers, timeout=30)
        except Exception as e:
            self.logger.error(f"Erro conexão inicial: {e}")
            return False, None, None

        vs, ev = self.extrair_tokens_aspnet(resp.text)
        
        for tentativa in range(1, tentativas + 1):
            ts = int(time.time() * 1000)
            url_cap = f"{self.base_url}/Web/GenerateCaptcha.aspx?{ts}"
            try:
                r_cap = self.session.get(url_cap, headers=self.headers, timeout=20)
                captcha_code = self.processar_captcha(r_cap.content)
            except Exception as cap_err:
                self.logger.error(f"Falha ao baixar captcha: {cap_err}")
                captcha_code = None
            
            # Se falhou OCR, tentar mais uma vez sem gastar tentativa de login
            if not captcha_code:
                self.logger.warning(f"Falha OCR Captcha (Tentativa {tentativa}/{tentativas})")
                time.sleep(1)
                continue

            self.logger.info(f"Tentando login com captcha: {captcha_code}")
            
            payload = {
                "__EVENTTARGET": "",
                "__EVENTARGUMENT": "",
                "__LASTFOCUS": "",
                "__VIEWSTATE": vs,
                "__EVENTVALIDATION": ev,
                "rblUsuario": "2",
                "tbxCnpj": cnpj,
                "tbxOns": codigo_ons,
                "tbxCodigoCaptcha": captcha_code,
                "btnAutenticar": "Autenticar"
            }
            
            r_auth = self.session.post(url_login, data=payload, headers=self.headers, timeout=30)
            
            # Redirecionamento 302 ou sucesso na URL
            if "wfmBuscaNotas.aspx" in r_auth.url:
                parsed = urllib.parse.urlparse(r_auth.url)
                params = urllib.parse.parse_qs(parsed.query)
                u = params.get('u', [None])[0]
                id_ = params.get('id', [None])[0]
                if u and id_:
                    self.logger.info(f"Login Sucesso! URL={r_auth.url}")
                    return True, u, id_
            
            # Tenta pegar erro
            soup = BeautifulSoup(r_auth.text, 'html.parser')
            err = soup.find('span', {'id': 'lblMensagem'})
            if err and err.text.strip():
                self.logger.warning(f"Erro login: {err.text.strip()}")
            
            # Atualiza tokens
            vs, ev = self.extrair_tokens_aspnet(r_auth.text)
            time.sleep(1.5)

        self.logger.error("Falha no login após todas tentativas")
        return False, None, None

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1.5, min=2, max=10), reraise=True)
    def buscar_notas(self, u, id_, ano, mes):
        url_busca = f"{self.base_url}/Web/wfmBuscaNotas.aspx"
        
        self.logger.info(f"Buscando notas do período {mes:02d}/{ano}...")
        
        # 1. GET Inicial na Busca
        params = {"u": u, "id": id_}
        
        headers_get = self.headers.copy()
        headers_get.update({
            "Referer": f"{self.base_url}/Web/wfmAutenticar.aspx",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1"
        })
        
        r_get = self.session.get(url_busca, params=params, headers=headers_get, timeout=30)
        
        vs, ev = self.extrair_tokens_aspnet(r_get.text)
        
        # ONS Value extraction
        soup = BeautifulSoup(r_get.text, 'html.parser')
        ons_val = "4313"
        ddl = soup.find('select', {'name': 'ddlONS'})
        if ddl:
            sel = ddl.find('option', {'selected': 'selected'})
            if sel: ons_val = sel.get('value', '4313')
            

        # 2. POST da Busca
        headers_post = self.headers.copy()
        headers_post.update({
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": self.base_url,
            "Referer": f"{url_busca}?u={u}&id={id_}",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1"
        })

        payload = {
            "__EVENTTARGET": "",
            "__EVENTARGUMENT": "",
            "__LASTFOCUS": "",
            "__VIEWSTATE": vs,
            "__VIEWSTATEENCRYPTED": "",
            "__EVENTVALIDATION": ev,
            "ddlONS": ons_val,
            "ddlAno": str(ano),
            "ddlCompetencia": str(int(mes)), # Remove zero a esquerda se tiver
            "btnBuscar": "Buscar"
        }

        r_post = self.session.post(f"{url_busca}?u={u}&id={id_}", data=payload, headers=headers_post, timeout=30)
        
        soup = BeautifulSoup(r_post.text, 'html.parser')
        grid = soup.find('table', {'id': 'gvwResultado'})
        
        notas = []
        if grid:
            self.logger.info("Grid encontrado.")
            rows = grid.find_all('tr')[1:]
            for row in rows:
                cells = row.find_all('td')
                if len(cells) >= 5:
                    link = cells[0].find('a')
                    if link:
                        href = link.get('href', '')
                        m = re.search(r"__doPostBack\('([^']*)'", href)
                        evt_target = m.group(1) if m else None
                        
                        if evt_target:
                            nota_info = {
                                'id': link.get('id', ''),
                                'eventtarget': evt_target,
                                'tipo': cells[2].text.strip(),
                                'nome_arquivo': cells[3].text.strip()
                            }
                            notas.append(nota_info)
        else:
            self.logger.info("Grid não encontrado na busca.")
            msg = soup.find('span', {'id': 'lblMensagem'})
            if msg: self.logger.warning(f"MSG SISTEMA: {msg.text.strip()}")

        return notas, r_post.text

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1.5, min=2, max=10), reraise=True)
    def baixar_arquivo(self, u, id_, nota_info, html_anterior, save_dir):
        url_busca = f"{self.base_url}/Web/wfmBuscaNotas.aspx"
        
        self.logger.info(f"Baixando {nota_info['tipo']}: {nota_info['nome_arquivo']}...")
        
        vs, ev = self.extrair_tokens_aspnet(html_anterior)
        soup = BeautifulSoup(html_anterior, 'html.parser')
        
        def get_val(name, default):
            el = soup.find('select', {'name': name})
            if el:
                sel = el.find('option', {'selected': 'selected'})
                if sel: return sel.get('value', default)
            return default

        ons_val = get_val('ddlONS', '4313')
        ano_val = get_val('ddlAno', '2025')
        comp_val = get_val('ddlCompetencia', '8')

        headers_post = self.headers.copy()
        headers_post.update({
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": self.base_url,
            "Referer": f"{url_busca}?u={u}&id={id_}",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1"
        })

        payload = {
            "__EVENTTARGET": nota_info['eventtarget'],
            "__EVENTARGUMENT": "",
            "__LASTFOCUS": "",
            "__VIEWSTATE": vs,
            "__VIEWSTATEENCRYPTED": "",
            "__EVENTVALIDATION": ev,
            "ddlONS": ons_val,
            "ddlAno": ano_val,
            "ddlCompetencia": comp_val
        }

        r_down = self.session.post(f"{url_busca}?u={u}&id={id_}", data=payload, headers=headers_post, timeout=30)
        
        if r_down.status_code == 200:
            ctype = r_down.headers.get('Content-Type', '').lower()
            
            content_start = r_down.content[:10]
            is_pdf = b'%PDF' in content_start
            is_xml = b'<?xml' in content_start or b'<nfeProc' in content_start
            
            if is_pdf or is_xml or any(x in ctype for x in ['xml', 'pdf', 'octet-stream', 'application', 'image/jpeg']):
                filename = nota_info['nome_arquivo']
                cd = r_down.headers.get('Content-Disposition', '')
                if 'filename=' in cd:
                    m = re.search(r'filename[^;=\n]*=(([\'"]).*?\2|[^;\n]*)', cd)
                    if m: filename = m.group(1).strip('"\'')
                
                if is_pdf and not filename.lower().endswith('.pdf'):
                    filename += '.pdf'
                if is_xml and not filename.lower().endswith('.xml'):
                    filename += '.xml'

                filename = re.sub(r'[\\/*?:"<>|]', "", filename)
                os.makedirs(save_dir, exist_ok=True)
                full_path = os.path.join(save_dir, filename)
                
                with open(full_path, 'wb') as f:
                    f.write(r_down.content)
                self.logger.info(f"Salvo: {filename}")
                return True
            else:
                self.logger.warning(f"Tipo de arquivo desconhecido: {ctype}")
        
        return False

    def get_competencia(self):
        """Helper extraído do seu código para lidar com parametro de Mês/Ano"""
        if self.args.competencia:
            try:
                c = self.args.competencia.replace('/', '').replace('-', '')
                ano = int(c[:4])
                mes = int(c[4:6])
                return ano, mes
            except:
                self.logger.error("Competência inválida. Use YYYYMM. Usando atual.")
        now = datetime.now()
        return now.year, now.month

    def run(self):
        ano_busca, mes_busca = self.get_competencia()
        self.logger.info(f"Iniciando Light - Competência: {mes_busca:02d}/{ano_busca}")
        
        base_output_dir = self.get_output_path()
        target_agrupadora = self.args.base # Na arquitetura KEDA, a 'base' é a Agrupadora/Tenant (ex: AE, DE)
        target_agents = self.get_agents()

        # O robô da Light precisa buscar o JSON específico dela. Vamos testar se existe.
        empresas = self.carregar_referencia_empresas_light()
        
        if target_agrupadora and isinstance(empresas, dict):
             # Filtra apenas a base (agrupadora) enviada pelo KEDA
             if target_agrupadora.upper() in [k.upper() for k in empresas.keys()]:
                 # Manter apenas a base desejada
                 base_key = next((k for k in empresas.keys() if k.upper() == target_agrupadora.upper()), None)
                 empresas = {base_key: empresas[base_key]} if base_key else {}

        for agrupadora, agentes in empresas.items():
            # A lista de agentes no JSON da light é um dict ou list? Vamos padronizar pra list.
            if isinstance(agentes, dict):
                lista_empresas = []
                for cod_ons, dados_ons in agentes.items():
                    temp = dict(dados_ons)
                    temp['ons'] = str(cod_ons)
                    lista_empresas.append(temp)
            else:
                lista_empresas = agentes

            for dados in lista_empresas:
                ons = str(dados.get('ons') or dados.get('codigo_ons', ''))
                
                if target_agents and ons not in target_agents:
                    continue
                
                # Check shutdown a cada novo agente
                self.check_shutdown()

                cnpj = dados.get('cnpj')
                if not cnpj:
                    self.logger.warning(f"Agente {ons} ({agrupadora}) da Light não possui CNPJ. Pulando...")
                    continue

                # Nome da pasta (nome legível ou apenas ONS)
                nome_pasta = dados.get('pasta') or dados.get('nome') or f"ONS_{ons}"
                self.logger.info(f"Processando {agrupadora} - {nome_pasta} ({ons}) | CNPJ: {cnpj}")

                save_dir = os.path.join(base_output_dir, agrupadora, ons)

                ok, u, id_ = self.fazer_login(cnpj, ons)
                if ok:
                    notas, html_busca = self.buscar_notas(u, id_, ano_busca, mes_busca)
                    if notas:
                        self.logger.info(f"Encontradas {len(notas)} notas para {nome_pasta}.")
                        for nota in notas:
                            self.baixar_arquivo(u, id_, nota, html_busca, save_dir)
                    else:
                        self.logger.info(f"Nenhuma nota encontrada para {nome_pasta}.")
                else:
                    self.logger.error(f"Falha Login para {nome_pasta} (CNPJ: {cnpj}).")

if __name__ == "__main__":
    bot = LightRobot()
    bot.run()
