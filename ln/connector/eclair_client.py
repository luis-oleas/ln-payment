import time
import requests
from ln import route_payment as route_pay, utils as utils


def get_info(host: str = "localhost", port: int = 8290, user: str = "", passwd: str = "eclairpw"):
    """
    Gets info of a node connected by setting its parameters

    :param host: host of the node
    :param port: port of the node
    :param user: user of the node
    :param passwd: password of the node
    :return:
    """
    try:
        eclair = ClientEclair(host, port, user, passwd)
        result = eclair.getinfo()

        return result
    except requests.exceptions.ConnectionError as err:
        return None


def query_routes(node_destiny: str, amount: int, host: str = "localhost", port: int = 8290, user: str = "",
                 passwd: str = "eclairpw") -> route_pay.Payment:
    """
    Delivers a route given the destiny node, this implementation does not allow to set the origin destiny. It is
    dependant of the eclair node connected.
    :param node_destiny: Node to which a payment will be sent
    :param amount: the amount on satoshis to pay
    :param host: eclair host either (ip, localhost, 127.0.0.1)
    :param port: eclair port
    :param user: eclair user
    :param passwd: eclair password
    :return: Payment structure
        pubkey_origin
        pubkey_destiny
        payment_amount
        routes: Route
    To get the required route, it is required to get additional data, for instance the info about the node, most
    precisely the origen pub_key as well as the data about all nodes, all channels (only retrieves the pub_key of the
    nodes and the short channel id) and all updates (retrieves more detailed information about channels, however the
    data about of them are on two registers). Additionally, to construct the route, the response given by
    findroutetonode has to consider the hops from the last one, the reason is that the query route only contains
    the pubk_keys of the hops. Such procedure helps to gather the data about the channels as well as relevant info
    like is the fee. With the whole hop structure, it is necessary to reverse the order of the hops to get the final
    route.
    """
    pubkey_destiny = None
    eclair = ClientEclair(host, port, user, passwd)
    pubkey_origin = eclair.getinfo()['nodeId']
    nodes = {}
    channels = {}
    aux_channels = {}
    flag = False
    for node in eclair.nodes():
        nodes[node['nodeId']] = node
        if not flag and node['nodeId'] == node_destiny:
            pubkey_destiny = node['nodeId']
            flag = True

    for aux in eclair.allchannels():
        aux_channels[aux['shortChannelId']] = "{}-{}".format(aux['a'], aux['b'])

    if pubkey_destiny is not None:
        routes = eclair.findroutetonode(nodeId=pubkey_destiny, amountMsat=amount)
        # print(routes)
        route = route_pay.Route()
        routes_eclair = []
        total_time_lock = 0
        amount_msat = amount
        index = 0 if 'error' in routes else len(routes['routes'])

        list_channels = eclair.allupdates()
        for i in range(1, len(list_channels), 2):
            channel = list_channels[i]
            temp_id = aux_channels[channel['shortChannelId']]
            channels[temp_id] = channel

        if 'error' in routes:
            return route_pay.Payment(pubkey_origin, pubkey_destiny, amount, None, time.time_ns(), error=routes['error'])
        else:
            if index > 0 and len(routes['routes']) > 0:
                routes = routes['routes'][0]['nodeIds']
                for h in reversed(routes):
                    index -= 1
                    channel_id = "{}-{}".format(routes[index - 1], h)
                    if channel_id not in channels:
                        reverse_channel_id = "{}-{}".format(h, routes[index - 1])
                        if reverse_channel_id in channels:
                            channel = channels[reverse_channel_id]
                    else:
                        channel = channels[channel_id]
                    channel_id = utils.cl_to_lnd_scid(short_channel_id=channel['shortChannelId'])
                    # print(eclair.channel(channelId=channel['channelId']))
                    fee = float(0) if len(routes) == index + 1 or len(routes) == 1 else \
                        float(channel['feeBaseMsat']) / 1000
                    amount_msat += fee
                    hop = route_pay.Hop(channel_id=channel_id,
                                        channel_capacity=float(channel['htlcMaximumMsat']) / 1000,
                                        amt_2_fwrd=amount_msat,
                                        expiry=channel['cltvExpiryDelta'], amt_2_fwrd_msat=amount_msat * 1000,
                                        pub_key=h,
                                        tlv_pay_load=False,
                                        fee=fee,
                                        fee_msat=fee * 1000)
                    total_time_lock += hop.expiry
                    route.hops.append(hop)
                    if index == 1:
                        break
                hops_temp = route_pay.Route().hops
                for h in reversed(route.hops):
                    hops_temp.append(h)
                route.hops = hops_temp
                route.total_amt = amount_msat
                route.total_amt_msat = amount_msat * 1000
                route.total_fees = amount_msat - amount
                route.total_fees_msat = route.total_fees * 1000
                route.total_time_lock = total_time_lock
                route.success_prob = 1 / len(routes)

                routes_eclair.append(route)

                pubkey_origin_temp = pubkey_origin
                index = 0
                for hop in route.hops:
                    index += 1
                    pubkey_origin_temp = nodes[pubkey_origin_temp]['alias']
                    pubkey_destiny_temp = nodes[hop.pub_key]['alias']
                    utils.print_info_hop(hop.channel_id, hop.pub_key, index, None, None,
                                         pubkey_origin_temp, pubkey_destiny_temp)
                    pubkey_origin_temp = hop.pub_key
                utils.print_info_total_route(route.total_amt, route.total_fees, route.total_time_lock)

                return route_pay.Payment(pubkey_origin, pubkey_destiny, amount, routes_eclair, time.time_ns(),
                                         error=None)
            else:
                return route_pay.Payment(pubkey_origin, pubkey_destiny, amount, None, time.time_ns(),
                                         error="Routes no found - Eclair")
    else:
        return route_pay.Payment(pubkey_origin, pubkey_destiny, amount, None, time.time_ns(),
                                 error="Nodes not found - Eclair")


def send_payment(node_destiny: str, payment_amount: int, payment_hash: str, fee_sat: int, host: str, port: int,
                 user: str, passwd: str):
    """
    Sends a payment to a destiny node by connecting to a norigin node

    :param node_destiny: pub key of the node destiny that receives the payment
    :param payment_amount: payment amount to send
    :param payment_hash: payment hash of the payment to send
    :param fee_sat: total fee to send through the hops
    :param host: host of the origin node
    :param port: port of the origin node
    :param user: user of the origin node
    :param passwd: password of the origin node
    :return:
    """
    try:
        eclair = ClientEclair(host, port, user, passwd)
        result = eclair.sendtonode(nodeId=node_destiny, amountMsat=payment_amount * 1000, paymentHash=payment_hash,
                                   maxAttempts=5, feeThresholdSat=int(fee_sat))
        return result
    except ValueError as err:
        print('%s%s*** ERROR ON ECLAIR PAYMENT: %s' % (utils.spaces, utils.spaces, err.args[0].details))
        return None


class ClientEclair:
    def __init__(self, host: str, port: int, user: str, password: str, service_name=None, session=None):
        """
        Sets the parameters to make a request to an eclair node

        :param host: eclair host either (ip, localhost, 127.0.0.1)
        :param port: eclair port
        :param password: eclair password
        :param service_name: service/method used to perform an action
        :param session: handles the session given by the connection to the node
        """
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._session = session
        if session is None:
            self._session = requests.session()
        self._service_name = service_name
        self._url = 'http://%s:%s/%s' % (self._host, self._port, self._service_name)
        # print(self._url)

    def __getattr__(self, name):
        """
        Creates an object based on the service/method (findroutetonode, getinfo, channel, etc) to gather info about
        the node

        :param name: Service name
        :return: an object with the url set to perform an action
        """
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError
        if self._service_name is not None:
            name = "%s.%s" % (self._service_name, name)

        return ClientEclair(self._host, self._port, self._user, self._password, name, self._session)

    def __call__(self, *args, **kwargs):
        """
        Invokes to the post method and creates a session with the url and password passed by the user

        :param args:
        :param kwargs:
        :return:
        """
        return self._session.post(self._url, data=kwargs, auth=(self._user, self._password)).json()