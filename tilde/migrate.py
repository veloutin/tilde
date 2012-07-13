import os
import logging

from twisted.internet import protocol, reactor, defer

RSYNC = next((o for o in (
    os.path.join(b, 'rsync') for b in os.environ.get("PATH", ".").split(":")
    ) if os.path.isfile(o) and os.access(o, os.X_OK)), "rsync")


class RsyncServer(protocol.ProcessProtocol):
    ''' Protocol for handling the Rsync Server

    Logs all stdout/stderr at info/error

    on_done, if provided, will have its callback or errback fired
    when the process ends.
    '''
    def __init__(self, on_done=None):
        self.on_done = on_done

    def connectionMade(self):
        logging.info("rsync started")
        self.transport.loseConnection()

    def processExited(self, reason):
        status = reason.value.exitCode
        if status in (0, 20):
            logging.info("rsync stopped normally")
            if self.on_done:
                self.on_done.callback(self)
        else:
            if status is None:
                signal = reason.value.signal
                logging.info("rsync stopped by signal: %s", signal)
            else:
                logging.info("rsync stopped with status: %s", status)
            self.on_done.errback(reason)




if __name__ == '__main__':
    logging.basicConfig(level=1)
    d = defer.Deferred()
    d.addErrback(logging.error)
    d.addCallback(lambda r: reactor.stop())

    pp = RsyncServer(d)
    p = reactor.spawnProcess(pp, RSYNC, [
            "rsync", "--daemon",
            "--config", "rs.conf",
            "--bwlimit=100",
            "--no-detach",
            "--port", "5000",
            "--address", "localhost",
        ],
    )
    reactor.run()

