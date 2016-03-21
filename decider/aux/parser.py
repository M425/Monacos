from aux import configurator as cc
import json
from aux import exc


def load_obj(s):
    return json.loads(s)


def validate(whoami, obj):
    # check if hostname is valid
    found = False
    for m in obj['metrics']:
        if m['dimensions']['hostname'] == whoami:
            found = True
    if not found:
        raise exc.NotMyAlarm()
