#!/opt/monacos/decider/env/bin/python
import sys
import signal
import logging
import aux.logger
import bottle
import transitions
import json
import os
from bottle import HTTPError
from aux import configurator as cc
from aux import exc
from aux import bottle_errors
from aux import parser
from aux import ipc
from tools import state_machine

quitting = False

log = logging.getLogger('L.main')
log_api = logging.getLogger('L.REST')


'''
API
'''


@bottle.post('/overload')
def bottle_overload():
    machine = bottle.app().state['machine']
    log_api.info('RECV: Overload')
    return 'Notification received'

    # retrieve body
    try:
        data = json.load(bottle.request.body)
    except ValueError:
        log_api.error('Retrieving: ValueError')
        raise HTTPError(400)

    # validate the data
    status = None
    try:
        parser.validate(machine.whoami_host, data)
        status = data['state']
    except KeyError:
        log_api.error('Validating: KeyError')
        raise HTTPError(400)
    except exc.NotMyAlarm:
        log_api.error('Validating: NotMyAlarm')
        raise HTTPError(400)

    log.info('notification:%s' % status)
    if status == "ALARM":
        try:
            machine.overload()
        except transitions.MachineError:
            log.error('Machine: MachineError, state=%s' % machine.state)
            raise HTTPError(409)
    elif status == "OK":
        if machine.state != 'normal':
            try:
                machine.chillout()
            except transitions.MachineError:
                log.error('Machine: MachineError, state=%s' % machine.state)
                raise HTTPError(409)
        else:
            log.warning('notification: already normal')
    return 'Notification received'


@bottle.post('/underload')
def bottle_underload():
    machine = bottle.app().state['machine']
    log_api.info('RECV: Underload')
    return 'Notification received'
    # retrieve body
    try:
        data = json.load(bottle.request.body)
    except ValueError:
        log_api.error('Retrieving: ValueError')
        raise HTTPError(400)
    # validate the data
    try:
        parser.validate(machine.whoami_host, data)
    except KeyError:
        log_api.error('Validating: KeyError')
        raise HTTPError(400)
    except exc.NotMyAlarm:
        log_api.error('Validating: NotMyAlarm')
        raise HTTPError(400)
    # execute data
    try:
        machine.underload()
    except transitions.MachineError:
        log.error('Machine: MachineError, state=%s' % machine.state)
        raise HTTPError(409)
    return 'Notification received'


@bottle.post('/request')
def bottle_request():
    machine = bottle.app().state['machine']

    # retrieve body
    try:
        data = json.load(bottle.request.body)
    except ValueError:
        log_api.error('Retrieving: ValueError')
        raise HTTPError(400)

    log_api.info('RECV: Request for offloading: %s from %s' % (
                 data['action_id'], data['src']))

    machine.mona.get_alarms()
    a1 = machine.mona.get_my_alarm_over()['state']
    if a1 == 'ALARM':
        res = 'NO'
    else:
        res = machine.get_request_response()

    bottle.response.content_type = 'application/json'
    return {
        'response': '%s' % str(res),
        'action_id': data['action_id'],
        'src': machine.whoami_man,
        'dst': data['src']
    }


@bottle.post('/confirm')
def bottle_confirm():
    machine = bottle.app().state['machine']

    # retrieve body
    try:
        data = json.load(bottle.request.body)
    except ValueError:
        log_api.error('Retrieving: ValueError')
        raise HTTPError(400)

    if 'action_id' not in data or\
       'src' not in data or\
       'vm' not in data or\
       'id' not in data['vm']:
        log_api.error('Parsing: invalid packet')
        raise HTTPError(400)

    log_api.info('RECV: Confirm action: %s from %s' % (
                 data['action_id'], data['src']))

    machine.receiving_vms.append(data)

    # execute
    try:
        machine.confirm()
    except transitions.MachineError:
        log.error('Machine: MachineError, state=%s' % machine.state)
        raise HTTPError(409)

    bottle.response.content_type = 'application/json'
    return {
        'action_id': data['action_id'],
        'src': machine.whoami_man,
        'dst': data['src']
    }


@bottle.post('/wake')
def bottle_wake():
    machine = bottle.app().state['machine']

    log_api.info('RECV: Request for wakeup')

    machine.wake()

    bottle.response.content_type = 'application/json'
    return {'status': 'ok'}


'''
start function
'''


def start():
    """ Start the decider
    """
    host = cc.conf['decider']['host']
    managers = cc.conf['compute']['managers']
    whoami = cc.conf['whoami']

    port = None
    for m in managers:
        if m['realhost'] == whoami:
            port = m['decider_port']
    ipc.set('self_port', port)

    hostlist = []
    for m in managers:
        if m['realhost'] != whoami:
            hostlist.append(m)
    ipc.set('hostlist', json.dumps(hostlist))

    bottle.debug(True)
    app = bottle.app()
    app.state = {
        'machine': state_machine.get_machine()
    }
    app.error_handler = aux.bottle_errors.ERRORS_HANDLERS

    log_api.info('Starting the decider, listening to %s:%s, pid:%s',
                 host, port, str(os.getpid()))
    quiet = cc.conf['decider']['log']['level'] != "DEBUG"
    bottle.run(host=host, port=port,
               quiet=quiet, reloader=cc.conf['development'])


def signal_handler(signal, frame):
    global quitting
    if not quitting:
        quitting = True
        log = logging.getLogger('L.QUIT')
        log.info('Gracefully shutting down decider')
        machine = bottle.app().state['machine']
        machine.quit()
        sys.exit()

signal.signal(signal.SIGINT, signal_handler)

start()
