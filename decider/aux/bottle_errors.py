import bottle
import logging
import traceback
import sys

log_api = logging.getLogger('L.REST')

ERRORS = {
    400: 'Bad input parameters',
    401: 'Unauthorized',
    403: 'Forbidden',
    404: 'Api not found',
    405: 'Method not allowed',
    409: 'Conflict',
    412: 'Precondition failed',
    500: 'Unknown error'
}

def log_rest_error(code):
    url = bottle.request.urlparts
    log_api.error("%s -> %s %s, %s %s" %
        (
            bottle.request.remote_addr,
            code,
            ERRORS[code],
            bottle.request.method,
            url[2]+url[3]+url[4]
        ))
    log_api.debug("Content: %s" %
        (
            str(bottle.request.body.read())
        ))

def error_handler(code):
    def gen_err(*arg):
        log_rest_error(code)
        return ERRORS[code]+'\n'
    return gen_err


ERRORS_HANDLERS = {}
for code in ERRORS:
    ERRORS_HANDLERS[code] = error_handler(code)

