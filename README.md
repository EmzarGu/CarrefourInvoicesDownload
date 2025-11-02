# Carrefour Invoices Downloader

Automation toolkit that signs in to the Carrefour "Mes achats" portal and downloads
receipts for a given date range. The project uses [Playwright](https://playwright.dev)
and provides a small CLI wrapper.

## Prerequisites

* Python 3.10+
* `pipx` or `pip` for installing dependencies
* Playwright browsers (install via `playwright install` after dependency setup)

## Installation

```bash
pip install -e .
playwright install
```

## Usage

```bash
carrefour-download EMAIL PASSWORD START_DATE END_DATE [--download-dir PATH] [--headless] [--verbose]
```

* Dates must be passed using the `DD/MM/YYYY` format.
* Downloaded files are stored in the chosen directory with sub-folders per year and month.
* Use `--headless` to run without a visible browser window.

## Development

Run the CLI directly without installation:

```bash
python -m carrefour_downloader.cli EMAIL PASSWORD 01/01/2024 31/01/2024 --verbose
```

The Playwright automation is implemented in
[`carrefour_downloader/core.py`](carrefour_downloader/core.py).
