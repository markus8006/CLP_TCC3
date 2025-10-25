# src/utils/logs.py
import logging
from colorama import Fore, Style, init

init(autoreset=True)  # reseta cores automaticamente

PROCESS_LEVEL = 25  # INFO=20, WARNING=30 -> PROCESS no meio
logging.addLevelName(PROCESS_LEVEL, "PROCESS")

def process(self, message, *args, **kwargs):
    if self.isEnabledFor(PROCESS_LEVEL):
        self._log(PROCESS_LEVEL, message, args, **kwargs)

# injetando método process em logging.Logger
logging.Logger.process = process


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
        # usa o nome do nível customizado (PROCESS) caso exista
        levelname = record.levelname
        color = self.COLORS.get(levelname, Fore.WHITE)
        log_fmt = f"[%(asctime)s] {levelname:<8} %(message)s"
        formatter = logging.Formatter(log_fmt, "%Y-%m-%d %H:%M:%S")
        return color + formatter.format(record) + Style.RESET_ALL


def setup_logger(root_level=logging.INFO,
                 silence_names=None,
                 show_sqlalchemy_warning=True):
    """
    Inicializa o logger root colorido e silencia loggers listados.

    :param root_level: nível do root logger (DEBUG/INFO/WARNING/ERROR)
    :param silence_names: lista de nomes de loggers a silenciar (setLevel WARNING/ERROR)
    :param show_sqlalchemy_warning: se False, SQLAlchemy será silenciado
    :return: logger root configurado
    """
    if silence_names is None:
        silence_names = []

    # configura logger root
    logger = logging.getLogger()
    logger.setLevel(root_level)

    # limpa handlers antigos
    for h in list(logger.handlers):
        logger.removeHandler(h)

    # handler console com formatter colorido
    ch = logging.StreamHandler()
    ch.setFormatter(ColorFormatter())
    logger.addHandler(ch)

    # silenciar/ajustar loggers indesejados
    # opções comuns:
    defaults_to_silence = [
        "werkzeug",          # flask dev server
        "sqlalchemy.pool",
        "sqlalchemy.engine",
        "asyncio",
        "pymodbus",          # se estiver usando pymodbus
        "aiosqlite",         # se usar sqlite async
        "uvicorn.access",    # se usar uvicorn
    ]

    for name in defaults_to_silence:
        if name in ("sqlalchemy.engine", "sqlalchemy.pool") and show_sqlalchemy_warning:
            # mantém warnings do SQLAlchemy para problemas relevantes
            logging.getLogger(name).setLevel(logging.WARNING)
        else:
            logging.getLogger(name).setLevel(logging.ERROR)
        logging.getLogger(name).propagate = False

    # adicionais passados pelo usuário
    for name in silence_names:
        logging.getLogger(name).setLevel(logging.ERROR)
        logging.getLogger(name).propagate = False
    


    logging.getLogger('sqlalchemy').setLevel(logging.CRITICAL)



    return logger


# criar logger já configurado por padrão (pode chamar setup_logger manualmente se quiser)
logger = setup_logger()
