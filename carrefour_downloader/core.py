"""Core Playwright automation logic for downloading Carrefour invoices."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from playwright.async_api import Browser, Download, Locator, Page, async_playwright

LOGGER = logging.getLogger(__name__)

RECEIPT_ITEM = "li[data-testid=\"receipt-list-item\"].receipt-list-item"
RECEIPT_DATE = "span.order-item_date"
RECEIPT_DOWNLOAD_BUTTON = (
    "button.receipt-list-item__button.pl-button.pl-button--tone-main.pl-button--variation-tertiary"
)
LOAD_MORE_BUTTON = (
    "button.pl-button.pl-button--tone-main.pl-button--variation-tertiary"
)
LOAD_MORE_TEXT = "Voir plus d'achats magasin"
LOGIN_URL = "https://www.carrefour.fr/mon-compte/mes-achats"
DATE_PATTERN = re.compile(r"(\d{2})/(\d{2})/(\d{2,4})")


@dataclass(frozen=True)
class DateRange:
    """Inclusive date range used to filter receipts."""

    start: date
    end: date

    def contains(self, candidate: date) -> bool:
        return self.start <= candidate <= self.end


class CarrefourDownloader:
    """Download Carrefour invoices within a specified date range."""

    def __init__(
        self,
        *,
        email: str,
        password: str,
        date_range: DateRange,
        download_dir: Path,
        headless: bool = False,
    ) -> None:
        self.email = email
        self.password = password
        self.date_range = date_range
        self.download_dir = download_dir
        self.headless = headless

        self._browser: Browser | None = None
        self._page: Page | None = None
        self._processed_receipts: set[str] = set()

    async def run(self) -> None:
        """Entry point for executing the download workflow."""

        self.download_dir.mkdir(parents=True, exist_ok=True)

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=self.headless)
            self._browser = browser
            context = await browser.new_context(accept_downloads=True)
            self._page = await context.new_page()

            await self._login()
            await self._process_receipts()

            await context.close()
            await browser.close()

    async def _login(self) -> None:
        assert self._page is not None
        page = self._page

        LOGGER.info("Navigating to Carrefour login page")
        await page.goto(LOGIN_URL)

        # Carrefour uses a single page application for login; handle cookie banners
        await self._accept_cookies_if_present()

        LOGGER.info("Filling in credentials")
        await page.wait_for_selector("input[name='email']")
        await page.fill("input[name='email']", self.email)
        await page.fill("input[name='password']", self.password)
        await page.click("button[type='submit']")

        LOGGER.debug("Waiting for purchase history to load")
        await page.wait_for_selector(RECEIPT_ITEM)

    async def _accept_cookies_if_present(self) -> None:
        assert self._page is not None
        page = self._page

        try:
            await page.wait_for_selector("button[id='onetrust-accept-btn-handler']", timeout=5000)
        except Exception:
            return
        else:
            LOGGER.info("Accepting cookie banner")
            await page.click("button[id='onetrust-accept-btn-handler']")
            await page.wait_for_timeout(500)

    async def _process_receipts(self) -> None:
        assert self._page is not None
        page = self._page

        processed = 0
        while True:
            receipts = page.locator(RECEIPT_ITEM)
            count = await receipts.count()
            LOGGER.debug("Found %s receipts on the page", count)

            for index in range(processed, count):
                receipt = receipts.nth(index)
                await self._handle_receipt(receipt)

            processed = count

            if not await self._load_more_receipts():
                break

    async def _handle_receipt(self, receipt: Locator) -> None:
        assert self._page is not None
        page = self._page

        receipt_id = await self._receipt_identifier(receipt)
        if receipt_id in self._processed_receipts:
            LOGGER.debug("Skipping already processed receipt %s", receipt_id)
            return

        try:
            receipt_date_text = await receipt.locator(RECEIPT_DATE).inner_text()
        except Exception:
            LOGGER.exception("Receipt %s is missing its date element", receipt_id)
            return

        receipt_date = self._parse_date(receipt_date_text)
        if receipt_date is None:
            LOGGER.warning("Could not parse receipt date from %s", receipt_date_text)
            return

        if not self.date_range.contains(receipt_date):
            LOGGER.debug("Receipt %s is outside the target range", receipt_id)
            return

        LOGGER.info("Downloading receipt %s (%s)", receipt_id, receipt_date)
        button = receipt.locator(RECEIPT_DOWNLOAD_BUTTON)
        if await button.count() == 0:
            LOGGER.warning("Receipt %s has no download button", receipt_id)
            return
        try:
            async with page.expect_download() as download_info:
                await button.click()
            download = await download_info.value
        except Exception:
            LOGGER.exception("Failed to trigger download for receipt %s", receipt_id)
            return

        await self._save_download(download, receipt_date, receipt_id)
        self._processed_receipts.add(receipt_id)

    async def _save_download(self, download: Download, receipt_date: date, receipt_id: str) -> None:
        filename = download.suggested_filename
        extension = Path(filename).suffix or ".pdf"
        dated_folder = self.download_dir / f"{receipt_date.year:04d}" / f"{receipt_date.month:02d}"
        dated_folder.mkdir(parents=True, exist_ok=True)

        safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", receipt_id)
        destination = dated_folder / f"{receipt_date.isoformat()}_{safe_id}{extension}"

        LOGGER.debug("Saving download to %s", destination)
        await download.save_as(destination)

    async def _load_more_receipts(self) -> bool:
        assert self._page is not None
        page = self._page

        button = page.locator(LOAD_MORE_BUTTON, has_text=LOAD_MORE_TEXT)
        if await button.count() == 0:
            LOGGER.debug("No more receipts to load")
            return False

        LOGGER.info("Loading more receipts")
        await button.first.click()
        await page.wait_for_timeout(1500)
        return True

    async def _receipt_identifier(self, receipt: Locator) -> str:
        text = await receipt.inner_text()
        hash_source = re.sub(r"\s+", " ", text.strip())
        return hash_source[:120]

    def _parse_date(self, value: str) -> date | None:
        match = DATE_PATTERN.search(value)
        if not match:
            return None

        day, month, year = match.groups()
        year = int(year)
        if year < 100:
            year += 2000
        try:
            return date(year=int(year), month=int(month), day=int(day))
        except ValueError:
            return None
