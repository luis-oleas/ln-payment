import time
import queue
import networkx as nx
from typing import Tuple
from ln import route_payment as route_pay, utils as utils


def path_cost(graph: nx, path: [], payment_amount: int = 0) -> Tuple[int, list]:
    """
    Traverses the given path to determine its total path cost and the value for each hop, thus, the function gathers
    the channels from each pair of nodes on the path, then it calculates the lowest fees for policy_source and
    policy_destiny and finally determines the lowest fee between both policies

    :param payment_amount: amount to be paid to destiny node
    :param graph: structure that contains the whole data about the network
    :param path: route to transverse to get its path cost
    :return: cost of the given path, and the fee charged on each hop
    """
    path_costs = 0
    key_values = []
    val = None
    fee = None
    for i in range(len(path)):
        if i > 0:
            edge = (path[i - 1], path[i])
            channels = graph.get_edge_data(*edge)
            if 0 not in channels and 1 not in channels:
                val_dest, val_source = get_min_source_dest_channels(channels, payment_amount)
                if val_source[1]['policy_source'] is not None:
                    if val_dest[1]['policy_dest'] is not None:
                        min_htlc_source = 1 if 'min_htlc' not in val_source[1]['policy_source'] else \
                            int(val_source[1]['policy_source']['min_htlc'])
                        min_htlc_dest = 1 if 'min_htlc' not in val_dest[1]['policy_dest'] else \
                            int(val_dest[1]['policy_dest']['min_htlc'])
                        if int(val_source[1]['policy_source']['fee_base_msat']) <= int(
                                val_dest[1]['policy_dest']['fee_base_msat']) \
                                and min_htlc_source <= min_htlc_dest:
                            fee = int(val_source[1]['policy_source']['fee_base_msat'])
                            val = val_source[0]
                        else:
                            fee = int(val_dest[1]['policy_dest']['fee_base_msat'])
                            val = val_dest[0]
                    else:
                        fee = int(val_source[1]['policy_source']['fee_base_msat'])
                        val = val_source[0]
                else:
                    if val_dest[1]['policy_dest'] is not None:
                        fee = int(val_dest[1]['policy_dest']['fee_base_msat'])
                        val = val_dest[0]
                key_values.append((val, fee))
                path_costs += fee
    return path_costs, key_values


def calculate_weight(graph: nx, u, v, payment_amount: int = 0) -> int:
    """
    Calculates the weight (cost given by the fee) for each pair of nodes (u, v) by comparing that either value between
    the fees of the source policy and destiny policy is the lowest, therefore, this method is used to determine the
    shortest past between node origin and node destiny. Hence, the cost of the path is essential to get this path.

    :param payment_amount: amount to be paid to node destiny
    :param graph: structure that contains the whole data about the network
    :param u: node u
    :param v: node v
    :return: cost of channel
    """
    cost = None
    channels = graph.get_edge_data(*(u, v))
    if 0 not in channels and 1 not in channels:
        val_dest, val_source = get_min_source_dest_channels(channels, payment_amount)
        if val_source[1]['policy_source'] is not None:
            if val_dest[1]['policy_dest'] is not None:
                min_htlc_source = 1 if 'min_htlc' not in val_source[1]['policy_source'] else \
                    int(val_source[1]['policy_source']['min_htlc'])
                min_htlc_dest = 1 if 'min_htlc' not in val_dest[1]['policy_dest'] else \
                    int(val_dest[1]['policy_dest']['min_htlc'])
                if int(val_source[1]['policy_source']['fee_base_msat']) <= int(val_dest[1]['policy_dest']['fee_base_msat']) \
                        and min_htlc_source <= min_htlc_dest:
                    cost = int(val_source[1]['policy_source']['fee_base_msat']) + min_htlc_source
                else:
                    cost = int(val_dest[1]['policy_dest']['fee_base_msat']) + min_htlc_dest
            else:
                cost = int(val_source[1]['policy_source']['fee_base_msat']) + \
                       int(val_source[1]['policy_source']['min_htlc'])
        else:
            if val_dest[1]['policy_dest'] is not None:
                cost = int(val_dest[1]['policy_dest']['fee_base_msat']) + int(val_dest[1]['policy_dest']['min_htlc'])

    return cost


def get_min_source_dest_channels(channels, payment_amount: int):
    """
    Gets the minimum fee to charge from both policy_source (node_policy_1) and policy_destiny (node_policy_2) of all
    the channels between two nodes by
    *   Ascertaining that either policy exist, and it is enabled and
    *   Comparing that the channel can forward the payment (min_htlc < payment_amount) and its  balance is greater
        that the amount to forward (balance > fee_base_msat + payment_amount)

    :param channels: all channels between a pair of nodes
    :param payment_amount: payment amount to forward to next node
    :return: the lowest fees from policy_source and policy_destiny among all channels
    """
    val_source = min(channels.items(), key=lambda val_channels: 'policy_source' in val_channels[1]
                                                                and val_channels[1]['policy_source'] is not None
                                                                and not val_channels[1]['policy_source']['disabled']
                                                                and int(
        val_channels[1]['policy_source']['min_htlc']) < payment_amount
                                                                and int(val_channels[1]['balance']) > int(
        val_channels[1]['policy_source']['fee_base_msat']) + payment_amount)
    val_dest = min(channels.items(), key=lambda val_channels: 'policy_dest' in val_channels[1]
                                                              and val_channels[1]['policy_dest'] is not None
                                                              and not val_channels[1]['policy_dest']['disabled']
                                                              and int(
        val_channels[1]['policy_dest']['min_htlc']) < payment_amount
                                                              and int(val_channels[1]['balance']) > int(
        val_channels[1]['policy_dest']['fee_base_msat']) + payment_amount)
    return val_dest, val_source


def validate_policies(source, dest) -> Tuple[int, int, int]:
    """
    Compares the values of the source and destiny policies to find out the lowest min_htlc, fee and fee_rate, i.e.
    those three values are compared to get the policy with those lowest values

    :param source: source_policy to be compared
    :param dest: destiny_policy to be compared
    :return: min_htlc, fee and fee_rate of thw policy with the lowest values
    """
    if source is not None:
        if dest is not None:
            if int(source['min_htlc']) <= int(dest['min_htlc']) and int(source['fee_base_msat']) < int(
                    dest['fee_base_msat']):
                min_htlc = int(source['min_htlc'])
                fee = int(source['fee_base_msat'])
                fee_rate = int(source['fee_rate_milli_msat'])
            else:
                min_htlc = int(dest['min_htlc'])
                fee = int(dest['fee_base_msat'])
                fee_rate = int(dest['fee_rate_milli_msat'])
        else:
            min_htlc = int(source['min_htlc'])
            fee = int(source['fee_base_msat'])
            fee_rate = int(source['fee_rate_milli_msat'])
    else:
        min_htlc = int(dest['min_htlc'])
        fee = int(dest['fee_base_msat'])
        fee_rate = int(dest['fee_rate_milli_msat'])

    return min_htlc, fee, fee_rate


def spy(graph: nx, source: str, target: str, num_k: int, payment_amount: int) -> Tuple[list, list]:
    """
    Gets the shortest paths according to a given num_k between a source node, and a target node which forward a certain
    payment amount and fees through a path of nodes. Initially the method calculates the shortest path, which becomes
    the seed path. From there this implementation of Yen's algorithm find out the num_k the shortest paths which path
    costs are similar or slightly greater than the cost of seed path. To achieve those paths, the algorithm makes use of
    a couple of queues (A y B), the first one is on charge of gather the final shortest paths, and the other one has the
    possible candidates to be passed to the first queue. Additionally, the algorithm uses a root path which is the
    deviation of the seed path, and the spur node which is the node from which it finds the alternative routes.

    :param graph: structure that contains the whole data about the network
    :param source: node origin
    :param target: node destiny
    :param num_k: number of the shortest path found from the seed path
    :param payment_amount: amount to be paid to node destiny
    :return: list of the shortest paths and the cost of each one
    """
    try:
        short_path = [nx.shortest_path(graph, source, target,
                                       weight=lambda u, v, d: calculate_weight(graph, u, v, payment_amount))]
        short_path_costs = [path_cost(graph, short_path[0], payment_amount)]

        sub_short_path = queue.PriorityQueue()

        for k in range(1, num_k):
            try:
                for i in range(len(short_path[k - 1]) - 1):
                    spur_node = short_path[k - 1][i]
                    root_path = short_path[k - 1][:i]

                    removed_edges = []
                    for path in short_path:
                        if len(path) - 1 > i and root_path == path[:i]:
                            edge = (path[i], path[i + i])
                            if not graph.has_edge(*edge):
                                continue
                            removed_edges.append((edge, graph.get_edge_data(*edge)))
                            graph.remove_edge(*edge)
                    try:
                        spur_path = nx.shortest_path(graph, spur_node, target)
                        total_path = root_path + spur_path
                        total_path_cost = path_cost(graph, total_path)
                        sub_short_path.put((total_path_cost, total_path))
                    except nx.NetworkXNoPath:
                        pass
                    for removedEdge in removed_edges:
                        graph.add_edge(*removedEdge[0], **removedEdge[1])
                while True:
                    try:
                        cost_, path_ = sub_short_path.get(False)
                        if path_ not in short_path:
                            short_path.append(path_)
                            short_path_costs.append(cost_)
                            break
                    except queue.Empty:
                        break
            except IndexError:
                pass
        return short_path, short_path_costs
    except nx.NodeNotFound as e:
        print('%s%s*** ERROR ON SHORTEST PATH YEN: %s' % (utils.spaces, utils.spaces, e))
        return None


def query_route_yen(graph1: nx, graph2: nx, node_origin: str, node_destiny: str, payment_amount: int, num_k: int,
                    is_manual_test: bool = False) -> route_pay.Payment:
    """
    Creates the structure that contains the payment with relevant data such as nodes origin and destiny, route with the
    hops and its data and totals (amt, fee, time lock and success probability)

    :param num_k: number of sub paths to get with the algorithm
    :param graph1: contains detailed data about the network
    :param graph2: contains specific data about the network
    :param node_origin: alias of the node origin
    :param node_destiny: alias of the node destiny
    :param payment_amount: amount to be paid to node destiny
    :param is_manual_test: indicates if the test is manual, thus, the node_destiny and node_origin contain their aliases
    :return: Payment that contains data about both nodes and route, totals (amt, fee, time lock and success
    probability)
    """
    routes = {}
    if is_manual_test:
        pubkey_origin = utils.get_pubkey_alias(node_origin, graph1)
        pubkey_destiny = utils.get_pubkey_alias(node_destiny, graph1)
    else:
        pubkey_origin = node_origin
        pubkey_destiny = node_destiny

    hop_temp = {'chan_id': '', 'chan_capacity': '', 'amt_to_forward': 0.0, 'fee': 0.0, 'expiry': 0,
                'amt_to_forward_msat': 0.0,
                'fee_msat': 0.0, 'pub_key': '', 'tlv_payload': True}

    if pubkey_origin is not None and pubkey_destiny is not None:
        paths = spy(graph2.copy(), pubkey_origin, pubkey_destiny, num_k, payment_amount)
        if paths is not None:
            nodes = paths[0][0]
            channels = paths[1][0]
            routes['routes'] = [{'total_time_lock': 0, 'total_fees': 0, 'total_amt': 0, 'hops': [], 'total_fees_msat': 0,
                                 'total_amt_msat': 0}]
            routes['success_prob'] = 1 / len(nodes)

            amt_fee_msat = 0
            ln = 0 if len(channels[1]) == 1 else len(channels[1]) - 1 if len(channels[1]) == 2 else len(channels[1]) - 2
            for c in channels[1][0:ln]:
                amt_fee_msat += c[1] if c[1] >= 1000 else 1000

            val_hop = int((payment_amount * 1000 + amt_fee_msat) / 1000)

            routes['routes'][0]['total_fees_msat'] = amt_fee_msat
            routes['routes'][0]['total_amt_msat'] = val_hop * 1000
            routes['routes'][0]['total_fees'] = int(amt_fee_msat / 1000)
            routes['routes'][0]['total_amt'] = val_hop

            for i, val in enumerate(nodes):
                if i < len(nodes) - 1:
                    channel = graph2[val][nodes[i + 1]][channels[1][i][0]]
                    hop = hop_temp.copy()
                    routes['routes'][0]['total_time_lock'] += channel['policy_source']['time_lock_delta']

                    hop['chan_id'] = channels[1][i][0].split('-')[0]
                    hop['chan_capacity'] = channel['capacity']
                    if i != 0 and i != len(nodes) - 2:
                        # hop['fee'] = int(1 if int(channel['policy_source']['fee_base_msat']) < 1000 else int(
                        #     channel['policy_source']['fee_base_msat']) / 1000)
                        # hop['fee_msat'] = hop['fee'] * 1000
                        fee_msat = channels[1][i][1]
                        hop['fee_msat'] = fee_msat if fee_msat >= 1000 else 1000
                        hop['fee'] = hop['fee_msat'] / 1000
                        val_hop -= hop['fee']
                    if i == 0:
                        no_fee = 0
                        if len(channels[1]) <= 2:
                            no_fee = 0 if len(channels[1]) < 2 else (val_hop - payment_amount) * 1000 if channels[1][0][1] \
                                                                                                         >= 1000 else 1000
                        hop['fee_msat'] = no_fee if len(channels[1]) <= 2 else 0
                        hop['amt_to_forward_msat'] = payment_amount * 1000 if len(channels[1]) <= 2 else \
                            val_hop * 1000 - hop['fee_msat']
                        hop['amt_to_forward'] = int(hop['amt_to_forward_msat'] / 1000)
                        hop['fee'] = int(hop['fee_msat'] / 1000)
                    hop['amt_to_forward'] = hop['amt_to_forward'] if i == 0 else payment_amount if len(channels[1]) == 2 \
                        else val_hop
                    hop['expiry'] = channel['policy_source']['time_lock_delta']
                    hop['amt_to_forward_msat'] = hop['amt_to_forward'] * 1000
                    hop['pub_key'] = nodes[i + 1]

                    routes['routes'][0]['hops'].append(hop)

            node_dict, edge_dict = populate_graphs(graph1, graph2)

            return route_pay.create_route(routes, pubkey_origin, pubkey_destiny, payment_amount, edge_dict, node_dict)
        else:
            return route_pay.Payment(pubkey_origin, pubkey_destiny, payment_amount, None, time.time_ns(),
                                     error="Nodes not found - YEN - either node is not in graph")
    else:
        return route_pay.Payment(pubkey_origin, pubkey_destiny, payment_amount, None, time.time_ns(),
                                 error="Nodes not found - YEN - either node is None")


def populate_graphs(g1: nx, g2: nx) -> Tuple[dict, dict]:
    """
    Set the value of dictionaries for the node and edge that will be used to print data about the hops

    :param g1: contains detailed data about the network
    :param g2: contains specific data about the network
    :return: dictionaries of nodes and edges
    """
    dict_edge = {}
    dict_node = dict(g1.nodes(data=True))

    for e in g1.edges(data=True, keys=True):
        dict_edge[e[2]] = e

    for e in g2.edges(data=True, keys=True):
        dict_edge[e[2]] = e

    return dict_node, dict_edge
