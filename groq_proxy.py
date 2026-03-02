"""Simple reverse proxy for Groq API to bypass IP restrictions."""

import asyncio
import logging

import aiohttp
from aiohttp import web

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

GROQ_BASE = "https://api.groq.com"
LISTEN_PORT = 8990


async def proxy_handler(request: web.Request) -> web.Response:
    """Forward request to Groq API."""
    target_url = f"{GROQ_BASE}{request.path_qs}"
    headers = dict(request.headers)
    headers.pop("Host", None)

    body = await request.read()
    logger.info(f"Proxy: {request.method} {request.path}")

    async with aiohttp.ClientSession() as session:
        async with session.request(
            method=request.method,
            url=target_url,
            headers=headers,
            data=body,
        ) as resp:
            response_body = await resp.read()
            return web.Response(
                status=resp.status,
                body=response_body,
                content_type=resp.content_type,
            )


app = web.Application()
app.router.add_route("*", "/{path:.*}", proxy_handler)

if __name__ == "__main__":
    logger.info(f"Starting Groq proxy on port {LISTEN_PORT}")
    web.run_app(app, host="0.0.0.0", port=LISTEN_PORT)
