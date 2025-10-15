import logging
from colorama import Fore, Style, init

init(autoreset=True)  # reseta cores automaticamente

class ColorFormatter(logging.Formatter):
    COLORS = {
        'PROCESS': Fore.CYAN,
        'DEBUG': Fore.BLUE,
        'INFO': Fore.GREEN,
        'WARNING': Fore.YELLOW,
        'ERROR': Fore.RED,
        'CRITICAL': Fore.MAGENTA
    }
    
    def format(self, record):
        color = self.COLORS.get(record.levelname, Fore.WHITE)
        log_fmt = f"[%(asctime)s] {record.levelname:<8} %(message)s"
        formatter = logging.Formatter(log_fmt, "%Y-%m-%d %H:%M:%S")
        return color + formatter.format(record) + Style.RESET_ALL

def setup_logger():
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    # Remove todos os handlers antigos
    while logger.handlers:
        logger.handlers.pop()
    handler = logging.StreamHandler()
    handler.setFormatter(ColorFormatter())
    logger.addHandler(handler)

    # Silenciar SQLAlchemy
    for ns in ("sqlalchemy", "sqlalchemy.engine", "sqlalchemy.pool", "sqlalchemy.orm"):
        logging.getLogger(ns).handlers.clear()
        logging.getLogger(ns).setLevel(logging.WARNING)
        logging.getLogger(ns).propagate = False
    return logger





    return logger



PROCESS_LEVEL = 25  # INFO=20, WARNING=30 -> PROCESS no meio
logging.addLevelName(PROCESS_LEVEL, "PROCESS")

def process(self, message, *args, **kwargs):
    if self.isEnabledFor(PROCESS_LEVEL):
        self._log(PROCESS_LEVEL, message, args, **kwargs)

logging.Logger.process = process

logger = setup_logger()