import logging
import logging.config
import logging.handlers
import logging
import os
from colorlog import ColoredFormatter
from aux import configurator as cc

root_folder = cc.conf['root']['folder']
log_folder = root_folder + cc.conf['decider']['log']['folder']
log_filename = log_folder + cc.conf['decider']['log']['filename']
log_level = cc.conf['decider']['log']['level']

log_init = False


class NoLFilter(logging.Filter):
    def filter(self, record):
        if record.name[:2] == 'L.':
            record.name = record.name[2:]
        return True


def init_log():
    global log_init
    if log_init:
        return
    log_init = True
    logconfig = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'standard': {
                'format': '%(name)-15s [%(levelname)1.1s] %(message)s'
            },
            'standard_file': {
                'format': '%(asctime)15s %(name)-10s [%(levelname)1.1s] %(message)s'
            },
            'c_standard': {
                '()': 'colorlog.ColoredFormatter',
                'format': '%(log_color)s%(name)-15s [%(levelname)1.1s]%(reset)s %(blue)s%(message)s'
            },
            'c_standard_file': {
                '()': 'colorlog.ColoredFormatter',
                'format': '%(log_color)s%(asctime)15s %(name)-10s [%(levelname)1.1s]%(reset)s %(blue)s%(message)s'
            },
        },
        'filters': {
          'noL_filter': {
            '()': NoLFilter
          }
        },
        'handlers': {
            'default': {
                'level': 'INFO',
                'class': 'logging.StreamHandler',
                'formatter': 'c_standard_file'
            },
            'console': {
                'level': log_level,
                'class': 'logging.StreamHandler',
                'formatter': 'c_standard',
                'filters': ['noL_filter']
            },
            'rot': {
                'level': log_level,
                'class': 'logging.handlers.RotatingFileHandler',
                'formatter': 'c_standard_file',
                'filename': log_filename,
                'backupCount': 5,
                'filters': ['noL_filter']
            },
            'others': {
                'level': 'WARNING',
                'class': 'logging.StreamHandler',
                'formatter': 'c_standard'
            }
        },
        'loggers': {
            'L': {
                'handlers': ['rot', 'console'],
                'level': 'NOTSET'
            },
            'kazoo': {
                'handlers': ['rot', 'console'],
                'level': 'INFO'
            },
            'keystoneclient': {
                'handlers': ['rot', 'console'],
                'level': 'INFO'
            },
            'monascaclient': {
                'handlers': ['rot', 'console'],
                'level': 'INFO'
            },
            '': {
                'handlers': [],
                'level': 'NOTSET',
                'propagate': False
            },
        }
    }
    logging.config.dictConfig(logconfig)
    logging.addLevelName(25, "STATE")

    def state(self, message, *args, **kws):
        # Yes, logger takes its '*args' as 'args'
        if self.isEnabledFor(25):
            self._log(25, message, args, **kws)
    logging.Logger.state = state

    if os.path.isfile(log_filename):
        logging.getLogger('L').handlers[0].doRollover()

init_log()
