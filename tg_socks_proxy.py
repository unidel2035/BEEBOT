"""Minimal async SOCKS5 proxy for Telegram Bot API access from VPS.

VPS cannot reach api.telegram.org directly (TLS timeout at hosting provider).
This proxy runs on hive (which HAS internet access), and is exposed to the VPS
via SSH reverse tunnel (see systemd/groq-tunnel.service).

Listen: localhost:9150 (SOCKS5, no auth)
Usage (bot side): set TG_SOCKS_PROXY=socks5://localhost:9150 in .env
"""

import asyncio
import logging
import struct

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

LISTEN_HOST = "127.0.0.1"
LISTEN_PORT = 9150


async def _pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while not reader.at_eof():
            data = await reader.read(65536)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except Exception:
        pass
    finally:
        try:
            writer.close()
        except Exception:
            pass


async def _handle(client_r: asyncio.StreamReader, client_w: asyncio.StreamWriter) -> None:
    try:
        # ── Greeting ──────────────────────────────────────────────────────────
        hdr = await client_r.read(2)
        if len(hdr) < 2 or hdr[0] != 0x05:
            return
        nmethods = hdr[1]
        await client_r.read(nmethods)          # skip auth method list
        client_w.write(b"\x05\x00")            # no-auth
        await client_w.drain()

        # ── Request ───────────────────────────────────────────────────────────
        req = await client_r.read(4)
        if len(req) < 4 or req[0] != 0x05 or req[1] != 0x01:  # only CONNECT
            client_w.write(b"\x05\x07\x00\x01" + b"\x00" * 6)
            await client_w.drain()
            return

        atyp = req[3]
        if atyp == 0x01:                       # IPv4
            raw = await client_r.read(4)
            host = ".".join(str(b) for b in raw)
        elif atyp == 0x03:                     # domain name
            alen = (await client_r.read(1))[0]
            host = (await client_r.read(alen)).decode()
        elif atyp == 0x04:                     # IPv6
            import socket
            raw = await client_r.read(16)
            host = socket.inet_ntop(socket.AF_INET6, raw)
        else:
            client_w.write(b"\x05\x08\x00\x01" + b"\x00" * 6)
            await client_w.drain()
            return

        port = struct.unpack("!H", await client_r.read(2))[0]

        # ── Connect to target ─────────────────────────────────────────────────
        try:
            remote_r, remote_w = await asyncio.open_connection(host, port)
        except Exception as e:
            logger.warning("Connect failed %s:%d — %s", host, port, e)
            client_w.write(b"\x05\x04\x00\x01" + b"\x00" * 6)
            await client_w.drain()
            return

        # ── Success ───────────────────────────────────────────────────────────
        client_w.write(b"\x05\x00\x00\x01" + b"\x00" * 4 + b"\x00\x00")
        await client_w.drain()

        logger.info("Tunnel: %s:%d", host, port)
        await asyncio.gather(
            _pipe(client_r, remote_w),
            _pipe(remote_r, client_w),
        )

    except Exception as e:
        logger.error("Handler error: %s", e)
    finally:
        try:
            client_w.close()
        except Exception:
            pass


async def main() -> None:
    server = await asyncio.start_server(_handle, LISTEN_HOST, LISTEN_PORT)
    logger.info("SOCKS5 proxy listening on %s:%d", LISTEN_HOST, LISTEN_PORT)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
