import os
import grpc
import time
import random
import codecs
import jsonpickle
import numpy as np
import networkx as nx
import ln.lightning_pb2 as ln
import ln.utils as utils
from datetime import datetime
import ln.shortest_path_yen as spy
import ln.route_payment as route_pay
from ln.connector import lnd_client as lnd, clightning_client as clight, eclair_client as eclair

# Constants for describing lightning clients implementations
IMPL_C_LIGHTNING = "c-lightning"
IMPL_LND = "lnd"
IMPL_LND_0_6 = "lnd_0.6"
IMPL_ECLAIR = "eclair"
IMPL_INCONCLUSIVE = "inconclusive"
IMPL_COLLIDING = "colliding"
IMPL_NODE = "IMPLEMENTATION/NODE_NAME"

IMPLEMENTATION_PARAMS = {
    IMPL_C_LIGHTNING: {'time_lock_delta': 14, 'fee_base_msat': '1000', 'fee_rate_milli_msat': '10'},
    IMPL_LND: {'time_lock_delta': 144, 'fee_base_msat': '1000', 'fee_rate_milli_msat': '1'},
    IMPL_LND_0_6: {'time_lock_delta': 40, 'fee_base_msat': '1000', 'fee_rate_milli_msat': '1'},
    IMPL_ECLAIR: {'time_lock_delta': 144, 'fee_base_msat': '1000', 'fee_rate_milli_msat': '100'}
}


def get_key_hops_block_make_payment(payment: route_pay.Payment, is_block: bool):
    """
    Delivers the pub keys of the hops for either case blocking payment or payment

    :type payment: object
    :param payment: structure for the payment with the hops
    :param is_block: specify the payment, or the blocking payment
    :return: pub keys and hops on direct or reverse order for the blocking payment or payment respectively
    """
    key_hops = {}
    list_hops = payment.routes[0].hops if is_block else reversed(payment.routes[0].hops)

    for h in list_hops:
        k = "{}-{}".format(h.channel_id, h.pub_key) if is_block else h.channel_id
        key_hops[k] = h if is_block else (h.pub_key, h)

    return key_hops


class LNPayment:
    """
        Structure used as main body of the simulation, it handles either the initial configuration to connect to a node
        or loading of a snapshot
    """

    def __init__(self, json_filename_temp: str, implementation: dict = None, balance: dict = None, htlc: dict = None):
        folder = '\\data' if os.sys.platform == 'win32' else '/data'
        self.location = os.path.realpath(
            os.path.join(os.getcwd(), os.path.dirname(__file__))) + folder

        self.name = json_filename_temp
        self.parameters = utils.load_file(self.location, "parameters.json", False)
        self.tests = utils.load_file(self.location, self.parameters["test_file"], False)
        self.macaroon_dir = self.cert_dir = self.host = None
        self.port = 0
        self.macaroon = self.cert = self.secure_channel = None
        self.payments = None
        self.implementation = implementation
        self.balance = balance
        self.htlc = htlc

        """
        Load data from json_filename and fill in all the data we know for the two graphs.
        Data for all fields except those starting with * can be found in the json file.
        g1:
            nodes
                pub_key (id)
                last_update
                alias
                addresses
                color
                features
                * implementation
            edges
                channel_id (id)
                chan_point
                capacity
                last_update
                node1_pub
                node2_pub
                node1_policy
                node2_policy

        g2:
            nodes
                pub_key (id)

            edges
                channel_id | node1_pub (id) 
                    o bé 
                channel_id | node2_pub (id) 
                * balance (float)
                * pending_htlc (dict)
        """

        # channel = lnd.get_channel_id(self.macaroon, self.channel, 261683767476225)
        # print(channel.__dict__)
        # The user has the option to get data from either the network or a snapshot
        self.is_snapshot = True if input('Load from Snapshot? (y/n):') == 'y' else False
        data = None
        while True:
            try:
                # Function to set the initial params to get data from the network: mainnet, testnet or regtest
                self.__set_param_node(is_snapshot=self.is_snapshot)

                if self.is_snapshot:
                    # Function to load data from a json file and set its initial values
                    data = utils.load_file(self.location, self.name, True)
                else:
                    # Function to load g1 and g2 based on the network connected
                    data = lnd.describe_graph(self.macaroon, self.secure_channel, True, self.parameters)
            except grpc.RpcError as e:
                print("{} NODE CONNECTION ERROR:{}-{}-{}".format(utils.spaces, e.args[0].code.value[0],
                                                                 e.args[0].code.value[1].upper(),
                                                                 e.args[0].details.upper()))
                continue
            except FileNotFoundError as f:
                print("{} NODE CONNECTION ERROR:{}-{}".format(utils.spaces, f.strerror, f.filename))
                continue
            else:
                break

        # Gets the aim values for the simulations, specifically the dictionaries for the node and edge
        if 'nodes' in data and 'edges' in data:
            self.g1, self.g2, self.nodeDict, self.edgeDict = utils.populate_graphs(data)

            self.__infer_implementation(self.implementation)
            self.__assign_rand_balances(self.balance)
            self.__assign_rand_htlc(self.htlc)

            self.__start_payment()

            self.__check_correctness()

        if self.payments is not None:
            utils.save_file(self.location, self.parameters["results_file"], jsonpickle.encode(self.payments))

    @staticmethod
    def enum_value_to_name(val, enum_descriptor: route_pay.EnumDescriptor):
        """
        Gets the name of a descriptor based on its value

        :param val: value stored on the structure of Payment
        :param enum_descriptor: enumerator that adds functionality to payment description
        :return: Name of the descriptor
            Status: HTLC & Payment
            Failure: Code & Reason
        """

        # htlc = HTLC(enum_value_to_name(ln.PaymentFailureReason.FAILURE_REASON_NO_ROUTE))
        def descriptor(d):
            switcher = {
                0: ln.HTLCAttempt.HTLCStatus.DESCRIPTOR,
                1: ln.Payment.PaymentStatus.DESCRIPTOR,
                2: ln.Failure.FailureCode.DESCRIPTOR,
                3: ln.PaymentFailureReason.DESCRIPTOR
            }
            return switcher.get(d, "Invalid descriptor")

        desc = descriptor(enum_descriptor)
        print(desc.name)
        for (k, v) in desc.values_by_name.items():
            if v.number == val:
                return k
        return None

    def __set_param_node(self, parameters_test=None, is_snapshot=False):
        """
        Set configuration parameters to connect to a specific node to get query routes and perform payments.
        The variables macaroon and cert depend on the polar installation on the local machine

        :return: None
            Examples:
                * Default values
                macaroon:   '/home/deic/.polar/networks/1/volumes/lnd/alice/data/chain/bitcoin/regtest/admin.macaroon'
                cert:       '/home/deic/.polar/networks/1/volumes/lnd/alice/tls.cert'
                node:       alice
                host:       localhost / 127.0.0.1
                port:       10001
                channel:    127.0.0.1:10001, tls_certificate
        """
        if parameters_test is None:
            self.macaroon_dir = (self.parameters["polar_path"] + IMPL_NODE).replace('IMPLEMENTATION', 'lnd') \
                                + self.parameters["connector"]["lnd"]["macaroon_dir"]
            self.cert_dir = (self.parameters["polar_path"] + IMPL_NODE).replace('IMPLEMENTATION', 'lnd') \
                            + self.parameters["connector"]["lnd"]["cert_dir"]

            self.node = '' if is_snapshot else utils.input_value('', 'Input the name of node to connect '
                                                                     '(Default none):\n', False, False)
            if len(self.node) > 0:
                self.macaroon_dir = self.macaroon_dir.replace('NODE_NAME', self.node)
                self.cert_dir = self.cert_dir.replace('NODE_NAME', self.node)
            else:
                self.macaroon_dir = self.macaroon_dir.replace('NODE_NAME', self.parameters["connector"]["lnd"]["alias"])
                self.cert_dir = self.cert_dir.replace('NODE_NAME', self.parameters["connector"]["lnd"]["alias"])
                if not is_snapshot:
                    self.macaroon_dir = utils.input_value(self.macaroon_dir, 'Input macaroon dir (Default Alice\'s dir)'
                                                                             ':\n', True, False)
                    self.cert_dir = utils.input_value(self.cert_dir, 'Input cert dir (Default Alice\'s dir):\n', True,
                                                      False)

            self.host = self.parameters["connector"]["lnd"]["host"]
            self.port = self.parameters["connector"]["lnd"]["port"]
            if not is_snapshot:
                self.host = utils.validate_ip(self.host, utils.input_value(self.host, 'Input IP address of node '
                                                                                      '(Default: localhost)\n', False,
                                                                           False))
                self.port = utils.input_value(self.port, 'Input listen port of node (Default: 10001)\n', False, True)
        else:
            path = (self.parameters["polar_path"] + IMPL_NODE).replace('IMPLEMENTATION',
                                                                       parameters_test["implementation"]).replace(
                'NODE_NAME', parameters_test["alias"])
            self.macaroon_dir = path + self.parameters["connector"]["lnd"]["macaroon_dir"]
            self.cert_dir = path + self.parameters["connector"]["lnd"]["cert_dir"]
            self.host = parameters_test["host"]
            self.port = parameters_test["port"]

        if os.sys.platform == 'win32':
            self.macaroon_dir = self.macaroon_dir.replace('/', '\\')
            self.cert_dir = self.cert_dir.replace('/', '\\')

        if not is_snapshot:
            # self.macaroon = codecs.encode(open(self.macaroon_dir, 'rb').read(), 'hex')
            # os.environ['GRPC_SSL_CIPHER_SUITES'] = 'HIGH+ECDSA'
            # self.cert = open(self.cert_dir, 'rb').read()
            # ssl_creds = grpc.ssl_channel_credentials(self.cert)
            # self.secure_channel = grpc.secure_channel(str(self.host) + ':' + str(self.port), ssl_creds)
            self.macaroon = codecs.encode(open(self.macaroon_dir, 'rb').read(), 'hex')

            def metadata_callback(context, callback):
                callback([('macaroon', self.macaroon)], None)

            auth_creds = grpc.metadata_call_credentials(metadata_callback)
            # create SSL credentials
            os.environ['GRPC_SSL_CIPHER_SUITES'] = 'HIGH+ECDSA'
            self.cert = open(self.cert_dir, 'rb').read()
            ssl_creds = grpc.ssl_channel_credentials(self.cert)
            # combine macaroon and SSL credentials
            combined_creds = grpc.composite_channel_credentials(ssl_creds, auth_creds)
            # make the request
            self.secure_channel = grpc.secure_channel(str(self.host) + ':' + str(self.port), combined_creds)

    def __infer_implementation(self, config: dict):
        """
        Decide how we want to do this.

        config is a dict with parameters for tuning the implementation inference
        procedure
        :param config:
        """

    @staticmethod
    def __check_balance_config(config):
        """
        Checks the distribution used to assign the balance

        :param config:
        :return:
        """
        assert "name" in config, "No distribution specified"
        assert config["name"] in ["const", "unif", "normal", "exp", "beta"], "Unrecognized distribution name"

    def __assign_rand_balances(self, config: dict):
        """
        Randomly assigns balances to the channels following the specified distribution.
        Balances are not assigned if config is None.

        :param config: dict, distribution name (key 'name'), and params (keys depend on distribution name).
            Recognized keys are:

            name:   "const", "unif", "normal", "exp", "beta"
            mu:     float (only for name = normal)
            sigma:  float (only for name = normal)
            l:      float (only for name = exp)
            alpha:  float (only for name = beta)
            beta:   float (only for name = beta)

            Examples:
                config = {"name": "const"}
                config = {"name": "unif"}
                config = {"name": "normal", "mu": 0.5, "sigma": 0.2}
                config = {"name": "exp", "l": 1}
                config = {"name": "beta", "alpha": 0.25, "beta": 0.25}
        """

        rand_func = None
        if config is None:
            # Do not assign balances if config is None
            print("INFO: balances not assigned")
            return

        self.__check_balance_config(config)
        print("INFO: balances assigned using a {} distribution ({})".format(config["name"], config))

        if config["name"] == "const":
            rand_func = lambda exp: int(exp[2]["capacity"] / 2)
        elif config["name"] == "unif":
            rand_func = lambda exp: int(np.random.uniform(0, exp[2]["capacity"]))
        elif config["name"] == "normal":
            mu, sigma = config["mu"], config["sigma"]

            def rand_func(exp):
                r = np.random.normal(mu, sigma)
                while r < 0 or r > 1:
                    r = np.random.normal(mu, sigma)
                return exp[2]["capacity"] - int(exp[2]["capacity"] * r)
        elif config["name"] == "exp":
            l_param = config["l"]

            def rand_func(exp):
                r = np.random.exponential(l_param)
                while r > 1:
                    r = np.random.exponential(l_param)
                return exp[2]["capacity"] - int(exp[2]["capacity"] * r)
        elif config["name"] == "beta":
            alpha, beta = config["alpha"], config["beta"]
            rand_func = lambda exp: exp[2]["capacity"] - int(exp[2]["capacity"] * np.random.beta(alpha, beta))

        # TODO: Improve this code. Now we have a mapping between both graphs, so there is no need to
        # store channels already assigned (we can iterate by G1's edges)
        # We randomly assign one of the channel's balances, and set the other balance to the remaining amount
        assigned_channels = {}
        for e in self.g2.edges(data=True):
            if not e[2]["channel_id"] in assigned_channels:
                e[2]["balance"] = rand_func(e)
                assigned_channels[e[2]["channel_id"]] = e[2]["capacity"] - e[2]["balance"]
            else:
                e[2]["balance"] = assigned_channels[e[2]["channel_id"]]

    @staticmethod
    def __check_htlc_config(config):
        """
        Checks the distribution and htlc configuration

        :param config: dict, distribution name (key 'name'), and params (keys depend on distribution name).
        :return:
        """
        assert "name" in config, "No distribution specified"
        assert config["name"] in ["const"], "Unrecognized distribution name"
        if "amount_fract" in config:
            assert config["amount_fract"] * config["number"] <= 1, "Not enough balance for that number of HTLCs!"

    def __assign_rand_htlc(self, config):
        """
        Randomly assigns pending HTLCs to channels following the specified distribution.
        Pending HTLCs are not assigned if config is None.

        :param config: dict, distribution name (key 'name'), and params (keys depend on distribution name).
            Recognized keys are:

            name:           "const"
            number:         int
            amount_fract:   int

            Examples:
                config = {"name": "const", "number": 1, "amount_fract": 0.1}
                """
        rand_func = None
        if config is None:
            # Do not assign balances if config is None
            print("INFO: pending HTLCs not assigned")
            return

        self.__check_htlc_config(config)
        print("INFO: pending HTLCs assigned using a {} distribution ({})".format(config["name"], config))

        if config["name"] == "const":
            def rand_func(exp):
                htlc_dict_temp, amounts_temp = {}, 0
                for i in range(config["number"]):
                    amount = config["amount_fract"] * exp[2]["balance"]
                    # TODO: handle expiration times!
                    htlc_dict_temp[i] = (amount, 0)
                    amounts_temp += amount
                return htlc_dict_temp, amounts_temp

        for e in self.g2.edges(data=True):
            htlc_dict, amounts = rand_func(e)
            e[2]["pending_htlc"] = htlc_dict
            e[2]["balance"] = e[2]["balance"] - amounts

    def __check_correctness(self):
        """
        Check the three restrictions explained in the paper (page 2)

        :return:
        Prints info about Balance and Capacity on the channels
        """
        print("INFO: checking correctness of the imported graph (disable for better performance)")

        # Check 1: Same number of nodes in both graphs
        assert self.g1.number_of_nodes() == self.g2.number_of_nodes()

        # Check 2: Double number of edges in g2
        assert 2 * self.g1.number_of_edges() == self.g2.number_of_edges()

        # Check 3: The sum of the balances and blocked amounts in HTLCs on both sides of the channel
        # must be equal to the capacity
        for e in self.g1.edges(data=True, keys=True):
            r = self.get_ke2_from_ke1(e[2], u=e[0], v=e[1])

            one_edge_data = self.g2[e[0]][e[1]][r[0]]
            other_edge_data = self.g2[e[1]][e[0]][r[1]]

            print('CHANNEL_ID: %s' % (e[2]))
            balance_one_edge_data = one_edge_data["balance"] + sum([v[0]
                                                                    for v in one_edge_data["pending_htlc"].values()])
            print('%sBALANCE: %s AND BALANCE SQUARED: %s FROM %s TO %s' % (utils.spaces, one_edge_data["balance"],
                                                                           balance_one_edge_data,
                                                                           self.nodeDict[e[0]]['alias'],
                                                                           self.nodeDict[e[1]]['alias']))

            balance_other_edge_data = other_edge_data["balance"] + sum([v[0]
                                                                        for v in
                                                                        other_edge_data["pending_htlc"].values()])
            print('%sBALANCE: %s AND BALANCE SQUARED: %s FROM %s TO %s' % (utils.spaces, other_edge_data["balance"],
                                                                           balance_other_edge_data,
                                                                           self.nodeDict[e[1]]['alias'],
                                                                           self.nodeDict[e[0]]['alias']))
            print('%sCAPACITY CHANNEL: %s' % (utils.spaces, e[3]["capacity"]))

            assert balance_one_edge_data + balance_other_edge_data == e[3]["capacity"]

    def get_ke2_from_ke1(self, ke1, u=None, v=None):
        """
        Given the key of an undirected edge from G1, return the two keys corresponding to the directed edges in G2.

        :param ke1:key of an edge from G1
        :param u: a node incident to the edge
        :param v: the other node incident to the edge
        :return:
        """
        # TODO: Is there a better way to do this? We need to know the nodes in order to retrieve the edge!
        if u is None or v is None:
            for e in self.g1.edges(keys=True, data=True):
                if e[2] == ke1:
                    u, v = e[0], e[1]
                    break

        ke2_1 = "{}-{}".format(ke1, u)
        ke2_2 = "{}-{}".format(ke1, v)
        return ke2_1, ke2_2

    @staticmethod
    def get_ke1_from_ke2(ke2):
        """
        Given the key of a directed edge from G2, return the key from the corresponding undirected edge from G1.

        :param ke2: key of an edge from G2
        :return: key of an edge from G1
        """
        return ke2.split("-")[0]

    def get_number_of_nodes(self):
        """
        :return: int
        """
        return self.g1.number_of_nodes()

    def get_total_number_of_channels(self):
        """
        :return: int
        """

    def get_number_of_channels_by_node(self, node=None):
        """
        :return: dictionary with node ids as keys, number of channels as values if node=None,
            or int with number of channels by a given node
        """
        if node is None:
            dict_node_edge = {}
            for element in self.g1.nodes:
                dict_node_edge[element] = len(self.g1.edges(element))
            return dict_node_edge
        else:
            return len(self.g1.edges(node))

    def get_number_of_channels_distr(self, normalized=True):
        """
        Return the distribution of the number of channels per the node (both the pdf and cdf). The format can be:
            x: a list with all number of channels found
            pdf: a list with the number of nodes with each of the number of channels in x
            cdf: a list with the number of nodes with less than or equal each of the number of channels in x
        If normalized=True, return pdf and cdf values over 1. Otherwise, use absolute numbers.

        :param normalized: boolean
        :return: 3-element tuple, each element is a list
        """
        pass

    def get_total_network_capacity(self):
        """
        :return: int
        """
        total_capacity = 0
        for i in self.g1.edges:
            total_capacity = total_capacity + self.g1[i[0]][i[1]][i[2]]['capacity']
        return total_capacity

    def get_network_capacity_by_node(self, node=None):
        """
        :return: dictionary with node ids as keys, capacity per node if node=None,
            or int with capacity by a given node
        """
        if node is None:
            dict_cap_node = {}
            for e in self.g1.nodes:
                dict_cap_node[e] = 0
            for i in self.g1.edges:
                dict_cap_node[i[0]] = dict_cap_node[i[0]] + self.g1[i[0]][i[1]][i[2]]['capacity']
                dict_cap_node[i[1]] = dict_cap_node[i[1]] + self.g1[i[0]][i[1]][i[2]]['capacity']
            return dict_cap_node
        else:
            capacity = 0
            for i in self.g1.edges:
                if (i[0] == node) or (
                        i[1] == node):
                    capacity = capacity + self.g1[i[0]][i[1]][i[2]]['capacity']
            return capacity

    def get_network_capacity_distr(self, normalized=True):
        """
        COMPTE: això ho faria sobre les arestes! (pensem si també té sentit tenir les dades sobre els nodes)

        Return the distribution of the capacity (both the pdf and cdf). The format can be:
            x: a list with all capacities found
            pdf: a list with the number of nodes with each of the capacities in x
            cdf: a list with the number of nodes with less than or equal each of the capacities in x

        If normalized=True, return pdf and cdf values over 1. Otherwise, use absolute numbers.

        :return: 3-element tuple, each element is a list
        """

    def get_total_disabled_capacity(self):
        """
        Dependent on node policy and balance.

        :return: tuple, (total disabled, percentage over the total)
        """
        counter = 0
        for i in self.g2.edges:
            if (self.g2[i[0]][i[1]][i[2]]['policy_dest'] is not None) and (
                    self.g2[i[0]][i[1]][i[2]]['policy_dest']['disabled']):
                counter = counter + self.g2[i[0]][i[1]][i[2]]['balance']
        return counter

    def get_disabled_capacity_by_node(self, node=None):
        """
        :return: dictionary with node ids as keys, disabled capacity per node if node=None,
            or int with disabled capacity by a given node
        """
        if node is None:
            dict_cap_node = {}
            for e in self.g2.nodes:
                dict_cap_node[e] = 0
            for i in self.g2.edges:
                if (self.g2[i[0]][i[1]][i[2]]['policy_dest'] is not None) and (
                        self.g2[i[0]][i[1]][i[2]]['policy_dest']['disabled']):
                    dict_cap_node[i[0]] = dict_cap_node[i[0]] + self.g2[i[0]][i[1]][i[2]]['balance']
            return dict_cap_node
        else:
            counter = 0
            for i in self.g2.edges:
                if (i[0] == node) and (self.g2[i[0]][i[1]][i[2]]['policy_dest'] is not None) and (
                        self.g2[i[0]][i[1]][i[2]]['policy_dest']['disabled']):
                    counter = counter + self.g2[i[0]][i[1]][i[2]]['balance']
            return counter

    def get_disabled_capacity_distr(self, normalized=True):
        pass

    def get_total_blocked_amount(self):
        """
        Return the total blocked amount in HTLCs

        :return: tuple, (total blocked, percentage over the total)
        """
        pass

    def get_blocked_amount_by_node(self):
        pass

    def get_total_blocked_distr(self, normalized=True):
        """
        Return the distribution of the blocked capacity (both the pdf and cdf). The format can be:
            x: a list with all blocked capacities found
            pdf: a list with the number of nodes with each of the blocked capacities in x
            cdf: a list with the number of nodes with less than or equal each of the blocked capacities in x
        If normalized=True, return pdf and cdf values over 1. Otherwise, use absolute numbers.

        :return: 3-element tuple, each element is a list
        """

    def get_total_useful_capacity(self):
        """
        total - disabled - blocked in htlc

        :return: tuple, (total useful, percentage over the total)
        """
        pass

    def get_useful_capacity_by_node(self):
        pass

    def get_useful_capacity_distr(self, normalized=True):
        pass

    def get_balance_by_node(self, node=None):
        """
        Delivers the balance of either the whole network or a specific node

        :param node: node to get balance
        :return: dictionary with node ids as keys, balance per node if node=None,
            or int with balance by a given node
        """
        if node is None:
            dict_balance_node = {}
            for e in self.g2.nodes:
                dict_balance_node[e] = 0
            for i in self.g2.edges:
                dict_balance_node[i[0]] = dict_balance_node[i[0]] + self.g2[i[0]][i[1]][i[2]]['balance']
            return dict_balance_node
        else:
            balance = 0
            for i in self.g2.edges:
                if i[0] == node:
                    balance = balance + self.g2[i[0]][i[1]][i[2]]['balance']
            return balance

    def get_balance_distr(self, normalized=True):
        """
        Return the distribution of the balances (both the pdf and cdf). The format can be:
            x: a list with all balances found
            pdf: a list with the number of nodes with each of the balances in x
            cdf: a list with the number of nodes with less than or equal each of the balances in x
        If normalized=True, return pdf and cdf values over 1. Otherwise, use absolute numbers.

        :return: 3-element tuple, each element is a list
        """

    def get_number_of_nodes_by_implementation(self, divide_by_version=False):
        """
        Count number of nodes for each implementation. Depending on the flag divide_by_version,
        we distinguish between different versions of the same implementation or not.

        :return: dict, key is implementation name, value is tuple with number of nodes and percentage over the total
        """
        pass

    def get_implementation_by_node(self, node=None):
        pass

    def block_payment(self, payment: route_pay.Payment, is_node_policy: bool):
        """
        Sets the structure for htlcs with the blocked amount and decreases/increases balances

        :param payment: as returned by queryroute
        :param is_node_policy: as check of a node policy
        :return:
            The htlc structure contains the preimage which is validated at the time a payment takes place. Moreover,
            the payment status at this time is IN_FLIGHT
        """
        if payment.error is None:
            print('%s***** BEGIN OF BLOCK PAYMENT *****' % utils.spaces)
            payment_hash, preimage = utils.request_payment_hash_destiny(payment.pubkey_destiny)
            payment.payment_hash = payment_hash
            payment.creation_time_ns = time.time_ns()

            for h in payment.routes[0].hops:
                label_edge = "{}-{}".format(h.channel_id, h.pub_key)
                if label_edge in self.edgeDict:
                    edge = self.edgeDict[label_edge]
                    e = self.g2.get_edge_data(edge[0], edge[1])

                    print('%s%sCHANNEL_ID: %s FROM %s TO %s' % (utils.spaces, utils.spaces, label_edge,
                                                                self.nodeDict[edge[1]]['alias'],
                                                                self.nodeDict[h.pub_key]['alias']))
                    print(
                        '%s%s%sAMOUNT: %s - FEE: %s' % (utils.spaces, utils.spaces, utils.spaces, h.amt_2_fwrd, h.fee))
                    htlc = route_pay.HTLC(
                        time_lock_delta=IMPLEMENTATION_PARAMS[IMPL_LND]['time_lock_delta'] if not is_node_policy else
                        e[label_edge]['policy_dest']['time_lock_delta'],
                        fee_base_msat=IMPLEMENTATION_PARAMS[IMPL_LND]['fee_base_msat'] if not is_node_policy else
                        e[label_edge]['policy_dest']['fee_base_msat'],
                        fee_rate_mili_msat=IMPLEMENTATION_PARAMS[IMPL_LND]['fee_rate_milli_msat'] if not is_node_policy
                        else e[label_edge]['policy_dest']['fee_rate_milli_msat'],
                        payment_hash=payment_hash, payment_preimage=preimage,
                        payment_status=ln.Payment.PaymentStatus.IN_FLIGHT,
                        creation_time_ns=time.time_ns(), payment_failure_reason=None
                    )
                    htlc.htlc_payment = route_pay.HTLCPayment(htlc_status=ln.HTLCAttempt.HTLCStatus.IN_FLIGHT, hop=h,
                                                              attempt_time_ns=time.time_ns(), resolve_time_ns=None,
                                                              failure_code=None)
                    pending = route_pay.PendingHtlc(incoming=False, hash_lock=payment_hash,
                                                    amount=htlc.htlc_payment.hop.amt_2_fwrd
                                                           + 2 * htlc.htlc_payment.hop.fee,
                                                    expiration_height=htlc.htlc_payment.hop.expiry)
                    dict_htlc = {}
                    dict_pending = {}
                    last_pending = list(e[label_edge]['pending_htlc'])[-1] + 1
                    htlc.payment_index = last_pending
                    dict_htlc[last_pending] = htlc.__dict__
                    dict_pending[last_pending] = pending.__dict__
                    if 'htlc' not in e[label_edge]:
                        e[label_edge]['htlc'] = dict_htlc
                    else:
                        e[label_edge]['htlc'].update(dict_htlc)
                    if 'val_pending_htlc' not in e[label_edge]:
                        e[label_edge]['val_pending_htlc'] = dict_pending
                    else:
                        e[label_edge]['val_pending_htlc'].update(dict_pending)
                    e[label_edge]['pending_htlc'][last_pending] = (round(htlc.htlc_payment.hop.amt_2_fwrd +
                                                                         htlc.htlc_payment.hop.fee, 4), 0)
                    e[label_edge]['balance'] = round(e[label_edge]['balance'] - round(htlc.htlc_payment.hop.amt_2_fwrd +
                                                                                      htlc.htlc_payment.hop.fee, 4), 4)

                    e[label_edge]['capacity'] = e[label_edge]['capacity'] - (htlc.htlc_payment.hop.amt_2_fwrd +
                                                                             htlc.htlc_payment.hop.fee)
            print('%s***** END OF BLOCK PAYMENT *****' % utils.spaces)

    def make_payment(self, payment: route_pay.Payment):
        """
        Unblocks htlcs and make payment (increases balances to the receiving party)

        :param payment:
        :return:
        The payment consists on unblock the amount and fees that traverse through the route. Thus, the payment walks
        on reverse order the route, since destiny node must confirm that the hash of the preimage is a valid one.
        With the valid confirmation, the data channel is updated, specifically the payment and htlc unblocked
        At this point, the status and failure of the hltc is updated with:
            HTLCStatus: SUCCEEDED
            Failure Reason: None
        """
        time.sleep(random.randrange(0, self.parameters['sleep']))

        timeout = random.randrange(self.parameters["min_diff_ns"], self.parameters["max_diff_ns"],
                                   self.parameters["step_diff_ns"])
        diff_time_ns = time.time_ns() - payment.creation_time_ns

        if payment.error is None:
            if diff_time_ns < timeout:
                print('{}***** BEGIN OF PAYMENT *****'.format(utils.spaces))

                for h in reversed(payment.routes[0].hops):
                    label_edge = "{}-{}".format(h.channel_id, h.pub_key)
                    if label_edge in self.edgeDict:
                        edge = self.edgeDict[label_edge]
                        opposite_label_edge = "{}-{}".format(h.channel_id, edge[1])
                        e = self.g2.get_edge_data(edge[0], edge[1])

                        # Update the channel data with the payment and unblock htlc
                        for pvt in e[label_edge]['htlc']:
                            htlc = e[label_edge]['htlc'][pvt]
                            if htlc['payment_preimage'] is not None and htlc['payment_hash'] == payment.payment_hash \
                                    and utils.check_preimage_hash(htlc['payment_preimage'], htlc['payment_hash']):
                                print('%s%sUNBLOCK ON THE CHANNEL_ID: %s FROM %s TO %s' % (utils.spaces, utils.spaces,
                                                                                           label_edge,
                                                                                           self.nodeDict[edge[1]][
                                                                                               'alias'],
                                                                                           self.nodeDict[edge[0]][
                                                                                               'alias']))
                                htlc['payment_index'] = pvt
                                htlc['payment_preimage'] = htlc['payment_preimage']
                                htlc['payment_failure_reason'] = ln.PaymentFailureReason.FAILURE_REASON_NONE
                                htlc_payment = htlc['htlc_payment']
                                htlc_payment.htlc_status = ln.HTLCAttempt.HTLCStatus.SUCCEEDED
                                htlc_payment.resolve_time_ns = time.time_ns()

                                # Increase the balance to the receiving party
                                print('%s%s%sPAYMENT ON THE CHANNEL_ID: %s FROM %s TO %s' % (utils.spaces, utils.spaces,
                                                                                             utils.spaces,
                                                                                             opposite_label_edge,
                                                                                             self.nodeDict[edge[0]][
                                                                                                 'alias'],
                                                                                             self.nodeDict[edge[1]][
                                                                                                 'alias']))
                                print('%s%s%sAMOUNT PAID/FEE: %s' % (utils.spaces, utils.spaces, utils.spaces,
                                                                     -(h.amt_2_fwrd if h.fee == 0 else h.fee)))

                                payment_party = self.g2.get_edge_data(edge[1], edge[0])
                                payment_party = payment_party[opposite_label_edge]
                                # payment_party['pending_htlc'][pvt] = (-(h.amt_2_fwrd if h.fee == 0 else h.fee), 0)
                                last_pending = list(payment_party['pending_htlc'])[-1] + 1
                                payment_party['pending_htlc'][last_pending] = (round(-(h.amt_2_fwrd + h.fee), 4), 1)
                                payment_party['balance'] = round(
                                    payment_party['balance'] + round(float(h.amt_2_fwrd + h.fee),
                                                                     4), 4)
                                payment_party['capacity'] = payment_party['capacity'] + float(h.amt_2_fwrd if h.fee == 0
                                                                                              else h.fee)

                if not self.is_snapshot and self.is_manual_test != 'y':
                    print('%s==============================================' % utils.spaces)
                    self.make_payment_implementation(payment)

                print('***** END OF PAYMENT *****')
            else:
                print('***** BEGIN OF CANCEL OF PAYMENT *****')
                self.reverse_payment(payment)
                print('***** END OF CANCEL OF PAYMENT *****')
        else:
            print("%sERROR ON PAYMENT: %s" % (utils.spaces, payment.error))

    def make_payment_implementation(self, payment: route_pay.Payment):
        """
        Sends a payment from an origin node to a destiny node through its implementation either lnd, c-lightning or
        eclair

        :param payment: payment sent from origin node to destiny node
        :return:
        """
        response = None
        if payment.pubkey_origin in self.connectors['lnd']:
            print('%s*** PAYMENT ON LND FROM %s TO %s ***' % (utils.spaces,
                                                              utils.get_alias_pubkey(payment.pubkey_origin, self.g1),
                                                              utils.get_alias_pubkey(payment.pubkey_destiny, self.g1)))

            connector = self.connectors['lnd'][payment.pubkey_origin]
            response = lnd.send_payment_rpc(macaroon_dir=connector["macaroon_dir"], cert_dir=connector["cert_dir"],
                                            port=connector["port"], pubkey_destiny=payment.pubkey_destiny,
                                            payment_amount=payment.payment_amount, payment_hash=payment.payment_hash,
                                            host=connector["host"], final_cltv_delta=payment.routes[0].total_time_lock)
        else:
            if payment.pubkey_origin in self.connectors['eclair']:
                print('%s*** PAYMENT ON ECLAIR FROM %s TO %s ***' % (utils.spaces,
                                                                     utils.get_alias_pubkey(payment.pubkey_origin,
                                                                                            self.g1),
                                                                     utils.get_alias_pubkey(payment.pubkey_destiny,
                                                                                            self.g1)))

                connector = self.connectors['eclair'][payment.pubkey_origin]
                response = eclair.send_payment(node_destiny=payment.pubkey_destiny,
                                               payment_amount=payment.payment_amount,
                                               payment_hash=payment.payment_hash, fee_sat=payment.routes[0].total_fees,
                                               host=connector["host"], port=connector["port"], user=connector["user"],
                                               passwd=connector["passwd"])
            else:
                if payment.pubkey_origin in self.connectors['c-lightning']:
                    print('%s*** PAYMENT ON C-LIGHTNING FROM %s TO %s ***' % (utils.spaces,
                                                                              utils.get_alias_pubkey(
                                                                                  payment.pubkey_origin, self.g1),
                                                                              utils.get_alias_pubkey(
                                                                                  payment.pubkey_destiny, self.g1)))

                    connector = self.connectors['c-lightning'][payment.pubkey_origin]
                    response = clight.send_payment(macaroon_dir=connector['macaroon_dir'],
                                                   pubkey_destiny=payment.pubkey_destiny,
                                                   payment_amount=payment.payment_amount)

        if response is not None:
            print('%s%sPAYMENT RESPONSE:%s' % (utils.spaces, utils.spaces, response))

    def reverse_payment(self, payment: route_pay.Payment):
        """
        Reverse a payment established through the block and pay functions that calculate the balances in the forward
        and backward channels for each hop in a route

        :param payment: payment sent from an origin node to a destiny node
        :return:
        """
        if payment.error is None:
            for h in payment.routes[0].hops:
                label_edge = "{}-{}".format(h.channel_id, h.pub_key)
                if label_edge in self.edgeDict:
                    edge = self.edgeDict[label_edge]
                    e = self.g2.get_edge_data(edge[0], edge[1])

                    for pvt in e[label_edge]['htlc']:
                        htlc = e[label_edge]['htlc'][pvt]
                        if htlc['payment_preimage'] is not None and htlc['payment_hash'] == payment.payment_hash:
                            print('%s REVERSE PAYMENT ON THE CHANNEL_ID: %s FROM %s TO %s' % (utils.spaces, label_edge,
                                                                                              self.nodeDict[edge[1]][
                                                                                                  'alias'],
                                                                                              self.nodeDict[edge[0]][
                                                                                                  'alias']))
                            htlc['payment_failure_reason'] = ln.PaymentFailureReason.FAILURE_REASON_TIMEOUT
                            htlc['payment_status'] = ln.Payment.PaymentStatus.FAILED
                            htlc['htlc_payment'].htlc_status = ln.HTLCAttempt.HTLCStatus.FAILED

                            print('%s%s%s AMOUNT TO REVERSE PAID/FEE: %s' % (utils.spaces, utils.spaces, utils.spaces,
                                                                             (h.amt_2_fwrd if h.fee == 0 else h.fee)))

                            pending = htlc['payment_index']
                            e[label_edge]['pending_htlc'][pending] = (0, 0)
                            e[label_edge]['balance'] = round(e[label_edge]['balance'] +
                                                             round(htlc['htlc_payment'].hop.amt_2_fwrd +
                                                                   htlc['htlc_payment'].hop.fee, 4), 4)

                            e[label_edge]['capacity'] = e[label_edge]['capacity'] + (
                                    htlc['htlc_payment'].hop.amt_2_fwrd +
                                    htlc['htlc_payment'].hop.fee)

    def __start_payment(self):
        """
        The parameters to perform the payment are considered at this point, hence, the simulation takes on account
        four main parameters: Amount_Satoshis, origin node and destiny node (alias) and node policy values (either
        by IMPLEMENTATION_PARAMS or policies of the own node)
        The user can interact to make another payment between new nodes, request a new route or make block and unblock
        of payments.

        :return:
        """
        self.is_manual_test = input("MANUAL TEST (y/n)?\n")
        if self.is_manual_test == "y":
            while input("REQUEST A NEW PAYMENT (y/n)?\n") == 'y':
                payment = None
                payment_amount = int(utils.input_value('100', 'Payment amount (Default: 100):\n', False, True))
                node_origin = utils.input_value(self.parameters["connector"]["lnd"]["alias"],
                                                'Input node origin alias (Default: alice):\n', False, False)
                node_destiny = utils.input_value('dave', 'Input node destiny alias (Default: dave):\n', False, False)
                is_node_policy = utils.input_value('y', 'Do you prefer node policy params (y/n)?\n', False, False)

                while input("REQUEST A NEW ROUTE (y/n)?\n") == 'y':
                    if not self.is_snapshot and input("API QUERY ROUTE (y - lncli /n - Yen's algorithm)?\n") == 'y':
                        print("{}{}***** LND CONNECTOR *****".format(utils.spaces, utils.spaces))
                        payment = lnd.query_routes(self.g1, self.secure_channel,
                                                   self.nodeDict, self.edgeDict, node_origin, node_destiny,
                                                   payment_amount, is_manual_test=True)
                    else:
                        print("{}{}***** YEN'S ALGORITHM *****".format(utils.spaces, utils.spaces))
                        payment = spy.query_route_yen(self.g1, self.g2, node_origin, node_destiny, payment_amount,
                                                      self.parameters["num_k"], is_manual_test=True)

                if payment is not None:
                    self.block_payment(payment, True if is_node_policy == 'y' else False)

                    self.make_payment(payment)
                else:
                    print("{}UNABLE TO FIND A PATH - NO CHANNEL ID AVAILABLE".format(utils.spaces))
        else:
            if not self.is_snapshot:
                print('***** BEGIN OF PROCESS TO FIND CONNECTORS *****')
                self.connectors = utils.get_parameters_connection(self.parameters, self.g1)
                print('***** END OF PROCESS TO FIND CONNECTORS *****')
            if self.is_snapshot:
                utils.create_test_file(self.g1, self.parameters['connector'], self.parameters["num_routes"],
                                       self.parameters["max_amount"], self.location, self.parameters["test_file"],
                                       self.is_snapshot)
            else:
                if input("DO YOU WANT TO CREATE A TEST FILE? (y/n): ") == "y":
                    utils.create_test_file(self.g1, self.parameters['connector'], self.parameters["num_routes"],
                                           self.parameters["max_amount"], self.location, self.parameters["test_file"],
                                           self.is_snapshot)

            message = input("DESCRIBE THE TYPE OF TEST?\n")
            message = datetime.now().strftime("%m/%d/%Y, %H:%M:%S") + '---' + message

            payments = self.get_payments_queryroute()
            print('\n\n')
            for payment in payments.items():
                self.make_payment(payment[1])

            self.payments = {"0": message}
            self.payments.update(payments)

    def get_payments_queryroute(self):
        """
        Invokes the connectors as well as the Yen's algorithm to get the query routes from source to destiny and its
        inverse route creates. Additionally, it the payment structures to perform the block payment and its
        corresponding payment. For each connector, the simulation reads the values from the test.json file to get
        the data about the different types of nodes (lnd, eclair and c-lightning.). That data is used to set the
        parameter's nodes

        :return: list of route_payment.Payment
        """
        index = utils.Counter()
        payments = {}
        for key, value in self.tests.items():
            if key == "lnd" and value["flag"]:
                print("********** LND **********")
                value["node"]["implementation"] = key
                self.__set_param_node(parameters_test=value["node"])
                for route in value["routes"]:
                    if not self.is_snapshot:
                        for i in range(self.parameters["loop"]):
                            payments[str(index.preinc())] = lnd.query_routes(self.g1,
                                                                             self.secure_channel,
                                                                             self.nodeDict, self.edgeDict,
                                                                             route["origin"], route["destiny"],
                                                                             route["amount"])
                            self.block_payment(payments[index.__str__()], True)

                        payments[str(index.preinc())] = lnd.query_routes(self.g1,
                                                                         self.secure_channel, self.nodeDict,
                                                                         self.edgeDict,
                                                                         route["destiny"], route["origin"],
                                                                         route["amount"])
                        self.block_payment(payments[index.__str__()], True)

                    payments[str(index.preinc())] = spy.query_route_yen(self.g1, self.g2, route["origin"],
                                                                        route["destiny"], route["amount"],
                                                                        self.parameters["num_k"])
                    self.block_payment(payments[index.__str__()], True)

                    payments[str(index.preinc())] = spy.query_route_yen(self.g1, self.g2, route["destiny"],
                                                                        route["origin"], route["amount"],
                                                                        self.parameters["num_k"])
                    self.block_payment(payments[index.__str__()], True)
            else:
                if key == "eclair" and value["flag"]:
                    print("********** ECLAIR **********")
                    for route in value["routes"]:
                        if not self.is_snapshot:
                            for i in range(self.parameters["loop"]):
                                payments[str(index.preinc())] = eclair.query_routes(route["destiny"],
                                                                                    route["amount"],
                                                                                    value["node"]["host"],
                                                                                    value["node"]["port"],
                                                                                    value["node"]["user"],
                                                                                    value["node"]["passwd"])
                                self.block_payment(payments[index.__str__()], True)

                        payments[str(index.preinc())] = spy.query_route_yen(self.g1, self.g2, route["origin"],
                                                                            route["destiny"], route["amount"],
                                                                            self.parameters["num_k"])
                        self.block_payment(payments[index.__str__()], True)

                        payments[str(index.preinc())] = spy.query_route_yen(self.g1, self.g2, route["destiny"],
                                                                            route["origin"], route["amount"],
                                                                            self.parameters["num_k"])
                        self.block_payment(payments[index.__str__()], True)
                else:
                    if key == "c-lightning" and value["flag"]:
                        print("********** C-LIGHTNING **********")
                        for route in value["routes"]:
                            if not self.is_snapshot:
                                macaroon_dir = (self.parameters["polar_path"] + IMPL_NODE).replace(
                                    'IMPLEMENTATION', key).replace('NODE_NAME', value["node"]["alias"]) \
                                               + self.parameters["connector"]["c-lightning"]["macaroon_dir"]
                                for i in range(self.parameters["loop"]):
                                    payments[str(index.preinc())] = clight.query_routes(macaroon_dir,
                                                                                        route["origin"],
                                                                                        route["destiny"],
                                                                                        route["amount"])
                                    self.block_payment(payments[index.__str__()], True)

                                payments[str(index.preinc())] = clight.query_routes(macaroon_dir,
                                                                                    route["destiny"],
                                                                                    route["origin"],
                                                                                    route["amount"])
                                self.block_payment(payments[index.__str__()], True)

                            payments[str(index.preinc())] = spy.query_route_yen(self.g1, self.g2, route["origin"],
                                                                                route["destiny"], route["amount"],
                                                                                self.parameters["num_k"])
                            self.block_payment(payments[index.__str__()], True)

                            payments[str(index.preinc())] = spy.query_route_yen(self.g1, self.g2, route["destiny"],
                                                                                route["origin"], route["amount"],
                                                                                self.parameters["num_k"])
                            self.block_payment(payments[index.__str__()], True)
        return payments


json_filename = 'lnd_describegraph_regtest.json'
"""
Random balance distributions used in the paper:
    config = {"name": "const"}
    config = {"name": "unif"}
    config = {"name": "normal", "mu": 0.5, "sigma": 0.2}
    config = {"name": "exp", "l": 1}
    config = {"name": "beta", "alpha": 0.25, "beta": 0.25}
"""
balance_config = {"name": "const"}
"""
Example of random pending HTLCs distributions:
    config = {"name": "const", "number": 1, "amount_fract": 0.1}
    config = {"name": "const", "number": 0}
We only have a constant distribution, that assigns the given number of pending HTLC to every channel, with
an amount_fract of the amount of the balance locked in each HTLC.
"""
htlc_config = {"name": "const", "number": 3, "amount_fract": 0.1}

ln_graph = LNPayment(json_filename, balance=balance_config, htlc=htlc_config)

if hasattr(LNPayment, 'g1') and hasattr(LNPayment, 'g2'):
    print(nx.info(ln_graph.g1))
    print(nx.info(ln_graph.g2))
