from __future__ import annotations

import argparse

import uvicorn

from backend.app.core.config import Settings, load_settings


def browser_url(settings: Settings) -> str:
    host = settings.host
    if host == "0.0.0.0":
        host = "127.0.0.1"
    elif host in {"::", "[::]"}:
        host = "::1"
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    return f"http://{host}:{settings.port}"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="啟動 FinPilot R2 後端")
    parser.add_argument("--print-url", action="store_true", help="只輸出依目前設定解析的本機網址")
    args = parser.parse_args(argv)
    settings = load_settings()
    if args.print_url:
        print(browser_url(settings))
        return
    uvicorn.run(
        "backend.app.main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
        reload=False,
    )


if __name__ == "__main__":
    main()
