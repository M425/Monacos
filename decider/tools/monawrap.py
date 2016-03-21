from monascaclient import client
from monascaclient import ksclient
from aux import configurator as cc
import logging
from datetime import datetime, timedelta


class MonaWrap():
    def __init__(self):
        self.log = logging.getLogger('L.MONASCA')
        self.api_version = "2_0"
        self.whoami = cc.conf['whoami']
        ks_conf = cc.conf['keystone']['monasca']
        self.ks = ksclient.KSClient(
            auth_url=ks_conf['auth_url'],
            username=ks_conf['username'],
            password=ks_conf['password'])
        self.log.debug('Got keystone token')
        self.monasca_client = client.Client(
            self.api_version,
            self.ks.monasca_url,
            token=self.ks.token)
        self.log.debug('Got monasca client')
        self.alarms = None

    def get_avg(self, metric, period=600):
        now = datetime.utcnow()
        now = now.replace(microsecond=0)
        delta = timedelta(seconds=period+600)
        fields = {}
        fields['name'] = metric
        fields['period'] = period
        fields['start_time'] = (now-delta).isoformat()
        fields['dimensions'] = {'hostname': self.whoami}
        fields['statistics'] = 'avg'
        return self.monasca_client.metrics.list_statistics(**fields)

    def get_alarms(self):
        self.alarms = self.monasca_client.alarms.list()
        return self.alarms

    def get_avg_cpu_idle(self):
        return self.get_avg('cpu.idle_perc')

    def get_my_alarm(self, alarm_name):
        whoami = cc.conf['whoami-host']
        data = self.alarms
        # check if hostname is valid
        for obj in data:
            if obj['alarm_definition']['name'] == alarm_name:
                for m in obj['metrics']:
                    if m['dimensions']['hostname'] == whoami:
                        return obj
        return None

    def get_my_alarm_under(self):
        whoami = cc.conf['whoami-host']
        alarm_name = whoami[-2:]+'-under-alarm'
        return self.get_my_alarm(alarm_name)

    def get_my_alarm_over(self):
        data = self.alarms
        whoami = cc.conf['whoami-host']
        alarm_name = whoami[-2:]+'-over-alarm'
        return self.get_my_alarm(alarm_name)
