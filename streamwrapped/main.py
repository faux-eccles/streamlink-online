from itertools import starmap
import re
from urllib.parse import urlparse, urlunparse
from requests import session
import twisted
from twisted.protocols.tls import TLSMemoryBIOFactory
from twisted.web import server, resource, proxy, error
from twisted.internet import ssl, reactor, endpoints, endpoints

from streamlink import Streamlink
from streamlink.stream import HTTPStream

session = Streamlink()


class HTTPSReverseProxyResource(proxy.ReverseProxyResource, object):
    def proxyClientFactoryClass(self, *args, **kwargs):
        """
        Make all connections using HTTPS.
        """
        return TLSMemoryBIOFactory(
            ssl.optionsForClientTLS(self.host.decode("ascii")), True,
            super(HTTPSReverseProxyResource, self)
            .proxyClientFactoryClass(*args, **kwargs))

    def getChild(self, path, request):
        """
        Ensure that implementation of C{proxyClientFactoryClass} is honored
        down the resource chain.
        """
        child = super(HTTPSReverseProxyResource, self).getChild(path, request)
        return HTTPSReverseProxyResource(child.host, child.port, child.path,
                                         child.reactor)

class StreamlinkProxyResource(proxy.Resource):
    isLeaf=True
    proxyClientFactoryClass = proxy.ProxyClientFactory
    def __init__(self, slSessions: list, reactor=...):
        proxy.Resource.__init__(self)
        self.reactor = reactor
        self.streamLinkSessions = slSessions

    
    def render(self, request):
        """
        Render a request by forwarding it to the proxied server.
        """
        
        url = request.uri.replace(b"/" + b'/'.join(request.prepath) + b"/", b"").decode()
        url = urlparse(url)
        url = urlunparse(url).replace(":/", "://")
        url = url.replace(":///", "://") # vlc mangles the :// portion of the URL, attempt to coerce
        
        print(url, type(url))

        stream = session.streams(url)
        print(stream)
        if (len(stream) == 0):
            raise error.Error(404)
        
        target_stream = stream['best']

        if type(stream['best']) not in [HTTPStream]:

            print("unhandled strem")
            return b'unhandled strem'


        source_url = target_stream.url
        url_obj = urlparse(source_url)
        


        # RFC 2616 tells us that we can omit the port if it's the default port,
        # but we have to provide it otherwise
        if url_obj.port == 80 or url_obj.port == None:
            host = url_obj.hostname
        else:
            host = "%s:%d" % (url_obj.hostname, 443)
        request.requestHeaders.setRawHeaders(b"host", [host.encode("ascii")])
        request.content.seek(0, 0)
        qs = url_obj[4]
        if qs:
            rest = url_obj.path + "?" + qs
        else:
            rest = url_obj.path


        clientFactory = self.proxyClientFactoryClass(
            request.method,
            rest.encode(),
            request.clientproto,
            request.getAllHeaders(),
            request.content.read(),
            request,
        )



        if url_obj.scheme == "https":
            clientFactory = TLSMemoryBIOFactory(
                ssl.optionsForClientTLS(host), True,
                clientFactory
            )


        self.reactor.connectTCP(url_obj.hostname, 443 if url_obj.port == None else url_obj.port, clientFactory)
        return server.NOT_DONE_YET

class Simple(resource.Resource):
    isLeaf = False
    # def getChild(self, name, request):
    #     if name == '':
    #         return self
    #     return resource.Resource.getChild(self, name, request)
    
    def render_GET(self, request):
        url = request.uri[1:].decode('utf-8')
        print(url, type(url))

        streams = session.streams(url)
        print(streams)
        return 


root = Simple()
root.putChild(b'stream', StreamlinkProxyResource([], reactor=reactor))

site = server.Site(root)

endpoint = endpoints.TCP4ServerEndpoint(reactor, 8080, interface="127.0.0.1")
endpoint.listen(site)
reactor.run()