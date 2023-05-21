import os
import grpc
import time
import codecs
import requests
import ln.lightning_pb2 as rpc
import ln.lightning_pb2_grpc as lnrpc
import ln.router_pb2 as router
import ln.router_pb2_grpc as lnrouter
from typing import Any
from google.protobuf.json_format import MessageToDict
from ln import route_payment as routep, utils as utils


def get_channel_id(macaroon: str, secure_channel: grpc.Channel, channel_id: str) -> routep.ChannelEdge:
    """
    Gets data about a channel through its id, thus, the user must provide the lnd node's macaroon and any channel id
    :param macaroon: lnd node's macaroon
    :param secure_channel: secure channel got from host:port and channel credentials
    :param channel_id: id of the channel to get the data
    :return: channel's data
        The channel data is set with default values in case those values are None
    """
    stub = lnrpc.LightningStub(secure_channel)
    request = rpc.ChanInfoRequest(
        chan_id=channel_id
    )
    response = stub.GetChanInfo(request, metadata=[('macaroon', macaroon)])
    if response is not None:
        ch = MessageToDict(response, preserving_proto_field_name=True)
        if ch['node1_policy'] is not None and 'disabled' not in ch['node1_policy']:
            ch['node1_policy']['disabled'] = False
        if ch['node2_policy'] is not None and 'disabled' not in ch['node2_policy']:
            ch['node2_policy']['disabled'] = False
        rp1 = routep.RoutingPolicy(ch['node1_policy']['time_lock_delta'], ch['node1_policy']['min_htlc'],
                                   ch['node1_policy']['fee_base_msat'], ch['node1_policy']['fee_rate_milli_msat'],
                                   ch['node1_policy']['disabled'],
                                   ch['node1_policy']['max_htlc_msat'],
                                   ch['node1_policy']['last_update'])
        rp2 = routep.RoutingPolicy(ch['node2_policy']['time_lock_delta'], ch['node2_policy']['min_htlc'],
                                   ch['node2_policy']['fee_base_msat'], ch['node2_policy']['fee_rate_milli_msat'],
                                   ch['node2_policy']['disabled'],
                                   ch['node2_policy']['max_htlc_msat'],
                                   ch['node2_policy']['last_update'])
        secure_channel = routep.ChannelEdge(ch['channel_id'], ch['chan_point'], ch['last_update'], ch['node1_pub'],
                                            ch['node2_pub'],
                                            ch['capacity'], rp1, rp2)
        return secure_channel


def query_routes(g1, secure_channel: grpc.Channel, node_dict: dict, edge_dict: dict, node_origin: str,
                 node_destiny: str, payment_amount: int, is_manual_test: bool = False) -> routep.Payment:
    """
    Attempts to create a route to a destiny node capable of carrying a specific amount of satoshis.
    The route contains the  details required to create and send a HTLC, also including the necessary data
    for the Sphinx packet encapsulated within the HTLC.
    :return:
        routesLN, payment_amount, pubkey_origin, pubkey_destiny
    The method makes use of QueryRoutesRequest with the following main parameters:
        pub_key: pub_key node destiny
        source_pub_key: pub_key node origin
        fee_limit: this parameter is optional, but it may be used in case to delimit the max fee amount to charge
    """

    if is_manual_test:
        pubkey_origin = utils.get_pubkey_alias(node_origin, g1)
        pubkey_destiny = utils.get_pubkey_alias(node_destiny, g1)
    else:
        pubkey_origin = node_origin
        pubkey_destiny = node_destiny

    if pubkey_origin is not None and pubkey_destiny is not None:
        stub = lnrpc.LightningStub(secure_channel)
        request = rpc.QueryRoutesRequest(
            pub_key=pubkey_destiny,  # codecs.decode(pubkey_destiny, 'hex'),
            amt=payment_amount,
            amt_msat=None,
            final_cltv_delta=0,
            # fee_limit=ln.FeeLimit(percent=3),
            ignored_nodes=None,
            ignored_edges=None,
            source_pub_key=pubkey_origin,  # codecs.decode(pubkey_origin, 'hex'),
            use_mission_control=True,
            ignored_pairs=None,
            cltv_limit=0,
            dest_custom_records=None,
            outgoing_chan_id=0,
            last_hop_pubkey=None,
            route_hints=None,
            dest_features=None,
        )

        try:
            routes = stub.QueryRoutes(request)
            routes = MessageToDict(routes, preserving_proto_field_name=True)
            # print(response)
            if routes is not None:
                return routep.create_route(routes, pubkey_origin, pubkey_destiny, payment_amount, edge_dict,
                                           node_dict)
            else:
                return routep.Payment(pubkey_origin, pubkey_destiny, payment_amount, None, time.time_ns(),
                                      error="Routes not found - LND")
        except grpc.RpcError as e:

            print("{} Grpc Error Code:{}-{}-{}".format(utils.spaces, e.args[0].code.value[0],
                                                       e.args[0].code.value[1].upper(), e.args[0].details.upper()))
            return routep.Payment(pubkey_origin, pubkey_destiny, payment_amount, None, time.time_ns(),
                                  error=e.args[0].details + " - LND")

    else:
        return routep.Payment(pubkey_origin, pubkey_destiny, payment_amount, None, time.time_ns(),
                              error="Nodes not found - LND")


def describe_graph(macaroon, secure_channel, is_message: bool, parameters) -> dict:
    """
    Gathers data from the network to populate nodes and edges

    :param parameters:
    :param macaroon:
    :param secure_channel:
    :param is_message:
    :return:
    """
    stub = lnrpc.LightningStub(secure_channel)
    request = rpc.ListAliasesRequest()
    response = stub.ListAliases(request)
    dict_test = MessageToDict(response, preserving_proto_field_name=True)
    request = rpc.ChannelGraphRequest(
        include_unannounced=True
    )
    response = stub.DescribeGraph(request)
    dict_obj = utils.set_data_nodes_edges(MessageToDict(response, preserving_proto_field_name=True), is_message,
                                          parameters)

    return dict_obj


def send_payment_rpc(macaroon_dir: str, cert_dir: str, host: str, port: int, pubkey_destiny: str, payment_amount: int,
                     payment_hash: str, final_cltv_delta: int) -> Any:
    """
    Sends a payment to a destiny node by connecting to an origin node

    :param macaroon_dir: macaroon path of the origin node
    :param cert_dir: cert path of the origin node
    :param host: host of the origin node
    :param port: port of the origin node
    :param pubkey_destiny: pub key of the node destiny that receives the payment
    :param payment_amount: payment amount to send
    :param payment_hash: payment hash of the payment to send
    :param final_cltv_delta: cltv delta of the route
    :param fee_sat: total fee to send through the hops

    :return: response
    """

    macaroon = codecs.encode(open(macaroon_dir, 'rb').read(), 'hex')

    def metadata_callback(context, callback):
        callback([('macaroon', macaroon)], None)

    auth_creds = grpc.metadata_call_credentials(metadata_callback)
    # create SSL credentials
    os.environ['GRPC_SSL_CIPHER_SUITES'] = 'HIGH+ECDSA'
    cert = open(cert_dir, 'rb').read()
    ssl_creds = grpc.ssl_channel_credentials(cert)
    # combine macaroon and SSL credentials
    combined_creds = grpc.composite_channel_credentials(ssl_creds, auth_creds)
    # make the request
    secure_channel = grpc.secure_channel(str(host) + ':' + str(port), combined_creds)

    try:
        stub = lnrpc.LightningStub(secure_channel)
        request = rpc.SendRequest(
            # dest=str.encode(pubkey_destiny, encoding='utf-8'),
            # dest=str.encode(pubkey_destiny.encode().hex(), encoding='utf-8'),
    # dest=codecs.decode(pubkey_destiny, 'hex'),
            # dest=bytes(pubkey_destiny, 'utf-8'),
            # dest=str.encode(pubkey_destiny.encode().hex(base64), encoding='utf-8'),
            # dest=codecs.decode(pubkey_destiny.encode().hex(), 'hex'),
            # dest=codecs.decode(hex(int(pubkey_destiny, 16)), 'hex'),
            # dest=codecs.decode('0' * (len(hex(pubkey_destiny)) % 2) + hex(pubkey_destiny)[2:], 'hex'),
            # dest=codecs.decode(f'{pubkey_destiny:064x}', 'hex'),
            # dest=hex(pubkey_destiny).rstrip("L").lstrip("0x"),
            # dest=codecs.decode(pubkey_destiny, 'hex'),
            # dest=bytes.fromhex(pubkey_destiny),
    # dest=hex_string_to_bytes(pubkey_destiny),
            dest_string=pubkey_destiny,
            amt=payment_amount,
            # amt_msat=payment_amount * 1000,
            # payment_hash=bytes.fromhex(payment_hash),
            # payment_hash=codecs.decode(payment_hash, 'hex'),
            # payment_hash=hex_string_to_bytes(payment_hash),
            payment_hash_string=payment_hash,
            final_cltv_delta=final_cltv_delta,
            # fee_limit=rpc.FeeLimit(percent=5),
    # allow_self_payment=True
        )
        response = stub.SendPaymentSync(request)

        return response
    except grpc.RpcError as e:
        print('%s%s*** ERROR ON LND PAYMENT: %s' % (utils.spaces, utils.spaces, e._state.details))
        return None
    except TypeError as err:
        print('%s%s*** ERROR ON LND PAYMENT: %s' % (utils.spaces, utils.spaces, err.args[0]))
        return None
    except ValueError as er:
        print('%s%s*** ERROR ON LND PAYMENT: %s' % (utils.spaces, utils.spaces, er.args[0]))
        return None


def hex_string_to_bytes(hex_string):
    decode_hex = codecs.getdecoder("hex_codec")
    return decode_hex(hex_string)[0]


def send_payment_router(macaroon_dir: str, cert_dir: str, host: str, port: int, pubkey_destiny: str, payment_amount: int,
                        payment_hash, final_cltv_delta: int):
    cert = open(cert_dir, 'rb').read()
    ssl_creds = grpc.ssl_channel_credentials(cert)
    secure_channel = grpc.secure_channel(str(host) + ':' + str(port), ssl_creds)

    try:
        stub = lnrouter.RouterStub(secure_channel)
        request = router.SendPaymentRequest(
            dest=str.encode(pubkey_destiny, encoding='utf-8'),
            amt=payment_amount,
            amt_msat=payment_amount * 1000,
            payment_hash=str.encode(payment_hash, encoding='utf-8'),
            final_cltv_delta=final_cltv_delta,
            timeout_seconds=60,
            allow_self_payment=False,
            no_inflight_updates=False
        )
        for response in stub.SendPaymentV2(request, metadata=[('macaroon', macaroon_dir)]):
            return response
    except grpc.RpcError as e:
        print('%s%s*** ERROR ON LND PAYMENT: %s' % (utils.spaces, utils.spaces, e._state.details))
        return None
    except TypeError as err:
        print('%s%s*** ERROR ON LND PAYMENT: %s' % (utils.spaces, utils.spaces, err.args[0]))
        return None
    except ValueError as er:
        print('%s%s*** ERROR ON LND PAYMENT: %s' % (utils.spaces, utils.spaces, er.args[0]))
        return None


def get_info_url(host: str, port: int, macaroon: str, cert: str):
    """
    Gets info of the node by setting its connection parameters. Rest protocol

    :param host:host of the node
    :param port: port of the node
    :param macaroon: macaroon file of the node
    :param cert: cert file of hte node
    :return:
    """
    url = 'http://%s:%s/v1/%s' % (host, port, "getinfo")
    macaroon = codecs.encode(open(macaroon, 'rb').read(), 'hex')
    headers = {'Grpc-Metadata-macaroon': macaroon}
    return requests.get(url, headers=headers, verify=cert)


def get_info(host: str, port: int, macaroon: str, cert: str):
    """
    Gets info of the node by setting its connection parameters. Grpc protocol

    :param host:host of the node
    :param port: port of the node
    :param macaroon: macaroon file of the node
    :param cert: cert file of hte node
    :return:
    """
    try:
        macaroon = codecs.encode(open(macaroon, 'rb').read(), 'hex')
        os.environ['GRPC_SSL_CIPHER_SUITES'] = 'HIGH+ECDSA'
        cert = open(cert, 'rb').read()
        ssl_creds = grpc.ssl_channel_credentials(cert)
        channel = grpc.secure_channel(str(host) + ':' + str(port), ssl_creds)
        stub = lnrpc.LightningStub(channel)
        request = rpc.GetInfoRequest()
        response = stub.GetInfo(request, metadata=[('macaroon', macaroon)])

        return response
    except grpc.RpcError as err:
        return None
    except Exception as e:
        return None