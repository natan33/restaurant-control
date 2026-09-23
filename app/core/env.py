


import os
from pathlib import Path

from dotenv import load_dotenv


class BaseConfig:
    """Configuração Base com lógica de detecção de ambiente."""
    
    def __init__(self):
        # Resolve o diretório raiz (ajuste o número de .parent conforme sua estrutura)
        self.BASE_DIR = Path.cwd()
        
        # Detecta ambiente
        self.FLASK_ENV = os.getenv("FLASK_ENV", "development").lower()
        self.IS_PRODUCTION = self.FLASK_ENV == "production"

        self._load_and_validate()

    def _load_and_validate(self):
        env_file = self.BASE_DIR / '.env'
        
        if not self.IS_PRODUCTION:
            if env_file.exists():
                load_dotenv(env_file)
                #print(f"[*] Modo {self.FLASK_ENV.upper()}: .env carregado.")
            else:
                print(f"⚠️  Aviso: .env não encontrado em {self.BASE_DIR}")
        else:
            # Proteção Hardened: Impede execução se houver arquivo físico de segredos
            if env_file.exists():
                raise RuntimeError(
                    "❌ VIOLAÇÃO DE SEGURANÇA: Arquivo .env detectado em PRODUÇÃO. "
                    "Remova o arquivo e use variáveis de ambiente do Sistema/Container."
                )

    @staticmethod
    def get_env_or_raise(var_name: str) -> str:
        """Garante que variáveis críticas existam no SO."""
        value = os.getenv(var_name)
        if not value:
            raise RuntimeError(f"❌ Variável obrigatória ausente: {var_name}")
        return value