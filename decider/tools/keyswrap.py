from keystoneclient.v2_0 import client
from keystoneclient.auth.identity import v2
from keystoneclient import session
from aux import configurator as cc


def get_client():
    return client.Client(
        username=cc.conf['keystone']['username'],
        password=cc.conf['keystone']['password'],
        tenant_name=cc.conf['keystone']['tenant_name'],
        auth_url=cc.conf['keystone']['auth_url'])


def get_session(role):
    d = cc.conf['keystone'][role]
    return session.Session(auth=v2.Password(
        auth_url=d['auth_url'],
        username=d['username'],
        password=d['password'],
        tenant_name=d['tenant_name']))


