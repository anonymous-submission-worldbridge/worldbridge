#!/usr/bin/env python3
"""Serve the connect2 gallery, including byte-range requests for MP4 seeking."""

import argparse
from pathlib import Path

from aiohttp import web


ROOT = (
    Path(__file__).resolve().parents[1]
    / "infinigen/outputs/outdoor_full_demo/urban_v1_full_connect2"
)


async def index(request):
    return web.FileResponse(ROOT / "index.html")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", choices=["127.0.0.1"], default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18765)
    args = parser.parse_args()
    if not (ROOT / "index.html").is_file():
        parser.error(f"Missing gallery: {ROOT / 'index.html'}")
    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_static("/", ROOT, show_index=False)
    # on_startup runs before the listening socket is ready; print via run_app
    # after binding so VS Code's background task matcher can rely on it.
    web.run_app(
        app,
        host=args.host,
        port=args.port,
        print=lambda _: print(
            f"Connect2 preview ready: http://127.0.0.1:{args.port}/", flush=True
        ),
    )


if __name__ == "__main__":
    main()
