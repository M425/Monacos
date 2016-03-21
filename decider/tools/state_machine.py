import time
import threading
import requests
import random
import json
import logging
import hashlib
from transitions import Machine
from transitions import logger
from aux import ipc
from aux import configurator as cc
from aux import parser
from tools.novawrap import NovaWrap
from tools.monawrap import MonaWrap
from tools.zoowrap import ZooWrap
logger.setLevel(logging.INFO)
FSM = None

'''
###############################################################################
###############################################################################

  ##   #    # #    #    ##### #    # #####  ######   ##   #####   ####
 #  #  #    #  #  #       #   #    # #    # #       #  #  #    # #
#    # #    #   ##        #   ###### #    # #####  #    # #    #  ####
###### #    #   ##        #   #    # #####  #      ###### #    #      #
#    # #    #  #  #       #   #    # #   #  #      #    # #    # #    #
#    #  ####  #    #      #   #    # #    # ###### #    # #####   ####

###############################################################################
###############################################################################
'''


class NamedThread(threading.Thread):
    def __init__(self, name):
        super(NamedThread, self).__init__()
        self.name = name
        self.log = logging.getLogger('L.'+name)
        self.cond = threading.Condition()
        self.whoami_host = cc.conf['whoami-host']
        self.whoami_man = cc.conf['whoami-man']

    def cond_wait(self, timeout):
        self.cond.acquire()
        self.cond.wait(timeout)
        self.cond.release()

    def sleep(self, t=-1):
        if t == -1:
            tts = int(cc.conf['decider']['timeout'][self.name])
        else:
            tts = t
        self.log.debug('sleeping %d seconds' % tts)
        self.cond_wait(tts)
'''
###############################################################################
'''


class Executor(NamedThread):
    def __init__(self):
        super(Executor, self).__init__('EXEC')
        self.stop = False

    def run(self):
        while not self.stop:
            _, res = ipc.get_execution()
            if res == 'quit':
                self.stop = True
                break
            self.sleep()
            self.log.info('Execution: %s' % res)
            if res == 'underload':
                FSM.underload()
            elif res == 'overload':
                FSM.overload()
            elif res == 'avoid':
                FSM.avoid()
            elif res == 'retry':
                FSM.retry()
            elif res == 'chillout':
                FSM.chillout()
            elif res == 'sleep':
                FSM.sleep()
            else:
                self.log.error('Execution not understood: %s' % res)
'''
###############################################################################
'''


class Statser(NamedThread):
    def __init__(self):
        super(Statser, self).__init__('STATS')
        self.stop = False
        my_db = cc.conf['influxdb']['dbname']
        host = cc.conf['influxdb']['hostname']
        port = cc.conf['influxdb']['port']
        self.address = 'http://%s:%s/write?db=%s' % (host, port, my_db)
        self.state_num = {
            'sleeping': 0,
            'underload': 1,
            'underload_avoid': 2,
            'wakeup': 3,
            'normal': 4,
            'confirmed': 5,
            'overload': 6,
            'overload_avoid': 7
        }

    def send_stats(self, st, vmsn):
        self.log.info('STATE: %s, VMSNUM: %s' % (st, str(vmsn)))
        d = 'monacos_stats,host="%s" numvms=%s,state="%s",state_int=%d' % (
            cc.conf['whoami'], vmsn, st, self.state_num[st])

        # self.log.debug(d)
        r = requests.post(self.address, data=d)
        if r.status_code < 200 or r.status_code >= 300:
            self.log.critical('influxdb error')
        return

    def run(self):
        global FSM
        while not self.stop:
            state = FSM.state
            vmsnum = len(FSM.novawrap.get_my_vms_dict()['ACTIVE'])
            self.send_stats(state, vmsnum)
            self.sleep()


'''
###############################################################################
'''


class Requester(NamedThread):
    def __init__(self, dst, action_id):
        super(Requester, self).__init__('Req')
        self.whoami_man = cc.conf['whoami-man']
        self.dst = dst
        self.action_id = action_id

    def sendresult(self, res):
        ipc.rpush(self.action_id+'-WORK',
                  json.dumps({
                    'action_id': self.action_id,
                    'host': self.dst,
                    'response': res}))

    def run(self):
        port = -1
        managers = cc.conf['compute']['managers']
        manager = next((m for m in managers if m['manager'] == self.dst), None)
        port = manager['decider_port']
        url = "http://%s:%s/request" % (self.dst, port)
        try:
            self.log.debug('%s: Requesting to %s:%s' %
                           (self.action_id, self.dst, port))
            r = requests.post(url, json={
                              'action_id': self.action_id,
                              'src': self.whoami_man})
        except requests.ConnectionError:
            self.log.error('Requester: ConnectionError')
            self.sendresult("ERROR")
            return -1
        if r.status_code != 200:
            self.log.error('%s: %s ERROR response: %d' %
                           (self.action_id, self.dst, r.status_code))
            self.sendresult("ERROR")
        else:
            self.log.debug('%s: Request to %s ok: %s' %
                           (self.action_id, self.dst, r.json()['response']))
            self.sendresult(str(r.json()['response']))
'''
###############################################################################
'''


class RequesterManager(NamedThread):
    def __init__(self, action_id, my_vms):
        super(RequesterManager, self).__init__('REQ_man')
        self.my_vms = my_vms
        self.hostlist = json.loads(ipc.get("hostlist"))
        self.action_id = action_id
        self.responses = {
            'host': {},
            'inv': {
                'HIGH': [],
                'MID': [],
                'NO': [],
                'SLEEP': [],
                'UNDEFINED': [],
                'ERROR': []
            }
        }
        self.workers = {}
        self.responses_inv = []
        for host in self.hostlist:
            self.responses[host['manager']] = 'UNDEFINED'
            self.workers[host['manager']] = \
                Requester(host['manager'], self.action_id)

    def run(self):
        # invite the others host
        for host in self.hostlist:
            self.workers[host['manager']].start()
        counter_responses = 0
        while counter_responses < len(self.hostlist):
            _, res = ipc.blpop(self.action_id+'-WORK')
            respobj = json.loads(res)
            counter_responses += 1
            if self.action_id != respobj['action_id']:
                self.log.critical('Conflict with action_id')
                raise Exception('Conflict with action id')
            self.responses['host'][respobj['host']] = respobj['response']
            self.responses['inv'][respobj['response']].append(respobj['host'])
        self.log.debug('%s: requester ends' % (self.action_id))
        ipc.rpush(self.action_id, json.dumps(self.responses))
'''
###############################################################################
'''


class LoadHandler(NamedThread):
    def __init__(self, name):
        super(LoadHandler, self).__init__(name)
        self.action_id = FSM.create_action()
        self.hostlist = json.loads(ipc.get("hostlist"))

    def get_host_by_man(self, man):
        managers = cc.conf['compute']['managers']
        for m in managers:
            if m['manager'] == man:
                return m

    def select_candidates(self, candidates):
        return candidates[0]

    def get_hosts_from_response(self, responses):
        candidates = []
        candidates += responses['inv']['HIGH']
        candidates += responses['inv']['MID']
        self.log.info('%s: Found %d candidates' %
                      (self.action_id, len(candidates)))
        return candidates

    def start_requester(self, migrating_vms):
        self.log.debug('%s: Start requester', self.action_id)
        requester = RequesterManager(self.action_id, migrating_vms)
        requester.start()
        (_, res) = ipc.blpop(self.action_id)
        responses = json.loads(res)
        self.log.info('%s: Responses: %s' % (
                      self.action_id, str(responses['inv'])))
        return responses

    def get_my_vms(self):
        vms_dict = {
            'ACTIVE': [],
            'SHUTOFF': [],
            'MIGRATING': [],
            'SUSPENDED': [],
            'BUILD': [],
            'DELETED': [],
            'ERROR': [],
            'HARD_REBOOT': [],
            'REBOOT': [],
            'PASSWORD': [],
            'REBUILD': [],
            'RESIZE': [],
            'REVERT_RESIZE': [],
            'UNKNOWN': [],
            'VERIFY_RESIZE': [],
            'PENDING': []
        }
        my_vms = FSM.novawrap.get_my_vms()
        for v in my_vms:
            vms_dict[v['status']].append(v)
        return vms_dict

    def migrate_shutoff(self, vm):
        return FSM.novawrap.migrate_shutoff(vm)

    def migrate_active(self, migramatch):
        man = migramatch['man']
        vm = migramatch['vm']
        host = migramatch['host']
        action_id = migramatch['action_id']
        self.log.info('%s: MIGRAMATCH FOUND:' % action_id)
        self.log.debug('man: %s' % man)
        self.log.debug('host: %s' % host)
        self.log.debug('vm: %s' % vm)
        url = "http://%s:%s/confirm" % (
              man, host['decider_port'])
        requests.post(url, json=migramatch)
        self.log.warning('LIVE-MIGRATING %s' % vm['name'])
        return FSM.novawrap.migrate(vm, host)

    def wait_for_migration(self, mm):
        vm = mm['vm']
        refreshed_vm = vm
        while True:
            self.sleep(5)
            if FSM.quitting:
                self.log.warning('Quitting...')
                return False
            elif FSM.state == self.name:
                refreshed_vm = FSM.novawrap.get_vm_info(vm['name'])
                self.log.info('checking :%s' % refreshed_vm)
                if refreshed_vm['status'] != "MIGRATING":
                    self.log.info('VM: %s no more migrating: %s' % (
                                  vm['name'], refreshed_vm['status']))
                    break
                self.log.debug('VM: %s is still migrating' % (vm['name']))
            else:
                self.log.warning(self.name+' is not the state anymore')
                return False
        return True

    def wait_for_migration_shutoff(self, vm):
        while True:
            time.sleep(3)
            self.log.info('checking :%s' % vm)
            refreshed_vm = FSM.novawrap.get_vm_info(vm['name'])
            if refreshed_vm['host'] != self.whoami_host:
                self.log.info('refreshed: %s' % str(refreshed_vm))
                self.log.info('VM: %s no more migrating: %s' % (
                              vm['name'], refreshed_vm['status']))
                break
            self.log.debug('VM: %s is still migrating' % (vm['name']))

    def get_migration_map(self, action_id, mans, vms):
        migramap = []
        '''
        c = 0
        for vm in vms:
            migramap.append({
                'vm': vm,
                'host': hosts[c]
                })
            c += 1
        '''
        # check PENDING
        if len(mans) > 0 and len(vms['PENDING']) > 0:
            for v in vms['PENDING']:
                self.log.debug('%s: %s' % (v['name'], v['status']))
                if v['status'] == "ACTIVE":
                    migramap.append({
                        'action_id': action_id,
                        'vm': v,
                        'man': mans[0]
                        })
                    break
        # check ACTIVE
        if len(mans) > 0 and len(vms['ACTIVE']) > 0:
            for v in vms['ACTIVE']:
                self.log.debug('%s: %s' % (v['name'], v['status']))
                if v['status'] == "ACTIVE":
                    migramap.append({
                        'action_id': action_id,
                        'vm': v,
                        'man': mans[0]
                        })
                    break
        for migramatch in migramap:
            migramatch['host'] = self.get_host_by_man(migramatch['man'])
            migramatch['src'] = self.whoami_man
        self.log.info('%s: Migration map done: %s' % (
                      self.action_id, str(migramap)))
        return migramap

    def filter_ne(self, l, key, value):
        return [vm for vm in l
                if vm[key] != value]

    def move_vm(self, vms, _id, src, dest):
        for vm in vms[src]:
            if vm['id'] == _id:
                vms[src].remove(vm)
                vms[dest].append(vm)

    def remove_vm(self, vms, _id, src):
        for vm in vms[src]:
            if vm['id'] == _id:
                vms[src].remove(vm)

    def check_state(self, loadtype, st, callback):
        FSM.mona.get_alarms()
        if loadtype == 'overload':
            alarm = FSM.mona.get_my_alarm_over()
        if loadtype == 'underload':
            alarm = FSM.mona.get_my_alarm_under()

        if alarm:
            if alarm['state'] == st:
                self.log.info('Alarm is %s!!' % st)
                ipc.execute(callback)
                return True
            else:
                self.log.debug('Alarm is not %s: %s' % (st, alarm['state']))
        else:
            self.log.critical('alarm %s not found!!' % loadtype)
        return False
'''
###############################################################################
'''


class Checker(NamedThread):
    def __init__(self, name):
        super(Checker, self).__init__(name)

    def check_all(self):
        ''' return sample: [{
        u'lifecycle_state': None,
        u'links': [...],
        u'updated_timestamp': u'2015-11-29T18:41:32.000Z',
        u'state_updated_timestamp': u'2015-11-29T18:41:32.000Z',
        u'metrics': [{
            u'dimensions': {
                u'hostname': u'compute01', u'service': u'monitoring'
            }, u'id': None, u'name': u'cpu.idle_perc'
        }],
        u'state': u'ALARM', u'link': None,
        u'alarm_definition': {
            u'severity': u'HIGH',
            u'id': u'e6fba7c7-9d3c-41d9-bca9-2c1a99787ead',
            u'links': [...],
            u'name': u'01-under-alarm'
        }, u'created_timestamp': u'20g15-11-29T18:40:04.000Z',
        u'id': u'7b4c26c1-4ad9-404f-bac6-539307af6b00'}, {...}]
        '''
        FSM.mona.get_alarms()
        alarm_under = FSM.mona.get_my_alarm_under()
        if alarm_under:
            if alarm_under['state'] == 'ALARM':
                self.log.info('Underload detected')
                ipc.execute('underload')
                return True
            else:
                self.log.debug('not underload state: %s' % alarm_under['state'])
        else:
            self.log.critical('alarm under not found!!')
        alarm_over = FSM.mona.get_my_alarm_over()
        if alarm_over:
            if alarm_over['state'] == 'ALARM':
                self.log.info('Overload detected')
                ipc.execute('overload')
                return True
            else:
                self.log.debug('not overload state: %s' % alarm_under['state'])
        else:
            self.log.critical('alarm over not found!!')
        return False

    def check_avoided(self):
        FSM.mona.get_alarms()
        alarm = None
        if self.type == 'overload':
            alarm = FSM.mona.get_my_alarm_over()
        elif self.type == 'underload':
            alarm = FSM.mona.get_my_alarm_under()
        if alarm:
            self.log.debug('Recheck state: '+str(alarm['state']))
            if alarm['state'] == 'ALARM':
                ipc.execute('retry')
                return True
            elif alarm['state'] == 'OK' or alarm['state'] == 'UNDEFINED':
                ipc.execute('chillout')
                return True
        else:
            self.log.critical('alarm '+self.type+'not found!!')
        return False
'''
###############################################################################
'''


class Avoid(Checker):
    def __init__(self, avoid_type):
        super(Avoid, self).__init__(str(avoid_type)+'_avoid')
        self.busy = False
        FSM.attempts[avoid_type] += 1
        self.type = avoid_type

    def run(self):
        self.busy = True
        self.sleep()
        if FSM.quitting:
            self.log.warning('Quitting...')
        elif FSM.state == self.type+'_avoid':
            self.log.debug('woke up')
            '''
            DEPRECATED
            mona.get_avg_cpu_idle()[0]['statistics'][0][1]
            return sample:
            [{u'dimensions': {
            u'hostname': u'compute01', u'service': u'monitoring'},
            u'statistics': [
              [u'2015-11-25T17:00:00Z', 98.21000000000001],
              [u'2015-11-25T17:10:00Z', 98.19],
              [u'2015-11-25T17:20:00Z', 98.21111111111112]
            ], u'id': u'2015-11-25T17:20:00Z',
            u'columns': [u'timestamp', u'avg'],
            u'name': u'cpu.idle_perc'}]
            '''
            if not self.check_avoided():
                self.log.critical('no alarm found!')
        else:
            self.log.warning(self.type+'_avoid is not the state anymore')

'''
###############################################################################
###############################################################################


 ####  #####    ##### #    # #####  ######   ##   #####   ####
#        #        #   #    # #    # #       #  #  #    # #
 ####    #        #   ###### #    # #####  #    # #    #  ####
     #   #        #   #    # #####  #      ###### #    #      #
#    #   #        #   #    # #   #  #      #    # #    # #    #
 ####    #        #   #    # #    # ###### #    # #####   ####


###############################################################################
###############################################################################
'''


class thread_overload(LoadHandler):
    def __init__(self):
        super(thread_overload, self).__init__('overload')

    def wake_up_one(self):
        self.log.info('%s: No candidates found,' % (self.action_id,) +
                      'trying to wake up machine...')
        sleepers = FSM.zoowrap.get_sleeping()
        self.log.info('Found %d sleeping host' % (len(sleepers)))
        if len(sleepers) > 0:
            self.log.info(' ==== >NOW WAKEUP IS NEEDED')
            url = "http://%s:%s/wake" % (sleepers[0]+"-man", "42501")  # TODO port
            requests.post(url)
            ipc.execute('avoid')
        else:
            ipc.execute('avoid')

    def run(self):
        # select vm to migrate
        vms = self.get_my_vms()
        while True:
            if FSM.quitting:
                self.log.warning('Quitting...')
                break
            elif FSM.state == 'overload':
                if len(vms['ACTIVE']) < 1:
                    self.log.error('HARD ERROR: overload and vms count < 1')
                if self.check_state('overload', 'OK', 'chillout'):
                    break
                # start distributed algorithm request
                responses = self.start_requester(vms['ACTIVE'])
                # choose host
                candidates = self.get_hosts_from_response(responses)
                if len(candidates) == 0:
                    self.wake_up_one()
                    break
                else:
                    # vm placement
                    migramap = self.get_migration_map(self.action_id,
                                                      candidates,
                                                      vms)
                    for migramatch in migramap:
                        migra_id = migramatch['vm']['id']
                        self.move_vm(vms, migra_id, 'ACTIVE', 'PENDING')
                        self.migrate_active(migramatch)
                        if not self.wait_for_migration(migramatch):
                            return
                        self.remove_vm(vms, migramatch['vm']['id'], 'PENDING')
                        self.sleep()
            else:
                self.log.warning(self.name+' is not the state anymore')
                break


'''
###############################################################################
'''


class thread_underload(LoadHandler):
    def __init__(self):
        super(thread_underload, self).__init__('underload')

    def run(self):
        # select vm to migrate
        vms = self.get_my_vms()
        while len(vms['ACTIVE']) > 0:
            if FSM.quitting:
                self.log.warning('Quitting...')
                break
            elif FSM.state == 'underload':
                # start distributed algorithm request
                if self.check_state('underload', 'OK', 'chillout'):
                    break
                responses = self.start_requester(vms['ACTIVE'])
                # choose host
                candidates = self.get_hosts_from_response(responses)
                if len(candidates) == 0:
                    self.log.info('%s: No candidates found, avoid underload' %
                                  self.action_id)
                    ipc.execute('avoid')
                    break
                else:
                    # vm placement
                    migramap = self.get_migration_map(self.action_id,
                                                      candidates,
                                                      vms)
                    for migramatch in migramap:
                        migra_id = migramatch['vm']['id']
                        self.move_vm(vms, migra_id, 'ACTIVE', 'PENDING')
                        self.migrate_active(migramatch)
                        if not self.wait_for_migration(migramatch):
                            return
                        self.remove_vm(vms, migra_id, 'PENDING')
                        self.sleep()
            else:
                self.log.warning(self.name+' is not the state anymore')
                break
        else:
            self.log.info('all active vms have migrated')
            '''
            not working
            while len(vms_dict['SHUTOFF']) > 0:
                vm = vms_dict['SHUTOFF'].pop()
                self.log.warning('SHUTOFF-MIGRATING %s' % vm['name'])
                self.migrate_shutoff(vm)
                self.wait_for_migration_shutoff(vm)
            '''
            self.log.debug(vms)
            sleepers = FSM.zoowrap.get_sleeping()
            self.log.debug(sleepers)
            if len(sleepers) < len(cc.conf['compute']['managers'])-1:
                self.log.warning('%s: Start sleeping' % self.action_id)
                ipc.execute('sleep')
                return
            else:
                self.log.warning('%s is the last Man standing' % cc.conf['whoami'])
                ipc.execute('avoid')
                return
'''
###############################################################################
'''


class thread_underload_avoid(Avoid):
    def __init__(self):
        super(thread_underload_avoid, self).__init__('underload')
'''
###############################################################################
'''


class thread_overload_avoid(Avoid):
    def __init__(self):
        super(thread_overload_avoid, self).__init__('overload')
'''
###############################################################################
'''


class thread_confirmed(NamedThread):
    def __init__(self):
        super(thread_confirmed, self).__init__('confirmed')

    def check_state_vm(self, migramatch):
        vm = migramatch['vm']
        self.log.info('checking :%s' % vm)
        refreshed_vm = FSM.novawrap.get_vm_info(vm['name'])
        if refreshed_vm['status'] != "MIGRATING" and \
           refreshed_vm['host'] == self.whoami_host:
            self.log.info('VM: %s no more migrating: %s, in %s' % (
                          vm['name'],
                          refreshed_vm['status'],
                          refreshed_vm['host']))
            FSM.received_vms.append(refreshed_vm)
            return False
        self.log.debug('VM: %s is still migrating' % (vm['name']))
        return True

    def run(self):
        while True:
            self.sleep()
            if FSM.quitting:
                self.log.warning('Quitting...')
                return
            elif FSM.state == 'confirmed':
                FSM.receiving_vms[:] = [mm for mm in FSM.receiving_vms
                                        if self.check_state_vm(mm)]
                if len(FSM.receiving_vms) == 0:
                    self.log.info('No more receiving vms')
                    self.log.info('State confirmed: chilling out')
                    ipc.execute('chillout')
                    return
            else:
                self.log.warning(self.name+' is not the state anymore')
                return
'''
###############################################################################
'''


class thread_sleeping(NamedThread):
    def __init__(self):
        super(thread_sleeping, self).__init__('sleeping')
        FSM.reset_attempts()

    def run(self):
        self.log.debug('Connecting to zookeeper')
        self.log.debug('Push sleeping state')
        FSM.zoowrap.sleep()
        self.log.info('Sleep state confirmed')
        self.log.warning(' =====> NOW READY TO SLEEP')
        while True:
            self.sleep()
            if FSM.quitting:
                self.log.warning('Quitting...')
                return
            elif FSM.state == 'sleeping':
                if len(FSM.novawrap.get_my_vms_dict()['ACTIVE']) > 0:
                    self.log.info('no more sleeping, WAKE UP')
                    ipc.execute('wake')
                    return
            else:
                self.log.warning(self.name+' is not the state anymore')
                return
'''
###############################################################################
'''


class thread_wakeup(Checker):
    def __init__(self):
        super(thread_wakeup, self).__init__('wakeup')
        FSM.reset_attempts()

    def run(self):
        self.log.debug('Connecting to zookeeper')
        self.log.debug('Delete sleeping state')
        FSM.zoowrap.wake()
        self.log.info('Wake up confirmed')
        self.sleep()
        if FSM.quitting:
            self.log.warning('Quitting...')
        elif FSM.state == self.name:
            # self.log.info('woke up, checking...')
            # if not self.check_all():
            #     self.log.info('Nothing detected, chilling out')
            #     ipc.execute('chillout')
            self.log.debug('woke up, switching normal')
            ipc.execute('chillout')
        else:
            self.log.warning(self.name+' is not the state anymore')
'''
###############################################################################
'''


class thread_normal(Checker):
    def __init__(self):
        super(thread_normal, self).__init__('normal')
        FSM.reset_attempts()

    def run(self):
        self.busy = True
        while True:
            self.sleep()
            if FSM.quitting:
                self.log.warning('Quitting...')
                break
            elif FSM.state == 'normal':
                self.log.debug('woke up, checking...')
                if self.check_all():
                    break
            else:
                self.log.warning(self.name+' is not the state anymore')
                break
'''
###############################################################################
###############################################################################

######  ####  #    #
#      #      ##  ##
#####   ####  # ## #
#           # #    #
#      #    # #    #
#       ####  #    #

###############################################################################
###############################################################################
'''


class StatesMachine(Machine):
    def __init__(self):
        self.FirstWAKE = True
        self.log = logging.getLogger('L.Machine')
        self.zoowrap = ZooWrap()
        self.novawrap = NovaWrap()
        self.mona = MonaWrap()
        states = [{
            'name': 'booting'
            }, {
            'name': 'normal',
            'on_enter': 'on_enter_state',
            'on_exit': 'on_exit_state'
            }, {
            'name': 'overload',
            'on_enter': 'on_enter_state',
            'on_exit': 'on_exit_state'
            }, {
            'name': 'overload_avoid',
            'on_enter': 'on_enter_state',
            'on_exit': 'on_exit_state'
            }, {
            'name': 'underload',
            'on_enter': 'on_enter_state',
            'on_exit': 'on_exit_state'
            }, {
            'name': 'underload_avoid',
            'on_enter': 'on_enter_state',
            'on_exit': 'on_exit_state'
            }, {
            'name': 'sleeping',
            'on_enter': 'on_enter_state',
            'on_exit': 'on_exit_state'
            }, {
            'name': 'wakeup',
            'on_enter': 'on_enter_state',
            'on_exit': 'on_exit_state'
            }, {
            'name': 'confirmed',
            'on_enter': 'on_enter_state',
            'on_exit': 'on_exit_state'
            }
        ]
        self.states_aux = {
            'normal': {
                'res_mood': 'HIGH', 'thr': None},
            'overload': {
                'res_mood': 'NO', 'thr': None},
            'overload_avoid': {
                'res_mood': 'NO', 'thr': None},
            'underload': {
                'res_mood': 'NO', 'thr': None},
            'underload_avoid': {
                'res_mood': 'MID', 'thr': None},
            'sleeping': {
                'res_mood': 'SLEEP', 'thr': None},
            'wakeup': {
                'res_mood': 'NO', 'thr': None},
            'confirmed': {
                'res_mood': 'NO', 'thr': None}
        }
        transitions = [
            {'trigger': 'boot',
             'source': 'booting', 'dest': 'wakeup'},
            {'trigger': 'overload',
             'source': 'normal', 'dest': 'overload'},
            {'trigger': 'avoid',
             'source': 'overload', 'dest': 'overload_avoid'},
            {'trigger': 'retry',
             'source': 'overload_avoid', 'dest': 'overload'},
            {'trigger': 'underload',
             'source': 'normal', 'dest': 'underload'},
            {'trigger': 'avoid',
             'source': 'underload', 'dest': 'underload_avoid'},
            {'trigger': 'retry',
             'source': 'underload_avoid', 'dest': 'underload'},
            {'trigger': 'sleep',
             'source': 'underload', 'dest': 'sleeping'},
            {'trigger': 'wake',
             'source': 'sleeping', 'dest': 'wakeup'},
            {'trigger': 'chillout',
             'source': 'wakeup', 'dest': 'normal'},
            {'trigger': 'chillout',
             'source': 'sleeping', 'dest': 'normal'},
            {'trigger': 'confirm',
             'source': 'normal', 'dest': 'confirmed'},
            {'trigger': 'confirm',
             'source': 'underload_avoid', 'dest': 'confirmed'},
            {'trigger': 'chillout',
             'source': 'confirmed', 'dest': 'normal'},
            {'trigger': 'chillout',
             'source': 'overload_avoid', 'dest': 'normal'},
            {'trigger': 'chillout',
             'source': 'underload_avoid', 'dest': 'normal'},
            {'trigger': 'chillout',
             'source': 'overload', 'dest': 'normal'},
            {'trigger': 'chillout',
             'source': 'underload', 'dest': 'normal'}
        ]
        Machine.__init__(self,
                         states=states, transitions=transitions,
                         initial='booting')
        self.history = [{
            'state': 'normal',
            'action_id': None
        }]
        self.receiving_vms = []
        self.received_vms = []

        self.whoami_host = cc.conf['whoami-host']
        self.whoami_man = cc.conf['whoami-man']
        self.root_id = '%s-%03d' % (
            hashlib.md5(self.whoami_host).hexdigest()[1:4],
            random.randrange(1, 999, 1))
        self.action_count = 0
        self.action_current = None

        self.compute_hosts = cc.conf['compute']['managers']
        self.hostlist = json.loads(ipc.get("hostlist"))

        self.attempts = {
            'overload': 0,
            'underload': 0
        }
        self.last = {
            'overload': 'OK',
            'underload': 'OK'
        }
        self.quitting = False
        self.executor = Executor()
        self.executor.start()
        self.statser = Statser()
        self.statser.start()
        self.log.info('Machine started [%s]' % self.whoami_host)

    '''
    AUXILIARY FUNCTIONS
    ###########################################################################
    '''
    def init_threads(self):
        t = {}
        for s in self.states:
            t[s['name']] = None
        return t

    def create_action(self):
        self.action_count += 1
        action_id = "%s-%03d" % (self.root_id, self.action_count)
        self.action_current = action_id
        self.history[-1]['action_id'] = action_id
        self.log.info('New action: %s' % action_id)
        return action_id

    def reset_attempts(self):
        self.attempts = {
            'overload': 0,
            'underload': 0
        }

    def new_stat(self):
        self.statser.cond.acquire()
        self.statser.cond.notify()
        self.statser.cond.release()

    def notify(self, state):
        self.states_aux[state]['thr'].cond.acquire()
        self.states_aux[state]['thr'].cond.notify()
        self.states_aux[state]['thr'].cond.release()

    def notify_if_up(self, state):
        if self.states_aux[state]['thr'] is not None and \
           self.states_aux[state]['thr'].isAlive():
            self.notify(state)

    def get_request_response(self):
        return self.states_aux[self.state]['res_mood']

    def start_my_thread(self, thr):
        self.states_aux[self.state]['thr'] = thr
        self.states_aux[self.state]['thr'].start()

    '''
    STATE FUNCTIONS
    ###########################################################################
    '''
    def on_exit_state(self):
        st = self.state
        self.log.state('EXIT STATE: '+st)
        for t in self.states_aux.keys():
            self.notify_if_up(t)

    def on_enter_state(self):
        st = self.state
        self.log.state('STATE: %s' % st)
        self.history.append({'state': st, 'action_id': None})
        for t in self.states_aux.keys():
            self.notify_if_up(t)
        self.new_stat()
        self.start_my_thread(globals()['thread_'+st]())

    def quit(self):
        self.quitting = True
        for t in self.states_aux:
            self.notify_if_up(t)
        ipc.execute('quit')

        time.sleep(0.1)
        if self.statser.isAlive():
            self.statser.stop = True
            self.statser.cond.acquire()
            self.statser.cond.notify()
            self.statser.cond.release()
        time.sleep(0.1)
        if self.executor.isAlive():
            self.log.warning("Thread Executor is alive, should i kill it?")
        time.sleep(0.1)


def get_machine():
    global FSM
    if FSM is None:
        FSM = StatesMachine()
        FSM.boot()
    return FSM
