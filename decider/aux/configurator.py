import os
import yaml
import logging
import sys
import socket

glob_name = 'monacos'

default_config = {
    'log': {
        'level': 'INFO',
        'filename': 'decider.log',
        'folder': '/opt/'+glob_name+'/decider/log/'
    }
}
loaded_config = None
args_config = {}

conf = default_config

if loaded_config is None:
    config_root = os.getenv('MONACOS_ROOT_CONFIG',
                            '/opt/'+glob_name+'/decider/conf/')
    config_file = config_root+'decider.yaml'
    with open(config_file, "r") as f:
        loaded_config = yaml.load(f)
        conf.update(loaded_config)
        conf['whoami-host'] = conf['whoami']
        conf['whoami-man'] = conf['whoami']+'-man'


def setargs(argv):
    global conf
    config_hostname = False
    for arg in argv:
        if arg == '--config-whoami':
            config_hostname = True
        if arg[0:2] == '--' and '=' in arg:
            a = arg[2:].split('=')
            if a[0] == 'whoami':
                config_hostname = True
            args_config[a[0]] = a[1]
    conf.update(args_config)
    conf['whoami-host'] = conf['whoami']
    conf['whoami-man'] = conf['whoami']+'-man'
    if not config_hostname:
        whoami = socket.gethostname()[:-4]
        conf['whoami'] = whoami
        conf['whoami-host'] = conf['whoami']
        conf['whoami-man'] = conf['whoami']+'-man'

setargs(sys.argv)
