"""Implementation of the Transport Service.

The Transport Service provides the interface between the DICOM Upper Layer and
the TCP/IP networking layer.
"""


class TransportConnect(object):
    """Representation of the TRANSPOR CONNECT primitive

    When an Association is to be established by the DUL a TRANSPORT CONNECT
    request primitive shall be issued to the TCP Transport Service (Active
    Open).

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
    def __init__(self):
        """"""
        pass

    def open_connection(self, addr, port):
        """Open a TCP/IP connection to `addr` on `port`.

        Returns
        -------
        bool
            True if the connection is successful, False otherwise.
        """
        pass
