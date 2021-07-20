import io
import pathlib
from datetime import datetime
from re import S
from typing import Union, Optional
import asyncio
import json
from random import randrange
import hashlib
import urllib
import urllib.parse
import struct
import socket

import aiohttp

from .bcode import bdecode, bencode

#   announce
#   announce_list
#   comment
#   created_by
#   creation_date
#   info
#   locale
#   title
#   url_list


class TorrentFileInfo:
    def __init__(self, info):
        self.crc32 = info.get(b"crc32")
        self.length = info.get(b"length")
        self.md5 = info.get(b"md5")
        self.mtime = info.get(b"mtime")
        self.path = info.get(b"path")
        self.sha1 = info.get(b"sha1")


class TorrentInfo:

    MULTI_FILE_MODE = 1
    SINGLE_FILE_MODE = 2

    def __init__(self, info):

        self.length = info.get(b"length")
        self.name = info.get(b"name")
        self.pieces = info.get(b"pieces")
        self.piece_length = info.get(b"piece length")

        self.files = [TorrentFileInfo(x) for x in info.get(b"files", [])]
        self.mode = TorrentInfo.MULTI_FILE_MODE if self.files else TorrentInfo.SINGLE_FILE_MODE

        self.collections = info.get(b"collections")

        self._raw_data = info


class TrackerResponse:
    def __init__(self, data):
        self._decoded_data = data

        self._failure_reason = self._decoded_data.get(b"failure reason")
        self._warning_message = self._decoded_data.get(b"warning message")
        self._interval = self._decoded_data.get(b"interval")
        self._min_interval = self._decoded_data.get(b"min interval")
        self._tracker_id = self._decoded_data.get(b"tracker id")
        self._complete = self._decoded_data.get(b"complete")
        self._incomplete = self._decoded_data.get(b"incomplete")
        self._peers = self._decoded_data.get(b"peers")

    @property
    def failure_reason(self):
        if self._failure_reason:
            return self._failure_reason.encode()

    @property
    def warning_message(self):
        if self._warning_message:
            return self._warning_message.encode()

    @property
    def peers(self):
        if type(self._peers) == bytes:
            data = [self._peers[i : i + 6] for i in range(0, len(self._peers), 6)]

            def _decode_port(bts):
                return struct.unpack(">H", bts)[0]

            return [(socket.inet_ntoa(d[:4]), _decode_port(d[4:])) for d in data]

    @property
    def interval(self):
        if self._interval:
            return self._interval


class TrackerConnectionProxy:
    def __init__(self, client, torrent, peer_id):
        self.client = client
        self.torrent = torrent
        self.peer_id = peer_id

    async def __aenter__(self) -> TrackerResponse:

        params = {
            "info_hash": self.torrent.info_hash,
            "peer_id": self.peer_id,
            "port": 51413,
            "uploaded": 0,
            "downloaded": 0,
            "left": self.torrent.total_size,
            "compact": 1,
            "event": "started",
        }

        tracker_url = self.torrent.tracker_url + "?" + urllib.parse.urlencode(params)
        print("conencting to", tracker_url)
        async with self.client.get(tracker_url) as response:
            if response.status != 200:
                raise ConnectionError()

            data = await response.read()
            return TrackerResponse(bdecode(data))

    async def __aexit__(self, *args, **kwargs):
        await self.client.__aexit__(*args, **kwargs)


class Tracker:
    def __init__(self, torrent, client=None):
        self.torrent = torrent
        self._client = client or aiohttp.ClientSession()
        self.peer_id = "-PT9000-t3qn65w1qoni"

    def connect(self) -> TrackerConnectionProxy:

        return TrackerConnectionProxy(self._client, self.torrent, self.peer_id)


class Torrent:
    def __init__(self, file_handle_or_path: Union[str, pathlib.Path, io.RawIOBase]):

        if isinstance(file_handle_or_path, str):
            file_handle_or_path = pathlib.Path(file_handle_or_path)

        if isinstance(file_handle_or_path, pathlib.Path):
            with open(file_handle_or_path, "rb") as file_handle:
                data = bdecode(file_handle.read())

        elif isinstance(file_handle_or_path, io.BufferedIOBase) or hasattr(
            file_handle_or_path, "read"
        ):
            data = bdecode(file_handle_or_path.read())

        else:
            raise ValueError

        self.announce = data[b"announce"].decode()
        self.announce_list = [x[0] for x in data.get(b"announce-list", [[]])]
        if not self.announce_list:
            self.announce_list = [self.announce]
        self.comment = data.get(b"comment", b"").decode()
        self.created_by = data.get(b"created by", b"").decode()
        self.creation_date = datetime.utcfromtimestamp(data.get(b"creation date", 0))
        self.info = TorrentInfo(data[b"info"])
        self.locale = data.get(b"locale", b"").decode()
        self.title = data.get(b"title", b"").decode()
        self.url_list = [x.decode() for x in data.get(b"url-list", [])]

        self._raw_data = data

        self.tracker_url = self.announce
        self.info_hash = hashlib.sha1(bencode(self.info._raw_data)).digest()
        self.downloaded = 0
        self.peer_id = "-PT9000-t3qn65w1qoni"
        self.port = 51413
        self.total_size = self.info.length or sum([file.length for file in self.info.files])

        self.peers = None

    def get_params(self):
        return {
            "info_hash": urllib.parse.quote(self.info_hash),
            "peer_id": urllib.parse.quote(self.peer_id),
            "port": self.port,
            "event": "started",
            "downloaded": self.downloaded,
            "uploaded": 0,
            "left": self.left,
        }
