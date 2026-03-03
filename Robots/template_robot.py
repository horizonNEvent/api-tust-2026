import sys
import os
import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Adiciona o diretório raiz ao path para encontrar o base_robot
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from base_robot import BaseRobot

class CustomRobot(BaseRobot):
    def __init__(self):
        super().__init__("custom_robot") # Substitua pelo nome do seu robô
        self.session = requests.Session()

    # --- REGRA DE RESILIÊNCIA (TENACITY) ---
    # Exponential Backoff: Espera 2s, depois 4s, até no máximo 10s. Tentará 5 vezes.
    # Retry apenas se for erro de conexão ou timeout.
    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((requests.exceptions.ConnectionError, requests.exceptions.Timeout)),
        reraise=True
    )
    def _requisicao_instavel_exemplo(self, url):
        """
        Substitua este método pela sua chamada HTTP real (login, download, etc)
        Se der timeout, a biblioteca Tenacity vai lidar com os retries automaticamente.
        """
        self.logger.info(f"Tentando acessar {url}...")
        response = self.session.get(url, timeout=10)
        response.raise_for_status()
        return response

    def run(self):
        """Loop de execução principal."""
        self.logger.info("Iniciando processamento do robô...")
        
        # Exemplo: Lendo a lista de agentes passados pela API/Worker
        agentes = self.get_agents()
        
        for agente in agentes:
            # 1. Checagem de Graceful Shutdown (Se o KEDA desligar o container, ele para aqui e não corrompe o próximo)
            self.check_shutdown()
            
            self.logger.info(f"Processando Agente: {agente}")
            
            try:
                # ==========================================
                # COLE SUA LÓGICA DE LOGIN E DOWNLOAD AQUI
                # ==========================================
                
                # Exemplo chamando a função protegida por Tenacity:
                # self._requisicao_instavel_exemplo("https://site-da-transmissora.com.br")
                
                # 2. Defina o seu XML baixado e salve na pasta de saída
                output_path = self.get_output_path()
                os.makedirs(output_path, exist_ok=True)
                
                file_name = f"NFe_{agente}_exemplo.xml"
                final_file = os.path.join(output_path, file_name)
                
                with open(final_file, "w") as f:
                    f.write("<xml>Conteúdo do Seu Robô</xml>")
                    
                self.logger.info(f"✅ Arquivo salvo: {final_file}")
                
            except Exception as e:
                self.logger.error(f"💥 Erro fatal ao processar {agente}: {e}")
                # Quando der erro, prosseguimos para o próximo agente sem quebrar o loop inteiro.

if __name__ == "__main__":
    bot = CustomRobot()
    bot.run()
