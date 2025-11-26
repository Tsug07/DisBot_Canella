import logging
import os
import sys
from logging.handlers import RotatingFileHandler

# Cria diretório de logs se não existir
LOG_DIR = "logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

# Configuração do logger
logger = logging.getLogger("rebecca_bot")
logger.setLevel(logging.DEBUG)

# Handler para arquivo (rotativo) com UTF-8
file_handler = RotatingFileHandler(
    os.path.join(LOG_DIR, "rebecca_bot.log"),
    maxBytes=10485760,  # 10MB
    backupCount=5,
    encoding='utf-8'
)
file_handler.setLevel(logging.DEBUG)

# Handler para console - usa stderr e ignora erros de encoding
console_handler = logging.StreamHandler(sys.stderr)
console_handler.setLevel(logging.INFO)

# Formato das mensagens (sem emojis para evitar problemas de encoding)
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
