import os
import hashlib
from lxml import etree
from datetime import datetime
import json

def calculate_file_hash(filepath):
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def extract_xml_data(filepath, db_session=None):
    """
    Extrai CNPJ, Competência, Valor e tenta resolver o Agente e Transmissora.
    """
    try:
        tree = etree.parse(filepath)
        root = tree.getroot()
        
        # Remove namespaces
        for elem in root.getiterator():
            if not (isinstance(elem.tag, str) and "}" in elem.tag):
                continue
            elem.tag = elem.tag.split("}", 1)[1]

        # 1. CNPJ da Transmissora
        cnpj = None
        for path in [".//emit/CNPJ", ".//CNPJ", ".//emitente/CNPJ"]:
            elem = root.find(path)
            if elem is not None and elem.text:
                cnpj = elem.text.strip()
                break

        # 2. Competência
        competence = None
        venc_elem = root.find(".//dVenc")
        if venc_elem is not None and venc_elem.text:
            try:
                data_venc = venc_elem.text.strip()[:10]
                dt = datetime.strptime(data_venc, "%Y-%m-%d")
                if dt.month == 1:
                    competence = f"{dt.year - 1}-12"
                else:
                    competence = f"{dt.year}-{str(dt.month - 1).zfill(2)}"
            except: pass

        if not competence:
            for path in [".//dhEmi", ".//dEmi", ".//dhSaida", ".//dSaiEnt"]:
                elem = root.find(path)
                if elem is not None and elem.text:
                    competence = elem.text.strip()[:7]
                    break
        
        if not competence:
            competence = datetime.now().strftime("%Y-%m")

        # 3. Valor
        valor = None
        for path in [".//vNF", ".//vServ", ".//vTotal", ".//vLiq"]:
            elem = root.find(path)
            if elem is not None and elem.text:
                valor = elem.text.strip()
                break

        # 4. Resolver Transmissora e Agente
        transmissora_name = "unknown_transmissora"
        agent_name = "unknown_agent"
        ons_code = None

        if db_session and cnpj:
            from models import Transmissora
            t = db_session.query(Transmissora).filter(Transmissora.cnpj == cnpj).first()
            if t:
                transmissora_name = t.sigla or t.nome
                ons_code = t.codigo_ons

        # Resolver nome do Agente do empresas.json se tivermos o código ONS
        if ons_code:
            try:
                json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Data', 'empresas.json')
                with open(json_path, 'r', encoding='utf-8') as f:
                    empresas_data = json.load(f)
                
                # Search across all bases
                for base, agents in empresas_data.items():
                    if str(ons_code) in agents:
                        agent_name = agents[str(ons_code)]
                        break
            except Exception as e:
                print(f"Error loading empresas.json: {e}")

        return {
            "cnpj": cnpj,
            "competencia": competence,
            "valor": valor,
            "hash": calculate_file_hash(filepath),
            "valid": cnpj is not None,
            "transmissora": transmissora_name,
            "agent_name": agent_name,
            "ons_code": ons_code
        }

    except Exception as e:
        print(f"Erro ao ler XML {filepath}: {e}")
        return {"error": str(e), "valid": False}
