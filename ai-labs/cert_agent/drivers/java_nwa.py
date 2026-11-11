"""SAP Java driver: drives the NetWeaver Administrator key storage page with Playwright.

NOT VERIFIED AGAINST A REAL SYSTEM. The page address, the logon field names and the
button texts in the constants below are written from memory of NWA 7.5. On the first
run set `headless: false` in the inventory, watch the browser and correct the
constants. Every step saves a screenshot, which ends up on the Jira ticket.

A certificate id is "<key storage view>/<entry>", for example
"ICM_SSL_12345/ssl-credentials". The current certificate is read from the TLS
endpoint in the inventory, so no screen scraping is needed for discovery.
"""
from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from cryptography import x509

from .. import certcheck
from ..log import step
from .base import Driver, DriverError

KEY_STORAGE_PATH = "/nwa/key-storage"
USER_FIELD = 'input[name="j_username"]'
PASSWORD_FIELD = 'input[name="j_password"]'
LOGON_BUTTON = '[name="uidPasswordLogon"]'
GENERATE_CSR = "Generate CSR Request"
IMPORT_RESPONSE = "Import CSR Response"
ADD_FILE = "Add"
IMPORT_CONFIRM = "Import"
FILE_INPUT = 'input[type="file"]'
STEP_TIMEOUT_MS = 60_000


class JavaNwaDriver(Driver):
    key_reuse = True  # the CSR is generated for the existing key pair entry

    def __init__(self, target, settings):
        super().__init__(target, settings)
        self.options = target.options.get("nwa") or {}
        for name in ("base_url", "user", "password_env"):
            if not self.options.get(name):
                raise DriverError(f"{target.name}: nwa.{name} is missing in the inventory")
        self._shots = 0

    def _shot(self, page, name: str) -> None:
        self._shots += 1
        folder = Path(self.settings.work_dir) / "screenshots" / self.target.name
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{datetime.now():%Y%m%d-%H%M%S}_{self._shots:02d}_{name}.png"
        page.screenshot(path=str(path), full_page=True)
        self.evidence.append(path)
        step(f"{self.target.name}: screenshot {path.name}")

    @contextmanager
    def _page(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise DriverError("the java_nwa driver needs the playwright library") from exc
        password = os.environ.get(self.options["password_env"])
        if not password:
            raise DriverError(f"{self.target.name}: environment variable {self.options['password_env']} is not set")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=bool(self.options.get("headless", True)))
            context = browser.new_context(
                accept_downloads=True,
                # The server certificate is the one being renewed and may come from an internal CA.
                ignore_https_errors=bool(self.options.get("ignore_https_errors", False)),
            )
            context.set_default_timeout(STEP_TIMEOUT_MS)
            page = context.new_page()
            try:
                step(f"{self.target.name}: opening the NWA key storage page")
                page.goto(self.options["base_url"].rstrip("/") + KEY_STORAGE_PATH)
                page.fill(USER_FIELD, self.options["user"])
                page.fill(PASSWORD_FIELD, password)
                page.click(LOGON_BUTTON)
                page.wait_for_load_state("networkidle")
                self._shot(page, "logged-in")  # taken after the logon, so no password is on it
                yield page
            finally:
                context.close()
                browser.close()

    def _select_entry(self, page, cert_id: str) -> None:
        view, _, entry = cert_id.partition("/")
        if not view or not entry:
            raise DriverError(f"Java certificate id must be VIEW/ENTRY, got {cert_id!r}")
        self.target.cert(cert_id)
        step(f"{self.target.name}: selecting view {view}, entry {entry}")
        page.get_by_text(view, exact=True).first.click()
        page.wait_for_load_state("networkidle")
        page.get_by_text(entry, exact=True).first.click()
        page.wait_for_load_state("networkidle")
        self._shot(page, "entry-selected")

    def create_csr(self, cert_id: str) -> str:
        with self._page() as page:
            self._select_entry(page, cert_id)
            step(f"{self.target.name}: generating the CSR")
            with page.expect_download() as download:
                page.get_by_text(GENERATE_CSR, exact=True).first.click()
            csr = Path(download.value.path()).read_text()
            self._shot(page, "csr-generated")
        return csr

    def install(self, cert_id: str, leaf: x509.Certificate, chain: list[x509.Certificate]) -> None:
        with self._page() as page, tempfile.TemporaryDirectory() as folder:
            self._select_entry(page, cert_id)
            step(f"{self.target.name}: importing the CSR response ({1 + len(chain)} certificate(s))")
            page.get_by_text(IMPORT_RESPONSE, exact=True).first.click()
            for number, cert in enumerate([leaf, *chain]):  # own certificate first, then its issuers
                path = Path(folder) / f"{number:02d}.crt"
                path.write_text(certcheck.to_pem(cert))
                page.set_input_files(FILE_INPUT, str(path))
                page.get_by_text(ADD_FILE, exact=True).first.click()
                page.wait_for_load_state("networkidle")
            self._shot(page, "response-files-added")
            page.get_by_text(IMPORT_CONFIRM, exact=True).last.click()
            page.wait_for_load_state("networkidle")
            self._shot(page, "response-imported")
