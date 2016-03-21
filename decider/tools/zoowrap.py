from aux import configurator as cc
from kazoo.client import KazooClient
from kazoo.exceptions import NodeExistsError, NoNodeError
import logging


class ZooWrap():
    def __init__(self):
        self.zk = KazooClient(hosts="%s,%s" % (
            str(cc.conf['zookeeper']['host']),
            str(cc.conf['zookeeper']['port'])))
        self.zk.start()
        self.root = cc.conf['zookeeper']['rootpath']
        self.log = logging.getLogger('L.ZOOKEEPER')
        self.zk.ensure_path('/%s/sleeping' % (self.root))
        self.whoami = cc.conf['whoami']

    def get_sleeping(self):
        return self.zk.get_children('/%s/sleeping' % (self.root))

    def sleep(self):
        try:
            self.zk.create('/%s/sleeping/%s' % (self.root, self.whoami))
            self.log.info('Sleeping correctly')
        except NodeExistsError:
            self.log.error('Node already sleeping... seems weird')

    def wake(self):
        try:
            self.zk.delete('/%s/sleeping/%s' % (self.root, self.whoami))
        except NoNodeError:
            self.log.error('Node was not sleeping... seems weird')
