import logging.config
import os
import socket

CLIENT_NAME_SIZE = 5
CLIENT_NAME = os.urandom(CLIENT_NAME_SIZE)

LOGGER_NAME = f"{socket.gethostname()} ({CLIENT_NAME.hex()})"
LOGZ_CONF = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'logzioFormat': {
            'format': f'{{"client": "{LOGGER_NAME}"}}',
            'validate': False
        },
        'info': {
            'format': '%(asctime)s-%(levelname)s-%(name)s::%(module)s|%(lineno)s:: %(message)s'
        },
    },
    'handlers': {
        'logzio': {
            'class': 'logzio.handler.LogzioHandler',
            'level': 'ERROR',
            'formatter': 'logzioFormat',
            'token': 'zZkJFlysKNUhCtGmTxUiSQUOunCGfHBM',
            'logs_drain_timeout': 15,
            'url': 'https://listener.logz.io:8071'
        },
    },
    'loggers': {
        '': {
            'level': 'DEBUG',
            'handlers': ['logzio'],
            'propagate': True
        }
    }
}
logging.config.dictConfig(LOGZ_CONF)
logger = logging.getLogger(f"Client - {LOGGER_NAME}")
logging.getLogger("urllib3").setLevel(logging.INFO)


def timing_log(name: str, duration: float, extra=None):
    extra = extra or {}
    # logger.info(f"Timing", extra={'duration': duration * 1000, 'timing_part': name, **extra})
