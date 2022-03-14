import sys

from .constant import *
from .log import logger
from .parse import *
from .server import Server
from .client import Client


def main():
    args = sys.argv[1:]
    mode = args[0]

    if mode == SERVER_MODE:
        port = parse_server_args(args)
        logger.info(f"server mode, args: {port}")

        # pass control to Server object
        Server(port).start()
    elif mode == CLIENT_MODE:
        name, ip, sport, cport = parse_client_args(args)
        logger.info(f"client mode, args: {name}, {ip}, {sport}, {cport}")

        # pass control to Client object
        Client(name, ip, sport, cport).start()
    else:
        logger.critical(
            f"mode {mode} unrecognized: -s (server) or (-c) client")


if __name__ == "__main__":
    main()
