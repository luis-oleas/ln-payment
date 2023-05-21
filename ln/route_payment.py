import time
import ln.utils as utils
import ln.lightning_pb2 as rpc
from enum import Enum
from typing import List


class RoutingPolicy:
    """
        Class used to gather data about node policy that is part of the ChannelEdge
    """

    def __init__(self, time_lock_delta: int, min_htlc, fee_base_msat: int, fee_rate_milli_msat: int, disabled: bool,
                 max_htlc_msat, last_update):
        """

        :param time_lock_delta:
        :param min_htlc:
        :param fee_base_msat:
        :param fee_rate_milli_msat:
        :param disabled:
        :param max_htlc_msat:
        :param last_update:
        """
        self.time_lock_delta = time_lock_delta
        self.min_htlc = min_htlc
        self.fee_base_msat = fee_base_msat
        self.fee_rate_milli_msat = fee_rate_milli_msat
        self.disabled = disabled
        self.max_htlc_msat = max_htlc_msat
        self.last_update = last_update


class ChannelEdge:
    """
        Class used to represent the data that belongs to a channel between a pair of nodes
    """

    def __init__(self, channel_id: str, chan_point, last_update, node1_pub: str, node2_pub: str, capacity: int,
                 node1_policy: RoutingPolicy, node2_policy: RoutingPolicy):
        """

        :param channel_id:
        :param chan_point:
        :param last_update:
        :param node1_pub:
        :param node2_pub:
        :param capacity:
        :param node1_policy: Reference to RoutingPolicy
        :param node2_policy: Reference to RoutingPolicy
        """
        self.channel_id = channel_id
        self.chan_point = chan_point
        self.last_update = last_update
        self.node1_pub = node1_pub
        self.node2_pub = node2_pub
        self.capacity = capacity
        self.node1_policy: RoutingPolicy = node1_policy
        self.node2_policy: RoutingPolicy = node2_policy


class Payment:
    """
        Class used to handle the payment data (source and destiny pubkey, amount and routes) between a pair of nodes
    """

    def __init__(self, pubkey_origin, pubkey_destiny, payment_amount: int, routes,
                 creation_time_ns: int, payment_hash=None, error=None):
        """

        :param pubkey_origin:
        :param pubkey_destiny:
        :param payment_amount:
        :param routes:
        """
        self.pubkey_origin = pubkey_origin
        self.pubkey_destiny = pubkey_destiny
        self.payment_amount = payment_amount
        self.routes: Route = routes
        self.payment_hash = payment_hash
        self.creation_time_ns = creation_time_ns
        self.error = error


class HTLCPayment:
    """
        Class used to represent the payment status and its possible failure codes
    """

    def __init__(self, htlc_status: rpc.HTLCAttempt.HTLCStatus = None, hop=None, attempt_time_ns: int = None,
                 resolve_time_ns: int = None, failure_code: rpc.Failure.FailureCode = None):
        """

        :param htlc_status:
        :param hop:
        :param attempt_time_ns:
        :param resolve_time_ns:
        :param failure_code:
        """
        # IN_FLIGHT, SUCCEEDED, FAILED
        self.htlc_status: rpc.HTLCAttempt.HTLCStatus = htlc_status
        # The route taken by this HTLC
        self.hop: Hop = hop
        # The time on nanoseconds at which the HTLC was sent
        self.attempt_time_ns = attempt_time_ns
        # The time on nanoseconds at which the HTLC was settled or failed
        self.resolve_time_ns = resolve_time_ns
        # The failure codes as defined in the BOLT #4.
        self.failure_code: rpc.Failure.FailureCode = failure_code


class HTLC:
    """
        Class used to gather the whole data related to HTLC and its payment and its status. It also contains the
        payment hash and payment preimage required to validate the payment between hops
    """

    def __init__(self, time_lock_delta: int, fee_base_msat: int, fee_rate_mili_msat: int, payment_hash: bytes,
                 payment_preimage: bytes, payment_status, creation_time_ns: int,
                 payment_failure_reason: rpc.Payment.PaymentStatus):
        """

        :param time_lock_delta:
        :param fee_base_msat:
        :param fee_rate_mili_msat:
        :param payment_hash:
        :param payment_preimage:
        :param payment_status:
        :param creation_time_ns:
        :param payment_failure_reason:
        """
        # The timelock delta for HTLC forwarded over the channel. TimeLockDelta (or cltv_expiry_delta) is the minimum
        # number of blocks a node requires to be added to the expiry of HTLCs
        self.time_lock_delta: int = time_lock_delta
        # The base fee charged regardless of the number of milli-satoshis sent.
        self.fee_base_msat = fee_base_msat
        # The effective fee rate in milli-satoshis. The precision of this value / goes up to 6 decimal places, so 1e-6
        self.fee_rate_milli_msat = fee_rate_mili_msat
        # The hash of the payment
        self.payment_hash: bytes = payment_hash
        # The payment pre-image to unlock the payment
        self.payment_preimage: bytes = payment_preimage
        # UNKNOWN, IN_FLIGHT, SUCCEEDED, FAILED
        self.payment_status: rpc.Payment.PaymentStatus = payment_status
        # The time in nanoseconds at which the payment was created
        self.creation_time_ns = creation_time_ns
        # The htlcs made to settle the payment
        self.htlc_payment: HTLCPayment = HTLCPayment()
        # The creation index of this payment
        self.payment_index = None
        # FAILURE_REASON_NONE, FAILURE_REASON_TIMEOUT, FAILURE_REASON_NO_ROUTE, FAILURE_REASON_ERROR,
        # FAILURE_REASON_INCORRECT_PAYMENT_DETAILS, FAILURE_REASON_INSUFFICIENT_BALANCE
        self.payment_failure_reason: rpc.PaymentFailureReason = payment_failure_reason


class PendingHtlc:
    """
        Class used to gather data about a pending HTLC, it specifies the expiration in height blocks
    """

    def __init__(self, incoming: bool, amount: float, hash_lock: bytes, expiration_height):
        """

        :param incoming:
        :param amount:
        :param hash_lock:
        :param expiration_height:
        """
        # Flag that defines the node that receives the htlc
        self.incoming: bool = incoming
        # The value of payment on satoshis
        self.amount = amount
        # The hash payment
        self.hash_lock: bytes = hash_lock
        # The cltv value expired
        self.expiration_height = expiration_height


class Hop:
    """
        Class used to represent the hop between a pair of nodes, it contains the amount to forward as well as the
        fee charged by the node that sends the payment, therefore it is necessary to know the channel id and its
        capacity
    """

    def __init__(self, channel_id: str, channel_capacity: float, amt_2_fwrd: float, fee: float, expiry,
                 amt_2_fwrd_msat: float, fee_msat: float, pub_key: str, tlv_pay_load):
        """

        :param channel_id:
        :param channel_capacity:
        :param amt_2_fwrd:
        :param fee:
        :param expiry:
        :param amt_2_fwrd_msat:
        :param fee_msat:
        :param pub_key:
        :param tlv_pay_load:
        """
        # The channel id
        self.channel_id = channel_id
        # Channel capacity
        self.channel_capacity = channel_capacity
        # Amount to forward to the hop
        self.amt_2_fwrd = amt_2_fwrd
        # Fee on the channel
        self.fee = fee
        # Time that the channel expires (cltv_expiry)
        # CLTV locks bitcoins up until a (more or less) concrete time in the future. An actual time and date,
        # or a specific block height
        self.expiry = expiry
        # Amount to forward on millisatoshis
        self.amt_2_fwrd_msat = amt_2_fwrd_msat
        # Fee on millisatoshis
        self.fee_msat = fee_msat
        # Pub key of the hop optional to make a payment without relying on a copy of the channel graph
        self.pub_key = pub_key
        # If set to true, then this hop will be encoded using the new variable length TLV format
        self.tlv_pay_load = tlv_pay_load

    @property
    def __str__(self):
        return "|{0}| --> {1}".format(str(self.channel_id), str(self.channel_id))


class Route:
    """
        Class used to gather the whole data about hops and total payment amount and fees. It also contains the
        total time lock and the probability of success for the payment
    """

    def __init__(self):
        # The sum of time locks across the entire route, that could be considered the cltv to extend to the
        # first hop in the route
        self.total_time_lock = None
        # The sum of fees paid at each hop within the final route, 0 in the case of one-hop payment
        self.total_fees = None
        # The total amount of funds, including the fees at each hop, required to complete a payment over the route.
        # The first hop in the route that extends the HTLC will need to have at least this many satoshis
        self.total_amt = None
        # Total fees in milisatoshis
        self.total_fees_msat = None
        # Total amount in milisatoshis
        self.total_amt_msat = None
        # Probability route success
        self.success_prob = None
        # Data concerning to each hop
        self.hops: List[Hop] = []


class EnumDescriptor(Enum):
    """
        Class used as enumerator to add functionality to payment description
    """
    HTLCStatus = 0
    PaymentStatus = 1
    FailureCode = 2
    PaymentFailureReason = 3


def create_route(routes, pubkey_origin: str, pubkey_destiny: str, payment_amount: int, edge_dict: dict,
                 node_dict: dict):
    """
    Sets the payment with all the necessary data related with the route such as nodes origin and destiny, payment
    amount, and the hops on the route. Moreover, the payment contains the total payment amount, total fees, total time
    lock and success probability

    :param routes: Hops on the route to perform the payment
    :param pubkey_origin: pub key of the origin node
    :param pubkey_destiny: pub key of the destiny node
    :param payment_amount: amount to pay in satoshis
    :param edge_dict: dictionary with all the edges (channels)
    :param node_dict: dictionary with all the nodes
    :return: Payment structure
    """
    routes_ln = []

    if routes is not None:
        for route_temp in routes['routes']:
            index = 0
            route = Route()
            for hop_temp in route_temp['hops']:
                hop = Hop(channel_id=hop_temp['chan_id'], channel_capacity=hop_temp['chan_capacity'],
                          amt_2_fwrd=float(hop_temp['amt_to_forward']),
                          expiry=hop_temp['expiry'], amt_2_fwrd_msat=float(hop_temp['amt_to_forward_msat']),
                          pub_key=hop_temp['pub_key'],
                          tlv_pay_load=hop_temp['tlv_payload'] if 'tlv_payload' in hop_temp else False,
                          fee=float(hop_temp['fee']) if 'fee' in hop_temp else float(0),
                          fee_msat=float(hop_temp['fee_msat']) if 'fee_msat' in hop_temp else float(0))
                index += 1
                utils.print_info_hop(hop.channel_id, hop.pub_key, index, edge_dict, node_dict)

                route.hops.append(hop)

            route.total_amt = float(route_temp['total_amt'])
            route.total_amt_msat = float(route_temp['total_amt_msat'])
            route.total_fees = float(route_temp['total_fees']) if 'total_fees' in route_temp else float(0)
            route.total_fees_msat = float(route_temp['total_fees_msat']) if 'total_fees_msat' in route_temp else float(
                0)
            route.total_time_lock = int(route_temp['total_time_lock'])
            route.success_prob = routes['success_prob']

            utils.print_info_total_route(route.total_amt, route.total_fees, route.total_time_lock)

            routes_ln.append(route)

        return Payment(pubkey_origin, pubkey_destiny, payment_amount, routes_ln, time.time_ns())
