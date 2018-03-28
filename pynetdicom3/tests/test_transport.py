"""Tests for the Transport module"""

from struct import unpack

import gevent
from gevent.server import StreamServer

import pytest

from pynetdicom3.pdu import A_ASSOCIATE_RQ, A_ASSOCIATE_AC
from pynetdicom3.utils import pretty_bytes, PresentationContext


# Run for each incoming connection in a dedicated greenlet
# essentially this should represent an Association
def on_c_echo(socket, addr):
    """A Verification SCP

    Parameters
    ----------
    socket : gevent.socket
        The connection's socket
    addr : tuple of (str, int)
        The (TCP/IP address, port number) of the connection.
    """
    print('New connection from %s:%s' % addr)

    bytestream = bytes()

    # Get the data from the socket
    bytestream = socket.recv(1)
    pdu_type = unpack('B', bytestream)[0]
    if pdu_type not in [0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07]:
        print("Unrecognised PDU type: 0x%02x" % pdu_type)
    else:
        print("PDU type: 0x%02x" % pdu_type)

    # Byte 2 of a PDU is reserverd
    bytestream += socket.recv(1)

    # Bytes 3-6 is the PDU length
    length = socket.recv(4)
    bytestream += length
    length = unpack('>L', length)[0]
    print('PDU length: %d' %length)

    # Bytes 7 to (length - 7) is the remainder of the PDU
    bytestream += socket.recv(length)

    #print('Received A-ASSOCIATION-RQ PDU from peer')
    #for line in pretty_bytes(bytestream):
    #    print(line)

    # Convert bytestream to A-ASSOCIATE primitive
    if pdu_type == 0x01:
        assoc_rq = A_ASSOCIATE_RQ()
        assoc_rq.Decode(bytestream)

        # Display the assoc-rq debug
        receive_associate_rq(assoc_rq)

        # Convert to A-ASSOCIATE primitive
        primitive = assoc_rq.ToParams()

        # Set responding AE title
        primitive.called_ae_title = 'GEVENT_TEST'

        # Set maximum PDU receive length
        primitive.maximum_length_received = 16384

        # Set the presentation context response
        context = primitive.presentation_context_definition_list[0]
        reply = PresentationContext(context.ID, context.AbstractSyntax)
        reply.Result = 0x00
        reply.TransferSyntax = [context.TransferSyntax[0]]
        primitive.presentation_context_definition_list = []
        primitive.presentation_context_definition_results_list = [reply]
        primitive.result = 0

        a_assoc_ac = A_ASSOCIATE_AC()
        a_assoc_ac.FromParams(primitive)

        out = a_assoc_ac.Encode()

        socket.sendall(out)


def receive_associate_rq(a_associate_rq):
    """
    Placeholder for a function callback. Function will be called
    immediately after receiving and decoding an A-ASSOCIATE-RQ

    Parameters
    ----------
    a_associate_rq : pynetdicom3.pdu.A_ASSOCIATE_RQ
        The A-ASSOCIATE-RQ PDU instance
    """
    print("Association Received")

    # Shorthand
    pdu = a_associate_rq

    app_context = pdu.application_context_name.title()
    pres_contexts = pdu.presentation_context
    user_info = pdu.user_information

    #responding_ae = 'resp. AP Title'
    their_class_uid = 'unknown'
    their_version = 'unknown'

    if user_info.implementation_class_uid:
        their_class_uid = user_info.implementation_class_uid
    if user_info.implementation_version_name:
        their_version = user_info.implementation_version_name

    s = ['Request Parameters:']
    s.append('====================== BEGIN A-ASSOCIATE-RQ ================'
             '=====')
    s.append('Their Implementation Class UID:    {0!s}'
             .format(their_class_uid))
    s.append('Their Implementation Version Name: {0!s}'
             .format(their_version))
    s.append('Application Context Name:    {0!s}'
             .format(app_context))
    s.append('Calling Application Name:    {0!s}'
             .format(pdu.calling_ae_title.decode('utf-8')))
    s.append('Called Application Name:     {0!s}'
             .format(pdu.called_ae_title.decode('utf-8')))
    s.append('Their Max PDU Receive Size:  {0!s}'
             .format(user_info.maximum_length))

    ## Presentation Contexts
    s.append('Presentation Contexts:')
    for item in pres_contexts:
        s.append('  Context ID:        {0!s} (Proposed)'.format(item.ID))
        s.append('    Abstract Syntax: ={0!s}'.format(item.abstract_syntax))

        if item.SCU is None and item.SCP is None:
            scp_scu_role = 'Default'
        else:
            scp_scu_role = '{0!s}/{1!s}'.format(item.SCP, item.SCU)

        s.append('    Proposed SCP/SCU Role: {0!s}'.format(scp_scu_role))
        s.append('    Proposed Transfer Syntax(es):')
        for ts in item.transfer_syntax:
            s.append('      ={0!s}'.format(ts))

    ## Extended Negotiation
    if pdu.user_information.ext_neg is not None:
        s.append('Requested Extended Negotiation:')

        for item in pdu.user_information.ext_neg:
            s.append('  Abstract Syntax: ={0!s}'.format(item.UID))
            #s.append('    Application Information, length: %d bytes'
            #                                       %len(item.app_info))

            app_info = pretty_bytes(item.app_info)
            app_info[0] = '[' + app_info[0][1:]
            app_info[-1] = app_info[-1] + ' ]'
            for line in app_info:
                s.append('    {0!s}'.format(line))
    else:
        s.append('Requested Extended Negotiation: None')

    ## Common Extended Negotiation
    if pdu.user_information.common_ext_neg is not None:
        s.append('Requested Common Extended Negotiation:')

        for item in pdu.user_information.common_ext_neg:

            s.append('  Abstract Syntax: ={0!s}'
                     .format(item.sop_class_uid))
            s.append('  Service Class:   ={0!s}'
                     .format(item.service_class_uid))

            if item.related_general_sop_class_identification != []:
                s.append('  Related General SOP Class(es):')
                for sub_field in \
                            item.related_general_sop_class_identification:
                    s.append('    ={0!s}'.format(sub_field))
            else:
                s.append('  Related General SOP Classes: None')
    else:
        s.append('Requested Common Extended Negotiation: None')

    ## Asynchronous Operations Window Negotiation
    #async_neg = 'None'
    if pdu.user_information.async_ops_window is not None:
        s.append('Requested Asynchronous Operations Window Negotiation:')
        # FIXME
    else:
        s.append('Requested Asynchronous Operations Window ' \
                 'Negotiation: None')

    ## User Identity
    if user_info.user_identity is not None:
        usid = user_info.user_identity
        s.append('Requested User Identity Negotiation:')
        s.append('  Authentication Mode: {0:d} - {1!s}'
                 .format(usid.id_type, usid.id_type_str))
        if usid.id_type == 1:
            s.append('  Username: [{0!s}]'
                     .format(usid.primary.decode('utf-8')))
        elif usid.id_type == 2:
            s.append('  Username: [{0!s}]'
                     .format(usid.primary.decode('utf-8')))
            s.append('  Password: [{0!s}]'
                     .format(usid.secondary.decode('utf-8')))
        elif usid.id_type == 3:
            s.append('  Kerberos Service Ticket (not dumped) length: '
                     '{0:d}'.format(len(usid.primary)))
        elif usid.id_type == 4:
            s.append('  SAML Assertion (not dumped) length: '
                     '{0:d}'.format(len(usid.primary)))

        if usid.response_requested:
            s.append('  Positive Response requested: Yes')
        else:
            s.append('  Positive Response requested: None')
    else:
        s.append('Requested User Identity Negotiation: None')

    s.append('======================= END A-ASSOCIATE-RQ =================='
             '====')

    for line in s:
        print(line)



if __name__ == '__main__':
    ae = StreamServer(('localhost', 11112), on_c_echo)
    ae.serve_forever()
