import socket

from .log import logger


class Client:

    def __init__(self,
                 username,
                 server_ip,
                 server_port,
                 client_port,
                 logger=logger):
        self.username = username
        self.server = server_ip
        self.sport = server_port
        self.port = client_port
        self.logger = logger

        self.logger.info(
            f"instantiated client {self.username} @ port {self.port} for server @ {self.server}:{self.sport}"
        )

    def get_message(self):
        while True:
            message = input('>>>')
            self.sock.sendto(message.encode(), (self.server, self.sport))
            self.logger.info(f"sending to {self.server}: {message}")

            resp, server_addr = self.sock.recvfrom(2048)
            print(f"from {server_addr}: {resp.decode()}")

    def stop(self):
        self.sock.close()
        self.logger.info(f"client {self.username} gracefully exited")

    def start(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((socket.gethostname(), self.port))

        self.logger.info(f"created UDP socket, bound to port {self.port}")

        try:
            self.get_message()
        except KeyboardInterrupt:
            self.logger.info("keyboard interrupt! exiting client...")
            self.stop()
