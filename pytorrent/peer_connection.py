import asyncio
from asyncio.exceptions import CancelledError
import hashlib
import platform
from re import A
from pytorrent.torrent import TrackerResponse
import signal
from argparse import ArgumentParser
from typing import Optional, List
import logging
import time
import struct
import bitstring

import aiohttp


class PieceManager:
    def __init__(self):
        pass


class ProtocolError(BaseException):
    pass


REQUEST_SIZE = 2 ** 14


class PeerMessage:

    Choke = 0
    UnChoke = 1
    Interested = 2
    NotInterested = 3
    Have = 4
    BitField = 5
    Request = 6
    Piece = 7
    Cancel = 8
    Port = 9
    KeepAlive = None
    Handshake = None

    length: int

    def encode(self) -> bytes:
        pass

    @classmethod
    def decode(cls, data: bytes):
        pass

    def __str__(self):
        return self.__class__.__name__


class Handshake(PeerMessage):
    length = 49 + 19

    def __init__(self, info_hash, peer_id):

        if isinstance(info_hash, str):
            info_hash = info_hash.encode()

        if isinstance(peer_id, str):
            peer_id = peer_id.encode()

        self.info_hash = info_hash
        self.peer_id = peer_id

    def encode(self):
        """
        <pstrlen><pstr><reserved><info_hash><peer_id>
        """
        return struct.pack(
            ">B19s8x20s20s", 19, b"BitTorrent protocol", self.info_hash, self.peer_id
        )

    @classmethod
    def decode(cls, data: bytes):
        logging.debug("Decoding handshake of length %d", len(data))

        if len(data) < Handshake.length:
            return None

        parts = struct.unpack(">B19s8x20s20s", data)
        hash_info = parts[2]
        peer_id = parts[3]

        return cls(hash_info, peer_id)


class KeepAlive(PeerMessage):
    pass


class Choke(PeerMessage):
    pass


class UnChoke(PeerMessage):
    pass


class Interested(PeerMessage):
    length = 1

    def encode(self):
        return struct.pack(">Ib", Interested.length, PeerMessage.Interested)


class NotInterested(PeerMessage):
    pass


class Have(PeerMessage):
    def __init__(self, index: int):
        self.index = index

    def encode(self):
        return struct.pack(">IbI", 5, PeerMessage.Have, self.index)

    @classmethod
    def decode(cls, data: bytes):
        index = struct.unpack(">IbI", data)[2]
        return cls(index)


class BitField(PeerMessage):
    def __init__(self, data):
        self.bitfield = bitstring.BitArray(bytes=data)

    def encode(self):
        length = len(self.bitfield)
        return struct.pack(
            ">Ib" + str(length) + "s", 1 + length, PeerMessage.BitField, self.bitfield
        )

    @classmethod
    def decode(cls, data: bytes):
        message_length = struct.unpack(">I", data[0:4])[0]
        parts = struct.unpack(">Ib" + str(message_length - 1) + "s", data)
        return cls(parts[2])


class Request(PeerMessage):
    def __init__(self, index: int, begin: int, length: int = REQUEST_SIZE):
        self.index = index
        self.begin = begin
        self.length = length

    def encode(self):
        return struct.pack(">IbIII", 13, PeerMessage.Request, self.index, self.begin, self.length)

    @classmethod
    def decode(cls, data: bytes):

        parts = struct.unpack(">IbIII", data)
        return cls(parts[2], parts[3], parts[4])


class Piece(PeerMessage):
    length: int = 9

    def __init__(self, index: int, begin: int, data: bytes):
        self.index = index
        self.begin = begin
        self.data = data

    def encode(self):
        message_length = Piece.length + len(self.data)
        return struct.pack(
            ">IbII" + str(len(self.data)) + "s",
            message_length,
            PeerMessage.Piece,
            self.indx,
            self.begin,
            self.data,
        )

    @classmethod
    def decode(cls, data: bytes):
        message_length = struct.unpack(">I", data[0:4])[0]
        parts = struct.unpack(">IbII" + str(message_length - Piece.length) + "s", data)
        return cls(parts[2], parts[3], parts[4])


class Cancel(PeerMessage):
    def __init__(self, index: int, begin: int, length: int = REQUEST_SIZE):
        self.index = index
        self.begin = begin
        self.length = length

    def encode(self):
        return struct.pack(">IbIII", 13, PeerMessage.Cancel, self.index, self.begin, self.length)

    @classmethod
    def decode(cls, data: bytes):

        parts = struct.unpack(">IbIII", data)
        return cls(parts[2], parts[3], parts[4])


class Port(PeerMessage):
    def __init__(self):
        pass

    def encode():
        pass

    @classmethod
    def decode(cls, data: bytes):
        pass


class PeerConnection:
    def __init__(
        self,
        queue: asyncio.Queue,
        info_hash: bytes,
        peer_id: str,
        piece_manager: PieceManager,
        loop: asyncio.BaseEventLoop,
        session: aiohttp.ClientSession,
    ):
        self.loop = loop
        self.session = session
        self.states = []
        self.peer_states = []

        self.reader: asyncio.StreamReader = None
        self.writer: asyncio.StreamWriter = None

        self.piece_manager = piece_manager
        self.peer_id = peer_id
        self.info_hash = info_hash
        self.queue = queue

        self.future = asyncio.ensure_future(self._start(), loop=self.loop)

    async def _start(self):

        while "stopped" not in self.states:
            ip, port = await self.queue.get()
            logging.info("Got assigned peer with: %s:%d", ip, port)

            try:

                self.reader, self.writer = await asyncio.open_connection(ip, port)
                logging.info("connection opened to %s:%d", ip, port)

                buffer = await self._handshake()

                self.states.append("choked")
                await self._send_interested()
                self.states.append("interested")

                async for message in PeerStreamIterator(self.reader, buffer):
                    if "stopped" in self.states:
                        break

                    logging.debug("Got message %s", message)

            except Exception as e:
                self.stop()
                raise e

    def stop(self):
        self.states.append("stopped")
        if not self.future.done():
            self.future.cancel()

    async def _handshake(self):
        self.writer.write(Handshake(self.info_hash, self.peer_id).encode())
        await self.writer.drain()

        tries = 1
        buffer = b""
        while len(buffer) < Handshake.length and tries < 10:
            tries += 1
            buffer = await self.reader.read(PeerStreamIterator.CHUNK_SIZE)

        response = Handshake.decode(buffer[: Handshake.length])
        if not response:
            raise ProtocolError("Unable receive and parse a handshake")
        if not response.info_hash == self.info_hash:
            raise ProtocolError("Handshake with invalid info_hash")

        self.remote_id = response.peer_id
        logging.info("Handshake with peer '%s' was successful", self.remote_id.decode())

        return buffer[Handshake.length :]

    async def _send_interested(self):

        logging.debug("Sending interested")
        self.writer.write(Interested().encode())
        await self.writer.drain()
        logging.debug("Sent interested")


class PeerStreamIterator:

    CHUNK_SIZE = 10 * 1024

    def __init__(self, reader: asyncio.StreamReader, buffer: bytes):
        self.reader = reader
        self.buffer = buffer or b""

    def __aiter__(self):
        return self

    async def __anext__(self):

        while True:
            try:
                data = await self.reader.read(PeerStreamIterator.CHUNK_SIZE)
                logging.debug("Got %d bytes of data", len(data))
                if data:
                    self.buffer += data
                    if message := self.parse():
                        return message
                else:
                    if self.buffer:
                        logging.debug("No data read from stream.")
                        if message := self.parse():
                            return message

                    raise StopAsyncIteration()

            except ConnectionResetError:
                logging.debug("Connection closed by peer")
                raise StopAsyncIteration()

            except CancelledError:
                raise StopAsyncIteration()

            except StopAsyncIteration:
                raise

            except Exception as e:
                logging.critical("Error when iterating over stream!")
                logging.critical(e)
                raise StopAsyncIteration()

    def parse(self):
        header_length = 4
        if len(self.buffer) > 4:
            logging.debug("buffer: %s", self.buffer.hex())
            message_length = struct.unpack(">I", self.buffer[0:4])[0]

            if message_length == 0:
                return KeepAlive()

            if len(self.buffer) >= message_length:
                message_id = struct.unpack(">b", self.buffer[4:5])[0]

                logging.debug("Got message with id=%d", message_id)

                def _consume():
                    self.buffer = self.buffer[header_length + message_length :]

                def _data():
                    return self.buffer[: header_length + message_length]

                if message_id == PeerMessage.Choke:
                    _consume()
                    return Choke()
                elif message_id == PeerMessage.UnChoke:
                    _consume()
                    return UnChoke()
                elif message_id == PeerMessage.Interested:
                    _consume()
                    return Interested()
                elif message_id == PeerMessage.NotInterested:
                    _consume()
                    return NotInterested()
                elif message_id == PeerMessage.Have:
                    data = _data()
                    _consume()
                    return Have.decode(data)
                elif message_id == PeerMessage.BitField:
                    data = _data()
                    _consume()
                    return BitField.decode(data)
                elif message_id == PeerMessage.Request:
                    data = _data()
                    _consume()
                    return Request.decode(data)
                elif message_id == PeerMessage.Piece:
                    data = _data()
                    _consume()
                    return Piece.decode(data)
                elif message_id == PeerMessage.Cancel:
                    data = _data()
                    _consume()
                    return Cancel.decode(data)
                else:
                    logging.info("Unsupported message")
            else:
                logging.debug("Not enough in buffer in order to parse")
        return None
