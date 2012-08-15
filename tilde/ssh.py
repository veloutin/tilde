import sys, os
import struct

from zope.interface import implements
from twisted.internet.interfaces import IStreamClientEndpoint

from twisted.python.failure import Failure
from twisted.python.log import err
from twisted.internet.error import ConnectionDone
from twisted.internet.defer import Deferred, succeed, DeferredList
from twisted.internet.protocol import Factory, Protocol
from twisted.internet.endpoints import TCP4ClientEndpoint

from twisted.conch.ssh.common import NS, getNS
from twisted.conch.ssh.channel import SSHChannel
from twisted.conch.ssh.transport import SSHClientTransport
from twisted.conch.ssh.connection import SSHConnection
from twisted.conch.client.default import SSHUserAuthClient
from twisted.conch.client.options import ConchOptions

# setDebugging(True)

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
        self._user = user
        self.connection = None

    def connect(self):
        tcpEndpoint = TCP4ClientEndpoint(self._reactor,
                                         self._hostname,
                                         self._port)
        factory = MyFactory()
        factory.server = self
        factory.protocol = _CommandTransport
        factory.serverConnected = Deferred()

        d = tcpEndpoint.connect(factory)
        d.addErrback(factory.serverConnected.errback)

        return factory.commandConnected

    def runCommand(self, command, protocol):
        factory = Factory()
        factory.protocol = protocol
        factory.finished = Deferred()

        channel = _CommandChannel(command, factory)
        d = self.connection.openChannel(channel)
        d.addErrback(factory.finished.errback)
        return factory.finished


class _CommandTransport(SSHClientTransport):
    _secured = False

    def verifyHostKey(self, hostKey, fingerprint):
        return succeed(True)


    def connectionSecure(self):
        self._secured = True
        command = _CommandConnection(
            self.factory.command,
            self.factory.commandProtocolFactory,
            self.factory.commandConnected)
        userauth = SSHUserAuthClient(
            os.environ['USER'], ConchOptions(), command)
        self.requestService(userauth)


    def connectionLost(self, reason):
        if not self._secured:
            self.factory.commandConnected.errback(reason)



class _CommandConnection(SSHConnection):
    _ready = False

    def __init__(self, server):
        SSHConnection.__init__(self)
        self._server = server
        self._pendingChannelsDeferreds = []


    def serviceStarted(self):
        SSHConnection.serviceStarted(self)
        self._ready = True
        for d, channel in self._pendingChannelsDeferreds:
            self.openChannel(channel)
            d.callback(True)
        else:
            del self._pendingChannelsDeferreds[:]

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



class _CommandChannel(SSHChannel):
    name = 'session'

    def __init__(self, command, protocolFactory):
        SSHChannel.__init__(self)
        self._command = command
        self._protocolFactory = protocolFactory


    def channelOpen(self, ignored):
        print self, "channelOpen", id(self)
        self.conn.sendRequest(self, 'exec', NS(self._command))
        self._protocol = self._protocolFactory.buildProtocol(None)
        self._protocol.makeConnection(self)


    def request_exit_signal(self, data):
        signame, rest = getNS(data)
        core_dumped = struct.unpack('>?', rest[0])[0]
        msg, lang, rest = getNS(rest[1:], 2)
        print "Exit with SIG_{0}, dumped={1}, msg={2}, lang={3}".format(
            signame, core_dumped, msg, lang)

    def request_exit_status(self, data):
        stat = struct.unpack('>L', data)[0]
        print "Exit with status code %s" % stat


    def dataReceived(self, bytes):
        self._protocol.dataReceived(bytes)


    def closed(self):
        self._protocol.connectionLost(
            Failure(ConnectionDone("ssh channel closed")))




class SSHCommandClientEndpoint(object):

    def __init__(self, command, sshServer):
        self._command = command
        self._sshServer = sshServer


    def connect(self, protocolFactory):
        print "SSHCommand connect, factory: ", protocolFactory



class StdoutEcho(Protocol):
    def dataReceived(self, bytes):
        sys.stdout.write(bytes)
        sys.stdout.flush()

    def connectionMade(self):
        print self, "connectionMade", self.transport
        from twisted.internet import reactor
        reactor.callLater(3, self.transport.loseConnection)

    def connectionLost(self, reason):
        print self, "connectionLost", reason
        self.factory.finished.callback(reason)


class MyFactory(Factory):
    def __init__(self, ):
        print "MyFactory()"

    def startFactory(self):
        print self, "started"

    def stopFactory(self):
        print self, "stopped"

    def buildProtocol(self, addr):
        print self, "buildProtocol", addr
        return Factory.buildProtocol(self, addr)


def copyToStdout(endpoint):
    echoFactory = MyFactory()
    echoFactory.protocol = StdoutEcho
    echoFactory.finished = Deferred()
    d = endpoint.connect(echoFactory)
    d.addErrback(echoFactory.finished.errback)
    return echoFactory.finished



def main():
    from twisted.internet import reactor

    #from twisted.python.log import startLogging
    #startLogging(sys.stdout)
    server = SSHServer(reactor, "localhost", 22)
    d = server.connect()
    def runCommands(server):
        c1 = server.runCommand("hostname; sleep 1; hostname; sleep 3; echo NONO", StdoutEcho)
        c2 = server.runCommand("hostname -f; sleep 2; echo YAYA", StdoutEcho)
        c1.addErrback(err, "ssh command/copy to stdout failed")
        c2.addErrback(err, "ssh command/copy to stdout failed")
        dl = DeferredList([c1, c2])
        dl.addCallback(lambda ignored: reactor.stop())

    d.addCallback(runCommands)
    reactor.run()



if __name__ == '__main__':
    main()

