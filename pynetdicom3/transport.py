"""Implementation of the Transport Service.

The Transport Service provides the interface between the DICOM Upper Layer and
the TCP/IP networking layer.

------------
EXPERIMENTAL
------------
"""

from collections import namedtuple

import gevent
from gevent import socket
from gevent.server import StreamServer

from pynetdicom3.association import Association


class TransportConnect(object):
    """Represents a TRANSPORT CONNECT primitive

    State Machine
    -------------
    SCU
    ~~~
    When the AE is in Sta01 (Idle) and wants to connect to a peer (as an SCU)
    then it issues an A-ASSOCIATE request primitive (Evt01), performs
    AE-1 (Issue TRANSPORT CONNECT request primitive to the Transport Service)
    and moves to Sta04 (awaiting transport connection opening to complete).

    It then either:
    * Receives Evt02 (transport connection confirmation) and continues with
      association related events/actions.
    * Receives Evt15 (A-ABORT request primitive from the local AE), issues AA-2
      and goes to Sta01.
    * Receives Evt17 (transport connection closed indication), issues AA-4 and
      goes to Sta01.

    References
    ----------
    DICOM Standard, Part 8, Section 9.1.2.
    """
    pass


class TransportService(object):
    """

    Working Notes
    -------------
    * Port number should have no default, should be required and specified by
      the DUL.
    * Should support secure transport via 'Security Profiles' (PS3.15)
    * Should support at least 100 concurrent connections
    * Evt15 implies the ability to cancel a connection request at any point
      during the request (i.e. should be able to stop open_connection at any
      point if a A-P-ABORT request is received from local).

    Association
    -----------
    Requestor
    ~~~~~~~~~
    When an Association is to be established by the DUL (A-ASSOC-RQ primitive),
    a TRANSPORT CONNECT request primitive shall be issued to the TCP Transport
    Service (Active Open). Once the TCP Transport Connect Confirmation is
    received (Open Completed), an A-ASSOC-RQ PDU shall be sent/written on the
    now established transport connection.

    Acceptor
    ~~~~~~~~
    When a DUL becomes activated (Association Idle State - FSM Sta1), it shall
    wait for TCP Transport Connections in a passive mode by initiating a
    "listen". When an incoming TCP Transport Connection Indication is received
    from the network, it is accepted and a timer ARTIM shall be set. Any
    further exchange of PDUs (read/write) shall be performed as specified by
    the DUL's State Machine (including ARTIM expiration before an A-ASSOC-RQ PDU
    is received).

    Data Transfer
    -------------
    Data exchange of PDUs on an established TCP connection shall follow the
    specifications of the DULs State Machine and the DUL PDU structure.

    Closing a TCP Transport Connection
    ----------------------------------
    TCP Transport Connections shall be closed using the "don't linger" option.

    A TCP Transport Connection is closed under a number of situations (as
    described in the State Machine specifications). Some typical cases are:
    a. After an A-RELEASE-RQ has been sent and the A-RELEASE-RP PDU is received
    b. When a Transport Connection has been established by the DICOM remote UL
       Entity and no A-ASSOCIATION-RQ is received before the ARTIM timer
       expires.
    c. When an A-ABORT PDU has been received.
    d. When an A-ABORT PDU has been sent and the ARTIM timer expires before the
       Transport Connection is closed.
    e. When a TCP connection is being disconnected by the Transport Service
       Provider (i.e. network failure)
    f. When a TCP connection is being disconnected by the remote DICOM UL
       Entity.

    Except for when following the normal completion of an association reject,
    release or abort, and in specific situations (such as a temporary lack of
    resources), the State Machine should not disconnect a TCP connection or
    reject its establishment. The appropriate behaviour is to use the REJECT or
    ABORT services.

    The ARTIM Timer should not be used to oversee the association establishment
    or release. Such a mechanism falls under the protocol definition of the
    layer above the DUL (i.e. the AE).

    State Machine
    -------------
    Events
    ~~~~~~
    Evt2 - Transport connection confirmation (local transport service)
    Evt5 - Transport connection indication (local transport service)
    Evt17 - Transport connection closed indication (local transport service)

    States
    ~~~~~~
    Sta1 - Idle
    Sta2 - Transport connection open (awaiting A-ASSOC-RQ PDU)
    Sta4 - Awaiting transport connection opening to complete (from local
           transport service)
    Sta13 - Awaiting transport connection close indication (association no
            longer exists)

    Actions
    ~~~~~~~
    AE-1 - Issue TRANSPORT CONNECT request primitive to local transport service
    AE-4 - Issue A-ASSOC-RJ primitive and close transport connection
    AE-5 - Issue transport connection response primitive, start ARTIM
    AR-3 - Issue A-RELEASE confirmation primitive and close transport connection
    AA-2 - Stop ARTIM and close transport connection
    AA-3 - Issue A-ABORT/A-P-ABORT indication and close transport connection

    References
    ----------
    DICOM Standard, Part 8 - Network Communication Support for Message Exchange
    """
    def __init__(self, ae):
        """Initialise a new TransportService.

        Parameters
        ----------
        ae : applicationentity.ApplicationEntity
            The AE that we are providing transport services to.
        """
        self.ae = ae
        self.scp = None
        self.callbacks = {'connection_confirmation_indication' : [],
                          'connection_open_indication' : [],
                          'connection_close_indication' : []}

    def add_callback(self, callback, trigger):
        """Add a callback function to the TransportService.

        Callbacks will be called in the order they are added.

        Examples
        --------
        Print out the peer's IP address when a new connection is made.
        >>> def callable():
        ...     print(self)
        >>> transport = TransportService()
        >>> transport.add_callback(callable, 'on_receive_connection')

        from types import MethodType
        obj.method = MethodType(new_method, obj, MyObj)

        Parameters
        ----------
        callback : callable
            The callback function to add.
        trigger : str
            The trigger for the callback. Possible triggers corresponds to the
            State Machine Evt02, Evt05 and Evt17 events:
            - 'connection_confirmation_indication': called when acting as an
              SCU and the requested connection with the peer has been opened.
            - 'connection_open_indication': called when acting as an SCP and
              a peer has opened a new connection.
            - 'connection_close_indication': called when a connection is closed
              by either the local or the peer.
        """
        if trigger not in self.callbacks:
            raise ValueError('Invalid callback trigger')

        if callback not in self.callbacks[trigger]:
            self.callbacks[trigger].append(callback)

    def connection_indication(socket, addr):
        """A peer has connected to our SCP server.

        Parameters
        ----------

        """
        # Pass the connection to the ACSE (???)
        pass

        # Send Evt05 to the FSM
        pass

    def handle_server_connection(self, socket, addr):
        """Handle SCP connections.

        Requirements
        ------------
        * Can't return until we are done as that closes the socket
        * Must notify the FSM of:
            - Evt05: transport connection indication
            - Evt17: transport connection closed indication
        * Must pass off the socket/addr to whatever is handling the actual
          connection

        Parameters
        ----------
        socket : gevent.socket
            The connection's socket
        addr : tuple of (str, int)
            The (TCP/IP address, port number) of the connection.
        """
        print('New connection from %s:%s' % addr)

        # We can use the callbacks in the unit testing
        #   example: add in permanent loop to test concurrency
        for fn in self.callbacks['connection_open_indication']:
            try:
                fn(self, socket, addr)
            except Exception:
                pass

        # Testing, concurrency
        while True:
            gevent.sleep(0.5)

    def open_connection(self, primitive):
        """Open a TCP/IP connection to `addr` on `port`.

        Parameters
        ----------
        primitive : 2-tuple
            The TRANSPORT CONNECT request primitive, represented as a tuple of
            (str addr, int port), where addr is the TCP/IP address of the peer
            and port is the port number.

        Returns
        -------
        bool
            True if the connection is successful, False otherwise.
        """
        (addr, port) = primitive
        sock = socket.socket(type=socket.SOCK)
        sock.connect((addr, port))

        return True

    def start_server(self, port, server_params=None, ssl_args=None):
        """Start listening on `port` for connection requests.

        Connection
        ----------
        DICOM Standard Part 8, Section 9.1.4
            TCP transport connections shall be closed using the "don't linger"
            option.
        This is interpreted to mean that the defautlt timeout that we
        wait for client connections to stop is 0.

        SSL Support
        -----------
        The server can optionally work in SSL mode when given the correct
        keyword parameters in `ssl_args`. If using the ssl_context keyword
        argument, then the related ssl.SSLContext should either be imported
        from gevent.ssl or the process needs to be monkey-patched. See the
        gevent.server.StreamServer documentation for details.

        Parameters
        ----------
        port : int
            The port number to listen on for new connections.
        server_params : dict or None.
            If None (default), then the following gevent.server.StreamServer
            options will be used:
            * min_delay = 0.01
                The number of seconds to sleep in case there's an error in
                accept call(). For consecutive errors the delay will double
                until it reaches max_delay.
            * max_delay = 1.0
            * max_accept = 100
                The maximum number of concurrent connections.
            * stop_timeout = 0
                TCP transport connections shall be closed using the "don't
                linger" option (DICOM Standard Part 10, Section 9.1.4).
        ssl_args : dict or None
            If None (default), the the no SSL will be used. If the AE wants
            SSL then the dict should contain the keyword arguments that would
            apply to ssl.wrap_socket. Se the documentation for geven's
            StreamServer for more information.

        References
        ----------
        gevent.server.StreamServer
            http://www.gevent.org/gevent.server.html
        """
        # StreamServer(listener, handle=None, backlog=None, spawn='default',
        #              **ssl_args)
        #
        # listener
        #   Either an address that the server should bind on or a
        #   gevent.socket.socket instance that is already bound.
        # handle
        #   If given, the request handler. When the request handler returns,
        #   the socket used for the request will be closed.
        # backlog
        # spawn
        #   If provided, is called to create a new greenlet to run the handler
        #   (gevent.spawn() is used by default). Possible values are:
        #   * gevent.pool.Pool.spawn()
        #   * gevent.spawn_raw()
        #   * None
        #   * an integer - shortcut for gevent.pool.Pool(integer)
        self.scp = StreamServer(('localhost', port), self.handle_server_connection)

        # Set the server parameters
        params = {'stop_timeout' : 0,
                  'min_delay' : 0.01,
                  'max_delay' : 1.0,
                  'max_accept' : 100}
        if server_params:
            params.update(server_params)

        for name in params:
            setattr(self.scp, name, params[name])

        self.scp.stop_timeout = 0
        self.scp.serve_forever()

    def stop_server(self):
        """Stop listening for incoming connection requests."""
        if self.scp:
            self.scp.stop()
