"""Implementation of the Transport Service.

The Transport Service provides the interface between the DICOM Upper Layer and
the TCP/IP networking layer.

------------
EXPERIMENTAL
------------
"""

from collections import namedtuple
import signal

import gevent
from gevent import socket
from gevent.server import StreamServer
from gevent.socket import create_connection

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

    Attributes
    ----------
    ae : pynetdicom3.applicationentity.ApplicationEntity
        The AE that the TransportService belongs to.
    scp : gevent.StreamServer or None
        When AE.start() has been called this is a gevent.StreamServer, None
        if the StreamServer has stopped or not started.
    callbacks : dict
        A dict containing the str {callback trigger : list of callback
        functions}. Possible callback triggers are:
        - 'connection_confirmation_indication'
        - 'connection_open_indication'
        - 'connection_close_indication'
    network_timeout : float
        The timeout on receiving data from the peer or sending data to the peer.

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
        self.network_timeout = 30

    def add_callback(self, callback, trigger):
        """Add a callback function to the TransportService.

        Callbacks will be called in the order they are added.

        Examples
        --------
        Print out the peer's IP address when a new connection is made.
        >>> def callable(*args, **kwargs):
        ...     print(kwargs['addr'])
        >>> ae = AE(port=11112, scp_sop_class=[VerificationSOPClass])
        >>> ae.transport.add_callback(callable, 'connection_open_indication')
        >>> ae.start()

        TODO: Define callback parameters for each trigger

        Parameters
        ----------
        callback : callable
            The callback function to add. Callbacks are triggered prior to
            sending the corresponding event to the State Machine (and as
            such may not necessarily represent the current state of the
            association).
        trigger : str
            The trigger for the callback. Possible triggers corresponds to the
            State Machine Evt02, Evt05 and Evt17 events:
            - 'connection_confirmation_indication': called when acting as an
              SCU and the requested connection with the peer has been opened.
            - 'connection_open_indication': called when acting as an SCP and
              a peer has opened a new connection.
            - 'connection_close_indication': called when a connection has
              closed, either because it the peer has timed out or the local
              AE has performed an action that resulted in its closure.
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
        network_timeout = gevent.Timeout(10)
        network_timeout.start()

        print('New connection from %s:%s' % addr)
        print('Socket timeout is', socket.timeout)

        # We can use the callbacks in the unit testing
        #   example: add in permanent loop to test concurrency
        for fn in self.callbacks['connection_open_indication']:
            try:
                fn(socket=socket, address=addr)
            except Exception:
                pass

        # Need to test the connection
        # The peer may shut down nicely and send a proper disconnection notice
        # Alternatively the peer may just stop responding, in which case
        #   we need to rely on a timeout
        try:
            assoc = Association(self.ae, client_socket=socket)
            ae.active_associations.append(assoc)


        except gevent.Timeout as t:
            if t is not network_timeout:
                print('Non-network timeout')
                raise

             ae.active_associations.remove(assoc)
            print('Connection timed out')
        # requires gevent 1.3
        #finally:
            #network_timeout.close()



        print('Closing connection...')

    def open_connection(self, primitive):
        """Open a TCP/IP connection to `addr` on `port`.

        Parameters
        ----------
        primitive : 2-tuple
            The TRANSPORT CONNECT request primitive, represented as a tuple of
            (str host, int port), where host is the TCP/IP address of the peer
            and port is the port number. A port number of 0 tells the OS to
            use the default.
        timeout : int
            The timeout (in seconds) for the connection attempt.

        Returns
        -------
        ???

        bool
            True if the connection is successful, False otherwise.
        """
        # What is dest?
        try:
            dest = create_connection(primitive, self.timeout)
        except IOError as exc:
            # Failed to connect
            return False

        return socket

    def request_connection(self, primitive, socket):
        """Request a connection"""
        g = Greenlet.spawn(open_connection, primitive)

        if g:
            # Trigger FSM Evt2
            pass
        else:
            # Trigger FSM Evt17
            pass


    def start_server(self, port, server_params=None, ssl_args=None, blocking=True):
        """Start listening on `port` for connection requests.

        Should we allow the use of multiple servers?

        I.e. should we use server.start() or server.serve_forever()?
        https://stackoverflow.com/questions/10287629/gevent-streamserver-start-does-not-seem-to-do-what-i-expect

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
        blocking : bool
            If True, the server is blocking, False otherwise.

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
        self.scp = StreamServer(('localhost', port),
                                self.handle_server_connection)

        # Set the server parameters
        params = {'stop_timeout' : 0,
                  'min_delay' : 0.01,
                  'max_delay' : 1.0,
                  'max_accept' : 100}
        if server_params:
            params.update(server_params)

        for name in params:
            setattr(self.scp, name, params[name])

        #gevent.signal(signal.SIGTERM, self.scp.close)
        #gevent.signal(signal.SIGINT, self.scp.close)
        #socket.setdefaulttimeout(30)

        self.scp.serve_forever()
        #self.scp.start()
        #if blocking:
        #    gevent.wait()

    def close(self):
        """Stop listening for incoming connection requests."""
        if self.scp.closed():
            sys.exit('Multiple exit signals received - aborting')
        else:
            StreamServer.close(self.scp)

    def stop_server(self):
        if self.scp:
            self.scp.stop()
