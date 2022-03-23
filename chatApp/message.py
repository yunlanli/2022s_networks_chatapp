#
# This file contains functions to create and parse client & server messages
#

from datetime import datetime
import uuid

from .constant import TIMEOUT

# A Message can be one of these types
CHAT_MSG = 0
REGISTER = 1
DEREGISTER = 2
ACK_REG = 3
NACK_REG = 4
ACK_DEREG = 5
NACK_DEREG = 6
ACK_CHAT_MSG = 7
PEERS_UPDATE = 8
SAVE_MSG = 9
ACK_SAVE_MSG = 10
NACK_SAVE_MSG = 11
OFFLINE_MSG = 12
BROADCAST_MSG = 13
ACK_BROADCAST_MSG = 14

delim = " "

typ_to_str = [
    "CHAT_MSG", "REGISTER", "DEREGISTER", "ACK_REG", "ACK_DEREG",
    "ACK_CHAT_MSG"
]

REGULAR_MESSAGE = 0
CHANNEL_MESSAGE = 1


def get_ts():
    return datetime.now().timestamp()


def timeout(ts1, ts2):
    # if more than 500 milisecond,
    # retrn true otherwise false
    return ts2 * 1000 - ts1 * 1000 > TIMEOUT


def msg_type(typ):
    return typ_to_str[typ]


def msg_id():
    return str(uuid.uuid4())


def shorten_msg(msg):
    if len(msg) > 25:
        return f"{msg[:25]}.."
    else:
        return msg


def make(typ, content="", id=None):
    id = msg_id() if id is None else id
    msg = map(str, [typ, id, content])
    encoded = f"{delim.join(msg)}".encode()
    return encoded, id


def parse(msg):
    decoded = msg.decode()
    [typ, id, content] = decoded.split(delim, 2)

    return int(typ), id, content
