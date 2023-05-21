import re
import os
import sys
import json
import random
import hashlib
import ipaddress
import jsonpickle
import numpy as np
import networkx as nx
from datetime import datetime
from typing import Optional, Any, Tuple, Set
from ln.connector import eclair_client as eclair, lnd_client as lnd, clightning_client as clight

spaces = "".rjust(5)


def input_value(default: str, message: str, is_path: bool, is_value: bool):
    """
    Validates input data used to perform query routes. The data to control is of type integer and directory to load
    the json files


    :param default: default value to return in case of a None or empty value
    :param message: message to be printed as informative
    :param is_path: indicates if the value is a path/directory from which the simulation will load the json files
    :param is_value: indicates if the value is a number such as the amount in satoshis
    :return: the validated input data
    """
    data = None
    if is_value:
        while True:
            try:
                data = input(message)
                if data != '':
                    data = int(data)
            except ValueError:
                print("Expected an int value!!!!")
                continue
            else:
                break
    else:
        data = input(message)

    if is_path:
        has_error = False
        while True:
            if has_error:
                data = input(message)
            try:
                with open(data):  # OSError if file does not exist or is invalid
                    break
            except OSError as err:
                if len(data) > 0:
                    print("OS error: {0}".format(err))
                    has_error = True
                    continue
                else:
                    break
            except ValueError:
                if data == '':
                    print("Unexpected error:", sys.exc_info()[0])
                    has_error = True
                    continue
                else:
                    break

    return default if is_value and data == 0 or data == '' else data


def check_preimage_hash(preimage, hash_value) -> bool:
    """
    Validates that the preimage of the hash corresponds to the one provided on the hop to perform the payment

    :param preimage:generated random number
    :param hash_value:hash value of the preimage provided by the hop
    :return: true or false based on the operation
    """
    if hashlib.sha256(str(preimage).encode()).hexdigest() == hash_value:
        return True
    return False


def request_payment_hash_destiny(pub_key_destiny: str):
    """
    Generates a preimage and its hash value based on the pub_key of the destiny

    :param pub_key_destiny: pub_key of the node destiny
    :return: preimage and hash value
    """
    num = int(re.sub('[^0-9_]', '', str(pub_key_destiny)))
    preimage = np.random.uniform(0, num)
    return hashlib.sha256(str(preimage).encode()).hexdigest(), preimage


def validate_ip(host: str, ip: str) -> str:
    """
    Validates the ip/host of the node to connect

    :param host: host of the node
    :param ip: ip of the node
    :return: ip validated
    """
    try:
        host = host if ip == '' else ip
        ip = ipaddress.ip_address(host)
        print('%s is a correct IP%s address.' % (ip, ip.version))
    except ValueError:
        print('address/netmask is invalid: %s. Default ip  used: %s' % (ip, host))
        ip = host

    return ip


def load_file(location: str, file_name: str, is_snapshot: bool):
    """
    Lets to load a file by its name from a location in the project

    :param location: directory in which the file is located
    :param file_name: name of the file
    :param is_snapshot: indicates that the file is a snapshot and set the nodes and edges
    :return: data stored on the file
    """
    with open(os.path.join(location, file_name), encoding="utf8") as f:
        if is_snapshot:
            data = set_data_nodes_edges(json.load(f), True)
        else:
            data = json.load(f)

    return data


def save_file(location: str, file_name: str, data, has_datetime: bool = True):
    """
    Let store data on a file

    :param location: directory in which the file is located
    :param file_name: name of the file
    :param data: data to be stored in format dictionary
    :param has_datetime: flag that indicates that the name of the file contains the datetime in epoch style
    :return:
    """
    if has_datetime:
        time_str = datetime.now().strftime("%Y%m%dT%H%M%S")
        temp = file_name.split('.')
        file_name = temp[0] + '_' + time_str + '.' + temp[1]

    with open(os.path.join(location, file_name), 'w') as fp:
        data_json = json.loads(data)
        json.dump(data_json, fp, indent=4)
        fp.close()

    # temp_file = open(os.path.join(location, file_name), 'w')
    # with temp_file as fp:
    #     json.dump(data, fp)
    # temp_file.close()
    #
    # temp_file = open(os.path.join(location, file_name), 'r')
    # for line in temp_file:
    #     # read replace the string and store on a variable
    #     data_json = line.replace('\\', '').replace('"{', '{').replace('}"', '}')
    # data_json = json.loads(data_json)
    #
    # time_str = datetime.now().strftime("%Y%m%dT%H%M%S")
    # temp = file_name.split('.')
    # file_name = temp[0] + '_' + time_str + '.' + temp[1]
    # final_file = open(os.path.join(location, file_name), 'w')
    # with final_file as fp:
    #     json.dump(data_json, fp, indent=4)
    # temp_file.close()
    # final_file.close()


def create_test_file(g1: nx, connectors: dict, num_routes: int, max_amount: int, location: str, file_name: str,
                     is_snapshot: bool):
    """
    Creates a test file with random nodes (origin and destiny) and payment amount. The result test.json file contains
    data from the connector (lnd, eclair and c-lightning) from parameters.json

    :param g1: data of the network with nodes and channels
    :param connectors: parameters of connection of the three implementations (lnd, eclair and c-lightning)
    :param num_routes: number of routes to include in the key routes of the file
    :param max_amount: max amount that will be forwarded in a payment
    :param location: path that indicates the location where the file will be stored
    :param file_name: name of the file
    :param is_snapshot: the value of pub key is empty for the key eclair in the case of a snapshot

    :return: None
    """
    exclude = {"macaroon_dir", "cert_dir"}
    nodes = list(g1.nodes(data=True))
    num_nodes = len(nodes)
    result = {}
    for key, value in connectors.items():
        routes = []
        result[key] = {}
        result[key]["flag"] = True if ('alias' in value and len(value['alias']) > 0) or key == 'eclair' else False
        result[key]["node"] = exclude_keys_dictionary(value, exclude)
        pubkey_eclair = '' if key != 'eclair' else '' if is_snapshot else \
            eclair.get_info(value['host'], value['port'], value["user"], value['passwd'])['nodeId']
        for i in range(num_routes):
            rand = get_randoms(num_nodes)
            route = {"origin": pubkey_eclair if len(pubkey_eclair) > 0 else nodes[rand[0]][0],
                     "destiny": nodes[rand[1]][0], "amount": random.randrange(1, max_amount)}
            routes.append(route)
        result[key]["routes"] = routes

    save_file(location, file_name, jsonpickle.encode(result), has_datetime=False)


def get_randoms(max_value: int) -> Tuple[int, int]:
    """
    Returns a couple of random numbers that are used to select different origin and destiny pub keys of the nodes with
    the aim of creating a test.json file

    :param max_value: max value to get a random number
    :return: a couple of random numbers
    """
    rand1 = rand2 = 0
    while rand1 == rand2:
        rand1 = random.randrange(0, max_value)
        rand2 = random.randrange(0, max_value)

    return rand1, rand2


def exclude_keys_dictionary(dictionary: dict, keys: Set[str]) -> dict:
    """
    Exclude keys from a dictionary

    :param dictionary: dictionary with parameters that include values to exclude
    :param keys: keys to be excluded

    :return: dictionary without excluded keys
    """
    return {x: dictionary[x] for x in dictionary if x not in keys}


def set_data_nodes_edges(data: nx, is_message: bool = True, parameters=None) -> nx:
    """
    Sets the structure of the snapshot divided on nodes and edges. Moreover, it set the value of those parameters that
    are either None or empty from the edges and nodes

    :param parameters:
    :param data: data gathered from the json file
    :param is_message: meessage to print
    :return: data validated and set
    """
    index = 0
    dict_pub_key = {}
    nodes = {}
    if parameters is not None:
        clight_params = parameters["connector"]["c-lightning"]
        nodes_clightning = clight.get_nodes(parameters["polar_path"] + 'c-lightning/' + clight_params["alias"] +
                                            clight_params["macaroon_dir"])
        for dic in nodes_clightning['nodes']:
            if 'alias' in dic:
                nodes[dic["nodeid"]] = dic["alias"]
    for node in data['nodes']:
        index += 1
        if 'last_update' not in node: node['last_update'] = 0
        if 'alias' not in node:
            if nodes and node['pub_key'] in nodes:
                node['alias'] = nodes[node['pub_key']]
            else:
                node['alias'] = node['pub_key'][:4] + '..' + node['pub_key'][-4:]
        if 'addresses' not in node: node['addresses'] = []
        if 'color' not in node: node['color'] = '#000000'
        if 'features' not in node: node['features'] = {}
        dict_pub_key[node['pub_key']] = node['alias']
        if is_message:
            print('{}INFO: Node #{} - alias: {} - pub_key: {}'.format(spaces, index, node['alias'],
                                                                      node['pub_key']))
    if is_message:
        input("Press ENTER to continue.....")
    index = 0
    if 'edges' in data:
        for edge in data['edges']:
            index += 1
            if 'last_update' not in edge: edge['last_update'] = 0
            if 'node1_policy' in edge and edge['node1_policy'] is not None:
                policy1 = edge['node1_policy']
                if 'disabled' not in policy1: policy1['disabled'] = True
            if 'node2_policy' in edge and edge['node2_policy'] is not None:
                policy2 = edge['node2_policy']
                if 'disabled' not in policy2: policy2['disabled'] = True

            if is_message:
                print('{}INFO: Channel #{}({}) - from {} ({}) to {} ({})'.format(spaces, index,
                                                                                 edge['channel_id'],
                                                                                 dict_pub_key[edge['node1_pub']],
                                                                                 edge['node1_pub'],
                                                                                 dict_pub_key[edge['node2_pub']],
                                                                                 edge['node2_pub']))
    return data


def populate_graphs(data: nx):
    """
    NODES: Read the JSON file and import all node data to the g1 and g2 graph.
    EDGES: Read the JSON file and import all edge data to the g1 and g2 graph.

    :param data: data load from json file
    :return: g1, g2, nodeDict, edgeDict
    """
    g1 = nx.MultiGraph()
    g2 = nx.MultiDiGraph()
    # NODES: Read the JSON file and import all node data to the g1 graph.
    for n in data['nodes']:
        g1.add_node(n['pub_key'], last_update=n['last_update'],
                    alias=n['alias'], addresses=n['addresses'], color=n['color'],
                    features=n['features'])
    node_dict = dict(g1.nodes(data=True))

    # EDGES: Read the JSON file and import all edge data to the g1 graph.
    for e in data['edges']:
        g1.add_edge(e['node1_pub'], e['node2_pub'], key=e['channel_id'],
                    chan_point=e['chan_point'], last_update=e['last_update'],
                    node1_pub=e['node1_pub'], node2_pub=e['node2_pub'],
                    capacity=int(e['capacity']),
                    policy_source={'node1_policy': {}} if 'node1_policy' not in e else e["node1_policy"],
                    policy_dest={'node2_policy': {}} if 'node2_policy' not in e else e["node2_policy"])
    edge_dict = {}
    for e in g1.edges(data=True, keys=True):
        edge_dict[e[2]] = e

    # NODES: Read the JSON file and import all node data to the g2 graph.
    for n in data['nodes']:
        g2.add_node(n['pub_key'])

    # EDGES: Read the JSON file and import all edge data to the g2 graph.
    for e in data['edges']:
        if 'node1_policy' in e and 'node2_policy' in e:
            capacity = int(e['capacity'])
            k = "{}-{}".format(e['channel_id'], e['node1_pub'])

            g2.add_edge(e['node1_pub'], e['node2_pub'], key=k,
                        channel_id=e['channel_id'], last_update=e['last_update'],
                        policy_source=e["node1_policy"], policy_dest=e["node2_policy"],
                        capacity=capacity)  # TODO:(now we can use mappings between graphs, but this may be faster)

            k = "{}-{}".format(e['channel_id'], e['node2_pub'])

            g2.add_edge(e['node2_pub'], e['node1_pub'], key=k,
                        channel_id=e['channel_id'], last_update=e['last_update'],
                        policy_source=e["node2_policy"], policy_dest=e["node1_policy"],
                        capacity=capacity)  # TODO:(now we can use mappings between graphs, but this may be faster)
    for e in g2.edges(data=True, keys=True):
        edge_dict[e[2]] = e

    return g1, g2, node_dict, edge_dict


def get_parameters_connection(parameters: dict, g1: nx) -> dict:
    """
    Creates a dictionary with the parameters of the connectors  that will be used to connect a specific node to
    send a payment

    :param parameters: parameters with data to create a connection to a node
    :param g1: data of the network with nodes and channels
    :return: dictionary with the parameters to connect to a node
    """
    length = len(g1.nodes(data=True)._nodes)
    connectors = {"lnd": {}, "c-lightning": {}, "eclair": {}}

    for n in g1.nodes(data=True):
        macaroon = replace_path_os(parameters["polar_path"] + 'lnd/' + n[1]['alias'] +
                                   parameters["connector"]["lnd"]["macaroon_dir"])
        cert = replace_path_os(parameters["polar_path"] + 'lnd/' + n[1]['alias'] +
                               parameters["connector"]["lnd"]["cert_dir"])
        if validate_dir(macaroon) and validate_dir(cert):
            result = check_params_connector("lnd", length, parameters["connector"]["lnd"]["host"],
                                            macaroon=macaroon, cert=cert)

            connectors["lnd"][n[0]] = {"macaroon_dir": macaroon, "cert_dir": cert,
                                       "host": parameters["connector"]["lnd"]["host"],
                                       "port": result[0], "info": result[1]}
        else:
            macaroon = replace_path_os(parameters["polar_path"] + 'c-lightning/'
                                       + parameters["connector"]["c-lightning"]["alias"]
                                       + parameters["connector"]["c-lightning"]["macaroon_dir"])
            result = check_params_connector("c-lightning", length, "", macaroon, pub_key=n[0],
                                            split=parameters["connector"]["c-lightning"]["alias"])
            if result is not None:
                connectors["c-lightning"][n[0]] = {"macaroon_dir": result[0], "info": result[1]}
            else:
                result = check_params_connector("eclair", length, parameters["connector"]["eclair"]["host"],
                                                user=parameters["connector"]["eclair"]["user"],
                                                passwd=parameters["connector"]["eclair"]["passwd"],
                                                pub_key=n[0])

                connectors["eclair"][n[0]] = {"host": parameters["connector"]["lnd"]["host"],
                                              "port": result[0],
                                              "user": parameters["connector"]["eclair"]["user"],
                                              "passwd": parameters["connector"]["eclair"]["passwd"],
                                              "info": result[1]}

    return connectors


def replace_path_os(path: str) -> str:
    """
    Replaces the path according to the operating system

    :param path: path to replace according to OS
    :return: path replaced
    """
    if os.sys.platform == 'win32':
        return path.replace('/', '\\')

    return path


def check_params_connector(implementation: str, length: int, host: str, macaroon: str = None, cert: str = None,
                           user: str = None, passwd: str = None, pub_key: str = None, split: str = None) -> Tuple[int, Optional[Any]]:
    """
    Checks according to the implementation the missing parameters such as port, required to connect to a node

    :param implementation: type of implementation (lnd, eclair and c-lightning)
    :param length: number of nodes in the network
    :param host: host of the nodes (by default localhost)
    :param macaroon: path to the macaroon file
    :param cert: path to the cert file
    :param user: user to connect to a node
    :param passwd: password to connect to a node
    :param pub_key: pub_key of the node

    :return: port and info of the node
    """
    result = None
    port = 0
    if implementation == "lnd":
        for i in range(10000, 10000 + length + 2, 1):
            result = lnd.get_info(host, i, macaroon, cert)
            port = i
            if result is not None:
                break
    else:
        if implementation == "c-lightning":
            nodes = clight.get_nodes(macaroon)
            paths = macaroon.split(split, 1)
            directories = os.listdir(paths[0])
            for node in nodes["nodes"]:
                for dir in directories:
                    if pub_key == node["nodeid"] and dir == node["alias"]:
                        macaroon = paths[0] + node["alias"] + "/" + paths[1]
                        return macaroon, clight.get_info(macaroon)
            return None
        else:
            for i in range(8280, 8280 + length + 2, 1):
                result = eclair.get_info(host, i, user, passwd)
                port = i
                if result is not None and result['nodeId'] == pub_key:
                    break

    return port, result


def validate_dir(path: str) -> bool:
    """
    Validates whether a path exist or not

    :param path: path to validate
    :return: bool
    """
    try:
        with open(path):  # OSError if file does not exist or is invalid
            return True
    except OSError as err:
        if os.path.exists(path):
            return True
        else:
            return False


def print_info_hop(channel_id: str, pub_key: str, index: int, edge_dict: dict = None, node_dict: dict = None,
                   origin: str = None, destiny: str = None):
    """
    Prints info about the hop

    :param channel_id: The channel id of the hop
    :param pub_key: the pub key of the node in the channel
    :param index:  the index of the hop
    :param edge_dict: dictionary with all the edges
    :param node_dict: dictionary with all the nodes
    :param origin: node origin
    :param destiny: node destiny
    :return:  None
    """
    if origin is None and destiny is None:
        label_edge = "{}-{}".format(channel_id, pub_key)
        if label_edge in edge_dict:
            origin = node_dict[edge_dict[label_edge][1]]['alias']
            destiny = node_dict[edge_dict[label_edge][0]]['alias']
    print("{}INFO: HOP {} channel_id ({}) from {} to {}".format(spaces, index, channel_id, origin, destiny))


def print_info_total_route(total_amt: float, total_fees: float, total_time_lock: int):
    """
    Prints info about the total values on the payment

    :param total_amt: total amount in satoshis
    :param total_fees: total fees
    :param total_time_lock: total time lock
    :return: None
    """
    print('%s%sTOTAL AMT: %s' % (spaces, spaces, total_amt))
    print('%s%sTOTAL FEES: %s' % (spaces, spaces, total_fees))
    print('%s%sTOTAL TIME LOCK: %s' % (spaces, spaces, total_time_lock))
    # print(datetime.now().strftime("%m/%d/%Y, %H:%M:%S"))


def lnd_to_cl_scid(channel_id: int) -> Tuple[int, int, int]:
    """
    Transforms the value of channel_id to short_channel_id

    :param channel_id: channel_id
    :return: short_channel_id
    """
    block = channel_id >> 40
    tx = channel_id >> 16 & 0xFFFFFF
    output = channel_id & 0xFFFF
    return block, tx, output


def cl_to_lnd_scid(short_channel_id: str):
    """
    Transform the value of short_channel_id to channel_id

    :param short_channel_id:
    :return: channel_id
    """
    channel_id = [int(i) for i in short_channel_id.split('x')]
    return (channel_id[0] << 40) | (channel_id[1] << 16) | channel_id[2]


def get_pubkey_alias(alias: str, graph: nx) -> str:
    """
    Returns the pub_key from an alias

    :param alias: Node alias
    :param graph: multigraph with the whole data about the network
    :return: pubkey
    """
    pub_key = None
    for n in graph.nodes(data=True):
        if alias == n[1]['alias']:
            pub_key = n[0]
            if pub_key is not None:
                break

    return pub_key


def get_alias_pubkey(pubkey: str, graph: nx) -> str:
    """
    Returns the pub_key from an alias

    :param pubkey: Node pubkey
    :param graph: multigraph with the whole data about the network
    :return: alias
    """
    alias = None
    for n in graph.nodes(data=True):
        if pubkey == n[0]:
            alias = n[1]['alias']
            if alias is not None:
                break

    return alias


class Counter(object):
    def __init__(self, v=0):
        self.set(v)

    def preinc(self):
        self.v += 1
        return self.v

    def predec(self):
        self.v -= 1
        return self.v

    def postinc(self):
        self.v += 1
        return self.v - 1

    def postdec(self):
        self.v -= 1
        return self.v + 1

    def __add__(self, addend):
        return self.v + addend

    def __sub__(self, subtrahend):
        return self.v - subtrahend

    def __mul__(self, multiplier):
        return self.v * multiplier

    def __div__(self, divisor):
        return self.v / divisor

    def __getitem__(self):
        return self.v

    def __str__(self):
        return str(self.v)

    def set(self, v):
        if type(v) != int:
            v = 0
        self.v = v
