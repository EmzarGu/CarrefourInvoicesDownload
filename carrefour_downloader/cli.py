"""Command line interface for Carrefour invoice downloader."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from .core import CarrefourDownloader, DateRange

LOGGER = logging.getLogger(__name__)


def parse_date(value: str) -> date:
    """Parse a date provided on the command line.

    The command line uses the DD/MM/YYYY format to align with the dates displayed on
    the Carrefour website.
    """

    try:
        return datetime.strptime(value, "%d/%m/%Y").date()
    except ValueError as exc:  # pragma: no cover - user input validation
        msg = f"{value!r} is not a valid date (expected DD/MM/YYYY)."
        raise argparse.ArgumentTypeError(msg) from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download Carrefour invoices")
    parser.add_argument("email", help="Carrefour account email address")
    parser.add_argument("password", help="Carrefour account password")
    parser.add_argument(
        "start",
        type=parse_date,
        help="Start date of the range to download (DD/MM/YYYY)",
    )
    parser.add_argument(
        "end",
        type=parse_date,
        help="End date of the range to download (DD/MM/YYYY)",
    )
    parser.add_argument(
        "--download-dir",
        type=Path,
        default=Path(os.environ.get("CARREFOUR_DOWNLOAD_DIR", "downloads")),
        help="Directory where invoices will be saved",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run the browser in headless mode (default: headed)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    return parser


def configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    )


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(args.verbose)

    downloader = CarrefourDownloader(
        email=args.email,
        password=args.password,
        date_range=DateRange(start=args.start, end=args.end),
        download_dir=args.download_dir,
        headless=args.headless,
    )

    try:
        asyncio.run(downloader.run())
    except KeyboardInterrupt:  # pragma: no cover - user triggered
        LOGGER.warning("Interrupted by user")
        return 1
    except Exception:  # pragma: no cover - top level logging
        LOGGER.exception("Unexpected error during download")
        return 1

    return 0


if __name__ == "__main__":  # pragma: no cover - script entry point
    raise SystemExit(main())
