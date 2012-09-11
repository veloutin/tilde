import sys
import os
import struct

from cStringIO import StringIO

from twisted.python.failure import Failure
from twisted.python import log
from twisted.internet.error import (
    ProcessTerminated,
    ProcessDone,
    ConnectionDone,
)
from twisted.internet.defer import Deferred, succeed, DeferredList
from twisted.internet.protocol import Factory, Protocol
from twisted.internet.endpoints import TCP4ClientEndpoint

from twisted.conch.ssh.common import NS, getNS
from twisted.conch.ssh.channel import SSHChannel
from twisted.conch.ssh.transport import SSHClientTransport
from twisted.conch.ssh.connection import SSHConnection, EXTENDED_DATA_STDERR
from twisted.conch.client.default import SSHUserAuthClient
from twisted.conch.client.options import ConchOptions

# setDebugging(True)

class RemoteCommandProtocol(Protocol):
    """
    Base class for protocols that execute commands remotely
    """
    _finished = False
    reason = None

    def commandExited(self, reason):
        """
        Called when the remote command terminated.
        """
        self._finished = True
        self.reason = reason
        self.finished.callback(reason)

    def connectionLost(self, reason):
        """
        Called when the channel closes
        """
        if not self._finished:
            self.finished.callback(reason)
            self._finished = True
            self.reason = reason

    def errReceived(self, bytes):
        """ Implement this to receive standard error """

class RunCommandProtocol(RemoteCommandProtocol):
    def __init__(self):
        self.out = StringIO()
        self.err = StringIO()

    def dataReceived(self, bytes):
        self.out.write(bytes)

    def errReceived(self, bytes):
        self.err.write(bytes)


class StdoutEcho(RemoteCommandProtocol):
    def dataReceived(self, bytes):
        sys.stdout.write(bytes)
        sys.stdout.flush()

class SSHServer(object):
    def __init__(self,
                 reactor,
                 hostname="localhost",
                 port=22,
                 user=None,
                ):
        self._reactor = reactor
        self._hostname = hostname
        self._port = port
        if user is None:
            user = os.environ['USER']
        self.user = str(user)
        self.connection = None

    def connect(self):
        tcpEndpoint = TCP4ClientEndpoint(self._reactor,
                                         self._hostname,
                                         self._port)
        factory = Factory()
        factory.server = self
        factory.protocol = SSHTransport
        factory.serverConnected = Deferred()
        factory.serverConnected.addCallback(lambda *i: self)

        d = tcpEndpoint.connect(factory)
        d.addErrback(factory.serverConnected.errback)

        return factory.serverConnected

    def runCommand(self, command, protocol=RemoteCommandProtocol):
        p = protocol()
        p.finished = Deferred()
        p.finished.addErrback(lambda reason: reason.trap(ProcessDone))

        channel = _CommandChannel(command, p)
        d = self.connection.requestChannel(channel)

        d.addErrback(p.finished.errback)
        return p


class SSHTransport(SSHClientTransport):
    _secured = False

    def verifyHostKey(self, hostKey, fingerprint):
        return succeed(True)

    def connectionSecure(self):
        self._secured = True
        conn = _CommandConnection(self.factory)
        userauth = SSHUserAuthClient(
            self.factory.server.user, ConchOptions(), conn)
        userauth.preferredOrder = ['publickey']
        self.requestService(userauth)

    def connectionLost(self, reason):
        if not self._secured:
            self.factory.commandConnected.errback(reason)


class _CommandConnection(SSHConnection):
    _ready = False

    def __init__(self, factory):
        SSHConnection.__init__(self)
        self.factory = factory
        self._pendingChannelsDeferreds = []

    def serviceStarted(self):
        SSHConnection.serviceStarted(self)
        self._ready = True
        for d, channel in self._pendingChannelsDeferreds:
            self.openChannel(channel)
            d.callback(True)
        else:
            del self._pendingChannelsDeferreds[:]

        self.factory.server.connection = self
        self.factory.serverConnected.callback(self)

    def serviceStopped(self):
        for d, channel in self._pendingChannelsDeferreds:
            d.cancel()
        else:
            del self._pendingChannelsDeferreds[:]
        self._ready = False

        SSHConnection.serviceStopped(self)

    def requestChannel(self, channel):
        ''' Request that a channel be opened when the service is started

        @param channel: the C{SSHChannel} instance to open
        @return a C{Deferred}
        '''
        if self._ready:
            self.openChannel(channel)
            return succeed(True)

        else:
            d = Deferred()
            self._pendingChannelsDeferreds.append((d, channel))
            return d

    def loseConnection(self):
        for channel in self.channels.itervalues():
            channel.loseConnection()
        self.transport.loseConnection()


class _CommandChannel(SSHChannel):
    name = 'session'

    def __init__(self, command, protocol):
        SSHChannel.__init__(self)
        if isinstance(command, unicode):
            command = command.encode('utf-8')
        self._command = command
        self._protocol = protocol

    def channelOpen(self, ignored):
        log.msg('exec ' + self._command)
        self.conn.sendRequest(self, 'exec', NS(self._command))
        self._protocol.makeConnection(self)

    def request_exit_signal(self, data):
        signame, rest = getNS(data)
        core_dumped = struct.unpack('>?', rest[0])[0]
        msg, lang, rest = getNS(rest[1:], 2)
        self._protocol.commandExited(
            Failure(ProcessTerminated(signal=signame, status=msg)))

    def request_exit_status(self, data):
        stat = struct.unpack('>L', data)[0]
        if stat:
            res = ProcessTerminated(exitCode=stat)
        else:
            res = ProcessDone(stat)

        self._protocol.commandExited(Failure(res))

    def dataReceived(self, data):
        self._protocol.dataReceived(data)

    def extReceived(self, type, data):
        if type == EXTENDED_DATA_STDERR:
            self._protocol.errReceived(data)
        else:
            SSHChannel.extReceived(self, type, data)


def main():
    from twisted.internet import reactor

    from twisted.python.log import startLogging
    startLogging(sys.stdout)
    server = SSHServer(reactor, "localhost", 22)
    d = server.connect()

    def runCommands(server):
        p1 = server.runCommand("ls /root", RunCommandProtocol)
        p2 = server.runCommand("whoami", RunCommandProtocol)
        c1, c2 = p1.finished, p2.finished
        c1.addErrback(log.err, "ssh command/copy to stdout failed")
        c2.addErrback(log.err, "ssh command/copy to stdout failed")
        dl = DeferredList([c1, c2])
        def printResults(reslist):
            print "p1 out:", p1.out.getvalue()
            print "p1 err:", p1.err.getvalue()
            print "p2 out:", p2.out.getvalue()
            print "p2 err:", p2.err.getvalue()
            reactor.stop()

        dl.addCallback(printResults)

    d.addCallback(runCommands)
    reactor.run()



if __name__ == '__main__':
    main()
