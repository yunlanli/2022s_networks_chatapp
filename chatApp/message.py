#
# This file contains functions to create and parse client & server messages
#

import uuid

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

delim = " "

typ_to_str = [
    "CHAT_MSG", "REGISTER", "DEREGISTER", "ACK_REG", "ACK_DEREG",
    "ACK_CHAT_MSG"
]


def msg_type(typ):
    return typ_to_str[typ]


def msg_id():
    return str(uuid.uuid4())


def make(typ, content=""):
    return f"{typ}{delim}{content}".encode()


def parse(msg):
    decoded = msg.decode()
    [typ, content] = decoded.split(delim, 1)

    return int(typ), content
