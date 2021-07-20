import asyncio
from asyncio.exceptions import CancelledError
import hashlib
import platform
from pytorrent.torrent import TrackerResponse
import signal
from argparse import ArgumentParser
from typing import Optional, List
import logging
import time
import struct
import bitstring

import aiohttp

from pytorrent import Torrent, bdecode, bencode, Tracker, PeerConnection, PieceManager


def create_parser() -> ArgumentParser:
    parser = ArgumentParser()
    parser.add_argument("file")
    parser.add_argument("-v", "--verbose", action="store_true", default=False)
    parser.add_argument("--debug", action="store_true", default=False)

    return parser


MAX_PEER_CONNECTIONS = 2  # 30


class Manager:
    def __init__(self):
        self.torrent_files: List[Torrent] = []
        self.should_continue = True
        self.abort = False

        self.available_peers = asyncio.Queue()
        self.peers = []
        self.piece_manager = PieceManager()

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

    async def run(self):
        self.http_session = aiohttp.ClientSession()
        torrent = self.torrent_files[0]
        tracker = Tracker(torrent, self.http_session)

        self.peers = [
            PeerConnection(
                self.available_peers,
                torrent.info_hash,
                tracker.peer_id,
                self.piece_manager,
                self.loop,
                self.http_session,
            )
            for _ in range(MAX_PEER_CONNECTIONS)
        ]

        previous = None
        interval = 30 * 60
        while True:

            current = time.time()

            if (not previous) or (previous + interval < current):
                async with Tracker(torrent, self.http_session).connect() as tracker_response:

                    if failed_reason := tracker_response.failure_reason:
                        logging.error(failed_reason)
                        continue

                    if warning_message := tracker_response.warning_message:
                        logging.warning(warning_message)

                    if tracker_response.peers:
                        logging.info("Got %d peers", len(tracker_response.peers))
                        previous = current
                        interval = tracker_response.interval
                        self._empty_queue()
                        for peer in tracker_response.peers:
                            self.available_peers.put_nowait(peer)

            else:
                logging.debug("sleeping...")
                await asyncio.sleep(5)

    def _empty_queue(self):
        while not self.available_peers.empty():
            self.available_peers.get_nowait()

    def start(self):
        assert len(self.torrent_files) == 1

        self.loop.create_task(self.run())
        self.loop.run_forever()


def main():
    print("Start")

    args = create_parser().parse_args()

    manager = Manager()
    with open(args.file, "rb") as f:
        manager.load_file(Torrent(f))

    if args.verbose:
        logging.basicConfig(level=logging.INFO)

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)

    def on_sigint(_sig_nb, _frame):
        print("Stopping the loop")
        manager.loop.stop()
        manager.stop()

    signal.signal(signal.SIGINT, on_sigint)

    manager.start()


if __name__ == "__main__":
    main()
