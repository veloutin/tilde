import json
import logging
mlog = logging.getLogger(__name__)
import os

from zope.interface import implements

from twisted.cred.portal import IRealm, Portal
from twisted.cred.checkers import InMemoryUsernamePasswordDatabaseDontUse
from twisted.internet import defer
from twisted.python import failure
from twisted.web.resource import IResource, Resource
from twisted.web import server
from twisted.web.guard import HTTPAuthSessionWrapper, DigestCredentialFactory

from tilde.models import Home, HomeState
from tilde.commands import Commands


def use_to_json(obj):
    if hasattr(obj, "to_json"):
        return obj.to_json()
    else:
        raise TypeError(obj)

def to_json(o, request):
    request.setHeader("Content-Type", "application/json")
    if isinstance(o, failure.Failure):
        mlog.debug("Json request failure: %r", o)
        request.setResponseCode(500)
        try:
            json.dump({"error":str(o.value)}, request)
        except Exception, e:
            mlog.warning("Failed to dump response")
        request.finish()
        return

    try:
        request.write(json.dumps(o, default=use_to_json))
    except TypeError as e:
        mlog.warning("Failed to dump %r : %s", e, o)
        request.setResponseCode(500)
        try:
            json.dump({"error":str(e)}, request)
        except Exception, e:
            mlog.error("Jeez, wtf %r", e)
    request.finish()

class TildeRESTRealm(object):
    implements(IRealm)

    def requestAvatar(self, avatarId, mind, *interfaces):
        if IResource in interfaces:
            return (IResource, self.root, lambda: None)
        return NotImplementedError()

class HomeResource(Resource):
    isLeaf = 1

    def __init__(self, service, q):
        Resource.__init__(self)
        self.service = service
        self.q = q

    def render_GET(self, request):
        d = self.service.findHome(*self.q)
        d.addCallback(lambda homes: {"homes":homes})
        d.addBoth(to_json, request)
        return server.NOT_DONE_YET


class ByUUID(Resource):
    def __init__(self, service):
        Resource.__init__(self)
        self.service = service

    def getChild(self, name, request):
        return HomeResource(self.service, (Home.uuid == name.decode("utf-8"),))

class ByID(Resource):
    def __init__(self, service):
        Resource.__init__(self)
        self.service = service

    def getChild(self, name, request):
        return HomeResource(self.service, (Home.id == int(name),))


class Merge(Resource):
    isLeaf = 1

    def __init__(self, service):
        Resource.__init__(self)
        self.service = service


    def gotHomes(self, results):
        source, sstate, dest, dstate = results
        try:
            return {
                "source":source[0],
                "source_state":sstate,
                "dest":dest[0],
                "dest_state":dstate,
            }
        except IndexError:
            return defer.fail("Not found")

    def getHomes(self, source, dest):
        return defer.gatherResults([
                self.service.findHome(Home.id == source),
                self.service.findState(HomeState.id == source),
                self.service.findHome(Home.id == dest),
                self.service.findState(HomeState.id == dest),
            ],
            consumeErrors=True
        ).addCallback(self.gotHomes)

    @defer.inlineCallbacks
    def _getCurrentState(self, home, statuses):
        if len(statuses) > 1:
            yield self.service.updateOne(home, statuses)
            statuses = yield self.service.findState(Home.id == home.id)

        if statuses:
            status = statuses[0]
        else:
            status = None

        defer.returnValue((home, status))


    def chownRefPath(self, server, path, ref):
        return server.namedCommand(
            Commands.chown_ref.name,
            path=server.get_real_path(path),
            ref=server.get_real_path(ref),
        )


    @defer.inlineCallbacks
    def merge(self, homedict, path):
        source, sstatus = yield self._getCurrentState(
            homedict['source'],
            homedict['source_state'],
        )
        dest, dstatus = yield self._getCurrentState(
            homedict['dest'],
            homedict['dest_state'],
        )

        if not dstatus:
            yield self.service.create(dest)

        if not path:
            path = os.path.basename(os.path.normpath(source.path))

        source.server_name = dest.server_name
        source.path = os.path.join(dest.path, path)
        source.owner = dest.owner

        if sstatus:
            yield self.service.migrate(source, sstatus)
            sdf = self.service.serverManager.getServer(dest.server_name)
            sdf.addCallback(self.chownRefPath, source.path, dest.path)
            yield sdf

        yield self.service.deleteHome(source)

        defer.returnValue({"message":"success"})



    def render_GET(self, request):
        source = request.args.get('source_id', [None])[0]
        dest = request.args.get('dest_id', [None])[0]
        missing = set(["source_id", "dest_id"]).difference(request.args)
        if missing:
            request.setResponseCode(400)
            request.setHeader("Content-Type", "application/json")
            missing = ", ".join(missing)
            return json.dumps({"error":"Missing args: {0}".format(missing)})

        try:
            source, dest = int(source), int(dest)
        except ValueError, e:
            request.setResponseCode(400)
            request.setHeader("Content-Type", "application/json")
            return json.dumps({"error":str(e)})

        self.getHomes(source, dest).addBoth(to_json, request)
        return server.NOT_DONE_YET

    def render_POST(self, request):
        source = request.args.get('source_id', [None])[0]
        dest = request.args.get('dest_id', [None])[0]
        missing = set(["source_id", "dest_id"]).difference(request.args)
        if missing:
            request.setResponseCode(400)
            request.setHeader("Content-Type", "application/json")
            missing = ", ".join(missing)
            return json.dumps({"error":"Missing args: {0}".format(missing)})

        try:
            source, dest = int(source), int(dest)
        except ValueError, e:
            request.setResponseCode(400)
            request.setHeader("Content-Type", "application/json")
            return json.dumps({"error":str(e)})

        self.getHomes(source, dest).addCallback(
            self.merge,
            request.args.get('path', [""])[0].decode("utf-8"),
        ).addBoth(to_json, request)

        return server.NOT_DONE_YET

def getResource(rest_cfg, service):
    checkers = []
    if "users" in rest_cfg:
        checkers.append(
            InMemoryUsernamePasswordDatabaseDontUse(**rest_cfg["users"])
        )

    res = Resource()
    res.putChild("uuid", ByUUID(service))
    res.putChild("id", ByID(service))
    res.putChild("merge", Merge(service))


    #realm = TildeRESTRealm()
    #realm.root = res
    #portal = Portal(realm, checkers)
    #credFactory = DigestCredentialFactory("md5", "localhost:8081")

    #res = HTTPAuthSessionWrapper(portal, [credFactory])
    return res


if __name__ == '__main__':
    import logging
    logging.basicConfig(level=1)
    from twisted.python import log
    obs = log.PythonLoggingObserver()
    obs.start()
    from tilde.loader import load_config, setup_environment
    from tilde.runner import getService
    from twisted.internet import reactor

    cfg = load_config("etc/tilde.ini")
    setup_environment(cfg)
    service, _clean = getService(cfg, reactor)
    root = getResource(cfg["rest"], service)

    reactor.listenTCP(8081, server.Site(root))
    reactor.run()
