import logging
from logging.handlers import RotatingFileHandler
import os
import sys
import uuid

LOG_FILE = os.environ.get('LOG_FILE', os.path.join(os.path.dirname(__file__), 'content_creation.log'))
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO').upper()
RUN_ID = uuid.uuid4().hex


class RunIdFilter(logging.Filter):
    def filter(self, record):
        record.run_id = RUN_ID
        return True


def setup_logging(log_file: str = None, level: str = None):
    log_file = log_file or LOG_FILE
    level = (level or LOG_LEVEL).upper()
    fmt = '%(asctime)s %(levelname)s %(name)s [run_id=%(run_id)s] %(module)s:%(lineno)d %(message)s'
    datefmt = '%Y-%m-%dT%H:%M:%S%z'

    root = logging.getLogger()
    root.setLevel(getattr(logging, level, logging.INFO))
    # make idempotent
    root.handlers = []

    fh = RotatingFileHandler(log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding='utf-8')
    fh.setFormatter(logging.Formatter(fmt, datefmt=datefmt))
    fh.addFilter(RunIdFilter())
    root.addHandler(fh)

    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(logging.Formatter(fmt, datefmt=datefmt))
    ch.addFilter(RunIdFilter())
    root.addHandler(ch)


def get_logger(name: str = None):
    return logging.getLogger(name)


def write_log(message: str, level: str = 'info', **extra):
    logger = get_logger('app')
    lvl = level.lower()
    if lvl == 'debug':
        logger.debug(message, extra=extra)
    elif lvl == 'warning':
        logger.warning(message, extra=extra)
    elif lvl == 'error':
        logger.error(message, extra=extra)
    elif lvl == 'critical':
        logger.critical(message, extra=extra)
    else:
        logger.info(message, extra=extra)
