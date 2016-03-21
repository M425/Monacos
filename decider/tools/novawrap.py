import logging
from aux import configurator as cc
from tools import keyswrap
from novaclient import client


class NovaWrap():
    def __init__(self, role='admin'):
        self.log = logging.getLogger('L.NOVA')
        self.sess = keyswrap.get_session(role)
        self.log.info('Start: session retrieved')
        self.whoami = cc.conf['whoami']
        self.client = client.Client("2", session=self.sess)
        self.log.info('Start: client created')

    def get_my_vms(self):
        search_opts = {'host': self.whoami, 'all_tenants': True}
        serverlist = self.client.servers.list(
            detailed=True, search_opts=search_opts)
        vmlist = []
        for server in serverlist:
            vmlist.append({
                'name': server.name,
                'id': server.id,
                'status': server.status,
                'flavor_id': server.flavor['id'],
                'host': server.__dict__['OS-EXT-SRV-ATTR:host']
            })
        self.log.debug('GetVms: vms retrieved')
        return vmlist

    def get_my_vms_dict(self):
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
        my_vms = self.get_my_vms()
        for v in my_vms:
            vms_dict[v['status']].append(v)
        return vms_dict

    def get_vm_info(self, vm_name):
        search_opts = {'name': vm_name, 'all_tenants': True}
        serverlist = self.client.servers.list(
            detailed=True, search_opts=search_opts)
        self.log.info('GetVmInfo: vm retrieved')
        if len(serverlist) == 1:
            server = serverlist[0]
            return {
                'name': server.name,
                'id': server.id,
                'status': server.status,
                'flavor_id': server.flavor['id'],
                'image_id': server.image['id'],
                'host': server.__dict__['OS-EXT-SRV-ATTR:host']
            }
        else:
            self.log.error('serverlist contains %d servers!' % len(serverlist))
            self.log.error('servers: %s' % str(serverlist))
            return None

    def migrate(self, vm, host):
        self.log.info('GetVms: vms parsed')
        return self.client.servers.live_migrate(vm['id'], host['realhost'],
                                                False, False)

    def migrate_shutoff(self, vm):
        self.log.info('GetVms: vms parsed')
        return self.client.servers.migrate(vm['id'])
