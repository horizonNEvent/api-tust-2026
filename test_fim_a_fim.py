import requests
import time
import argparse

API_URL = "http://localhost:8001"

def disparar_robo(config_id, nome):
    print(f"\n🚀 Disparando ordem via API TUST (ID: {config_id}) - {nome}...")
    try:
        response = requests.post(f"{API_URL}/robots/run/{config_id}")
        if response.status_code == 200:
            print(f"✅ Ordem aceita! A API postou na fila SQS LocalStack.")
        else:
            print(f"❌ Erro na API: {response.text}")
    except Exception as e:
        print(f"❌ Falha de Conexão com a API: {e}")

def obter_configs():
    try:
        r = requests.get(f"{API_URL}/configs/")
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"❌ Falha ao buscar configs na API: {e}")
    return []

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gatilho de Teste TUST Fim-a-Fim")
    parser.add_argument("--id", type=int, help="ID específico do Robô para testar", default=None)
    parser.add_argument("--base", type=str, help="Disparar todas as configurações de uma Base (Ex: AE, DE, RE)", default=None)
    parser.add_argument("--robo", type=str, help="Disparar todas as configurações de um Robô (Ex: ASSU, CNT)", default=None)
    args = parser.parse_args()

    configs = obter_configs()
    if not configs:
        print("Nenhuma configuração lida do banco ou API fora do ar.")
        exit(1)

    # Filtros
    alvos = []
    if args.id:
        alvos = [c for c in configs if c['id'] == args.id]
        print(f"⚙️ Modo Individual: Testando APENAS o ID {args.id}")
    elif args.base:
        alvos = [c for c in configs if str(c.get('base')).upper() == args.base.upper()]
        print(f"⚙️ Modo Base: Testando TODOS os robôs da Base {args.base.upper()}")
    elif args.robo:
        alvos = [c for c in configs if str(c.get('robot_type')).upper() == args.robo.upper()]
        print(f"⚙️ Modo Robô: Testando TODAS as bases do Robô {args.robo.upper()}")
    else:
        print("⚙️ Modo Completo: Testando TUDO (Toda a esteira)... Isso pode gerar dezenas de mensagens SQS!")
        alvos = configs

    if not alvos:
        print("Nenhum robô encontrado para o filtro passado!")
        exit(0)

    for c in alvos:
        nome_exibicao = f"Robô: {str(c['robot_type']).upper()} | Base: {c.get('base')} | Agrupadora: {c.get('label')}"
        disparar_robo(c['id'], nome_exibicao)
        time.sleep(1) # Dá um pequeno fôlego pra API processar o lote de SQS
        
    print("\n👉 Olhe para o Terminal do Worker! Ele deve estar acordando e processando faturas conforme a Ordem enviada.")
