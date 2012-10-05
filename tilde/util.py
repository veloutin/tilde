from twisted.python.failure import Failure

# Inspired by twisted.python.log err()
def log_err(_err, _logger, _message, *args, **kw):
    if _err is None:
        _err = Failure()
    if isinstance(_err, Failure):
        exc_info = _err.type, _err.value, _err.tb

    _logger.error(_message, *args, exc_info=exc_info, **kw)
