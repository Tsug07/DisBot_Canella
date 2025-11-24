import logging
import os
from logging.handlers import RotatingFileHandler

# Cria diretório de logs se não existir
LOG_DIR = "logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

# Configuração do logger
logger = logging.getLogger("rebecca_bot")
logger.setLevel(logging.DEBUG)

# Handler para arquivo (rotativo)
file_handler = RotatingFileHandler(
    os.path.join(LOG_DIR, "rebecca_bot.log"),
    maxBytes=10485760,  # 10MB
    backupCount=5
)
file_handler.setLevel(logging.DEBUG)

# Handler para console
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)

# Formato das mensagens
formatter = logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

# Adiciona handlers ao logger
logger.addHandler(file_handler)
logger.addHandler(console_handler)

def get_logger():
    return logger
