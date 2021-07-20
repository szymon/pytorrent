import asyncio
import hashlib
import platform
import signal
from argparse import ArgumentParser
from typing import Optional, List
import logging
import time

import aiohttp

from pytorrent import Torrent, bdecode, bencode, Tracker


def create_parser() -> ArgumentParser:
    parser = ArgumentParser()
    parser.add_argument("file")

    return parser


class Manager:
    def __init__(self):
        self.torrent_files: List[Torrent] = []
        self.should_continue = True
        self.abort = False

        self.http_session: Optional[aiohttp.ClientSession]

        self.loop = asyncio.get_event_loop()

    def load_file(self, file):
        if isinstance(file, Torrent):
            self.torrent_files.append(file)
        else:
            self.torrent_files.append(Torrent(file))

    def stop(self):
        if not self.http_session.closed:
            self.loop.create_task(self.http_session.close())

    async def init(self):
        self.http_session = aiohttp.ClientSession()

        for torrent in self.torrent_files:

            async with Tracker(torrent).connect() as response:
                if failure_message := response.failure_reason:
                    logging.error(failure_message)

                if warning_message := response.warning_message:
                    logging.warning(warning_message)

                print(response.peers)

        while True:
            await asyncio.sleep(1)

    def start(self):
        assert len(self.torrent_files) == 1

        self.loop.create_task(self.init())
        self.loop.run_forever()


def main():
    print("Start")

    args = create_parser().parse_args()

    manager = Manager()
    with open(args.file, "rb") as f:
        manager.load_file(Torrent(f))

    def on_sigint(_sig_nb, _frame):
        print("Stopping the loop")
        manager.loop.stop()
        manager.stop()

    signal.signal(signal.SIGINT, on_sigint)

    manager.start()


if __name__ == "__main__":
    main()
