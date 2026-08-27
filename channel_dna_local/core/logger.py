import logging
import logging.handlers

from channel_dna_local.config import config

# Ensure log directory exists
log_dir = config.base_dir / "logs"
log_dir.mkdir(exist_ok=True)
log_file = log_dir / "channel_dna.log"

# Setup root logger
logger = logging.getLogger("ChannelDNA")
logger.setLevel(logging.DEBUG)

# File Handler (Rotating)
file_handler = logging.handlers.RotatingFileHandler(
    log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
)
file_handler.setLevel(logging.DEBUG)
file_formatter = logging.Formatter(
    fmt="[%(asctime)s] [%(levelname)s] [%(name)s.%(funcName)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
file_handler.setFormatter(file_formatter)
logger.addHandler(file_handler)

# Console Handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter(fmt="[%(levelname)s] %(message)s")
console_handler.setFormatter(console_formatter)
logger.addHandler(console_handler)


# Custom handler for GUI logs
class GUIHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.callbacks = []

    def add_callback(self, cb):
        if cb not in self.callbacks:
            self.callbacks.append(cb)

    def emit(self, record):
        msg = self.format(record)
        for cb in self.callbacks:
            try:
                cb(msg, record.levelname)
            except Exception:
                pass


gui_handler = GUIHandler()
gui_handler.setLevel(logging.INFO)
gui_handler.setFormatter(console_formatter)
logger.addHandler(gui_handler)


def get_logger(name: str):
    return logger.getChild(name)

