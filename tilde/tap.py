import logging.config

from twisted.internet import reactor
from twisted.python import usage
from twisted.python.log import PythonLoggingObserver

from tilde import loader, runner

class Options(usage.Options):
    optParameters = [
        ['config', 'c', '/etc/tilde/tilde.ini', "Main configuration file"],
        ['logging', 'l', None, "Logging configuration file"],
    ]

    optFlags = [
        ["verbose", "v"],
        ["debug", "d"],
        ["quiet", "q"],
        ["once", "1", "Run one update from the database (legacy run)"],
    ]

    @property
    def loglevel(self):
        if self["quiet"]:
            loglevel = logging.ERROR
        elif self["verbose"]:
            loglevel = logging.INFO
        elif self["debug"]:
            loglevel = logging.DEBUG
        else:
            loglevel = logging.WARN
        return loglevel


def makeService(config):
    if config['logging']:
        logging.config.fileConfig(config['logging'])
    else:
        logging.basicConfig(level=config.loglevel)

    obs = PythonLoggingObserver()
    obs.start()

    config = loader.load_config(config['config'])
    loader.setup_environment(config)
    return runner.getService(config, reactor)
