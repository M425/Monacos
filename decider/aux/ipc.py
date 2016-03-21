import sys
import redis
from redis.exceptions import ConnectionError
from aux import configurator as cc
import logging

log = logging.getLogger('L.REDIS')
prekey = cc.conf['whoami']

try:
    r = redis.Redis(host='localhost', port=6379, db=0)
    r.delete(prekey+'-EXECUTOR')
except ConnectionError:
    log.error('Error in Redis Connection')
    sys.exit(-1)


def get(key):
    newkey = prekey+'-'+key
    return r.get(newkey)


def set(key, value):
    newkey = prekey+'-'+key
    return r.set(newkey, value)


def blpop(key):
    newkey = prekey+'-'+key
    return r.blpop(newkey)


def rpush(key, value):
    newkey = prekey+'-'+key
    return r.rpush(newkey, value)


def execute(value):
    newkey = prekey+'-EXECUTOR'
    return r.rpush(newkey, value)


def get_execution():
    newkey = prekey+'-EXECUTOR'
    return r.blpop(newkey)


def stats(value):
    newkey = prekey+'-STATS'
    return r.rpush(newkey, value)


def get_stats():
    newkey = prekey+'-STATS'
    return r.blpop(newkey)
