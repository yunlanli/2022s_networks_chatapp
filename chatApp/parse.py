import sys

from .log import logger
from .constant import *


def usage(mode, exit=True):
    if mode == SERVER_MODE:
        print("Usage: ChatApp -s <port>")
    elif mode == SERVER_MODE:
        print(
            "Usage: ChatApp -c <name> <server-ip> <server-port> <client-port>")

    if exit:
        sys.exit(1)


def parse_port(port, exit=True):
    pno = int(port)

    if pno < 1024 or pno > 65535:
        logger.error(f"invalid port #: {pno}")
        pno = -1

        if exit: sys.exit(1)

    return pno


def parse_server_args(args):
    if len(args) != 2:
        logger.critical(f"expect 1 server arg, got {len(args)-1}")
        usage(args[0])

    return parse_port(args[1])


def parse_client_args(args):
    if len(args) != 5:
        logger.critical(f"expect 4 client args, got {len(args)-1}")
        usage(args[0])

    cname = args[1]
    server_ip = args[2]
    server_port = parse_port(args[3])
    client_port = parse_port(args[4])

    return cname, server_ip, server_port, client_port
