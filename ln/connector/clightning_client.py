import time
# from lightning import LightningRpc, RpcError
from pyln.client import LightningRpc, RpcError
from ln import route_payment as route_payment, utils as utils


def query_routes(macaroon_dir: str, node_origin: str, node_destiny: str, amount: int) -> route_payment.Payment:
    """
    Creates the structure to perform a Payment using c-lightning implementation, for which, the method makes use of
    functionality light listnodes, getroute and listchannels. This functionality is used to ge data to create a payment
    as well as calculate totals such as amt, fee, time lock and success probability

    :param macaroon_dir: directory on which is the c-lightning implementation
    :param node_origin: node origin
    :param node_destiny: node destiny
    :param amount: amount to be paid to node destiny
    :return:
    """
    dict_nodes = {}
    pubkey_origin = pubkey_destiny = None
    clight = LightningRpc(macaroon_dir)
    try:
        route = route_payment.Route()
        nodes = clight.listnodes()
        for node in nodes['nodes']:
            dict_nodes[node['nodeid']] = node
            if node_origin == node['alias'] or node_origin == node['nodeid']:
                pubkey_origin = node['nodeid']
            if node_destiny == node['alias'] or node_destiny == node["nodeid"]:
                pubkey_destiny = node['nodeid']

        if pubkey_origin is not None and pubkey_destiny is not None:
            routes = clight.getroute(node_id=pubkey_destiny, msatoshi=amount * 1000, riskfactor=0, fromid=pubkey_origin)
            origin = pubkey_origin
            index = 0
            total_time_lock = 0
            routes_clight = []
            if routes is not None:
                for h in routes['route']:
                    index += 1
                    channel_id = utils.cl_to_lnd_scid(short_channel_id=h['channel'])
                    channels = clight.listchannels(short_channel_id=h['channel'])
                    # print(clight.listchannels(source='038bbe7e958a38f829ed3aa5f112bdeff5334a68be72adbe8e37c929507efa7781'))
                    # print(clight.getinfo())
                    fee = float(0) if len(routes['route']) == index or len(routes['route']) == 1 else \
                        float(channels['channels'][h['direction']]['base_fee_millisatoshi'])
                    hop = route_payment.Hop(channel_id=channel_id,
                                            channel_capacity=channels['channels'][h['direction']]['satoshis'],
                                            amt_2_fwrd=float(h['msatoshi']) / 1000,
                                            expiry=h['delay'], amt_2_fwrd_msat=float(h['msatoshi']),
                                            pub_key=h['id'],
                                            tlv_pay_load=True if 'style' in h and h['style'] == 'tlv' else False,
                                            fee=fee,
                                            fee_msat=fee * 1000)
                    total_time_lock += hop.expiry
                    # print(hop.__dict__)
                    # origin = clight.listnodes(node_id=origin)['nodes'][0]['alias']
                    origin = dict_nodes[origin]['alias']
                    destiny = dict_nodes[hop.pub_key]['alias']
                    utils.print_info_hop(channel_id, hop.pub_key, index, None, None, origin, destiny)
                    origin = hop.pub_key

                    route.hops.append(hop)
                route.total_amt = float(route.hops[0].amt_2_fwrd)
                route.total_amt_msat = float(route.hops[0].amt_2_fwrd_msat)
                route.total_fees = float(route.total_amt - amount)
                route.total_fees_msat = route.total_fees * 1000
                route.total_time_lock = total_time_lock
                route.success_prob = 1 / len(routes['route'])

                utils.print_info_total_route(route.total_amt, route.total_fees, route.total_time_lock)

                routes_clight.append(route)
                # print(routes)
                return route_payment.Payment(pubkey_origin, pubkey_destiny, amount, routes_clight, time.time_ns(),
                                             error=None)
            else:
                return route_payment.Payment(pubkey_origin, pubkey_destiny, amount, None, time.time_ns(),
                                             error="Routes not found - C-lightning")
        else:
            return route_payment.Payment(pubkey_origin, pubkey_destiny, amount, None, time.time_ns(),
                                         error="Nodes not found - C-lightning")
    except RpcError as error:
        print("{}{} Grpc Error Code:{}-{}".format("     ", error.args[0].split(',')[0].upper(), error.error['code'],
                                                  error.error['message']))
        return route_payment.Payment(pubkey_origin, pubkey_destiny, amount, None, time.time_ns(),
                                     error=error.error['message'] + " - C-lightning")


def send_payment(macaroon_dir: str, pubkey_destiny: str, payment_amount: int):
    """
    Sends a payment to a destiny node by connecting to an origin node

    :param macaroon_dir: macaroon path of the origin node
    :param pubkey_destiny: pub key of the node destiny that receives the payment
    :param payment_amount: payment amount to send
    :return:
    """
    try:
        clight = LightningRpc(macaroon_dir)
        result = clight.keysend(destination=pubkey_destiny, msatoshi=payment_amount * 1000, label="payment",
                                retry_for=60)

        return result
    except RpcError as err:
        print('%s%s*** ERROR ON C-LIGHTNING PAYMENT: %s' % (utils.spaces, utils.spaces, err.error))
        return None


def get_info(macaroon_dir: str):
    """
    Gets info of the node by setting its connection parameters. Grpc protocol

    :param macaroon_dir: macaroon path of the origin node
    :return:
    """
    clight = LightningRpc(macaroon_dir)
    try:
        result = clight.getinfo()
        return result
    except RpcError as error:
        return None


def get_nodes(macaroon_dir: str):
    """
    Get info of all the nodes

    :param macaroon_dir:
    :return:
    """
    clight = LightningRpc(macaroon_dir)
    try:
        result = clight.listnodes()
        return result
    except RpcError as error:
        return None
