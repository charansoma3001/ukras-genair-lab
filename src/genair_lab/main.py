"""Launcher: ``genair`` starts the web server (the only entry point)."""

import argparse

import uvicorn


def main():
    parser = argparse.ArgumentParser(description="GenAIR Lab server")
    parser.add_argument(
        "--port", type=int, default=8001, help="Port for the web server"
    )
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to bind to")
    parser.add_argument(
        "--reload", action="store_true", help="Enable auto-reload (development)"
    )
    args = parser.parse_args()

    print(f"[*] Starting GenAIR Lab on http://localhost:{args.port}  (Ctrl-C to stop)")
    # The browser holds open MJPEG (/video_feed) and SSE (/events) streams. Without
    # a timeout, Ctrl-C waits forever for them to close, so force exit after 2s.
    uvicorn.run(
        "genair_lab.server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        timeout_graceful_shutdown=2,
    )


if __name__ == "__main__":
    main()
