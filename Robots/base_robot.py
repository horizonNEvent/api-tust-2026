import os
import argparse
import logging
import json
import signal
import sys

class BaseRobot:
    def __init__(self, name):
        self.name = name
        self.parser = argparse.ArgumentParser(description=f"Robô {name}")
        self._setup_args()
        self.args = self.parser.parse_args()
        self._setup_logging()
        
        # Graceful Shutdown configuration
        self.is_shutting_down = False
        signal.signal(signal.SIGINT, self._handle_sigterm)
        signal.signal(signal.SIGTERM, self._handle_sigterm)
        
    def _handle_sigterm(self, signum, frame):
        """
        Garante que o robô não corrompa arquivos caso o KEDA desligue o container.
        """
        self.logger.warning("🚨 Sinal de desligamento recebido (SIGTERM/SIGINT). Iniciando Graceful Shutdown...")
        self.is_shutting_down = True

    def check_shutdown(self):
        """Método helper simples para o robô parar o que está fazendo antes de cada iteração longa"""
        if self.is_shutting_down:
            self.logger.error("🛑 Interrompendo execução repentinamente de forma segura (Graceful Shutdown ativado)")
            sys.exit(0)
        
    def _setup_args(self):
        self.parser.add_argument("--output_dir", required=True, help="Diretório de saída")
        self.parser.add_argument("--user", help="Usuário")
        self.parser.add_argument("--password", help="Senha")
        self.parser.add_argument("--agente", help="Agentes (separados por vírgula)")
        self.parser.add_argument("--empresa", help="Empresa alvo")

    def _setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format='%(message)s'
        )
        self.logger = logging.getLogger(self.name)

    def get_output_path(self):
        return self.args.output_dir

    def get_agents(self):
        if self.args.agente:
            return [a.strip() for a in self.args.agente.split(",")]
        return []
