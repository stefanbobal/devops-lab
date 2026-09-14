import os
from dataclasses import dataclass

from playwright.async_api import async_playwright


@dataclass
class SAPSession:
    playwright: object
    browser: object
    context: object

    async def close(self):
        await self.context.close()
        await self.browser.close()
        await self.playwright.stop()


async def login_to_sap_for_me():
    username = os.environ["SAP_FOR_ME_USER"]
    password = os.environ["SAP_FOR_ME_PASSWORD"]

    headless = os.getenv(
        "SAP_FOR_ME_HEADLESS",
        "true"
    ).lower() != "false"

    p = await async_playwright().start()

    browser = await p.chromium.launch(
        headless=headless
    )

    context = await browser.new_context()
    page = await context.new_page()

    await page.goto(
        "https://me.sap.com/",
        wait_until="domcontentloaded",
        timeout=120000,
    )

    await page.wait_for_timeout(2000)

    print("Triggering SAP login...")

    await page.goto(
        "https://me.sap.com/backend/raw/core/User?login=true",
        wait_until="domcontentloaded",
        timeout=120000,
    )

    await page.wait_for_timeout(3000)

    print("Login URL:", page.url)
    print("Login title:", await page.title())

    username_selectors = [
        'input[type="email"]',
        'input[name="j_username"]',
        'input[name="username"]',
        '#j_username',
    ]

    password_selectors = [
        'input[type="password"]',
        'input[name="j_password"]',
        'input[name="password"]',
        '#j_password',
    ]

    async def find_visible(selectors):
        for selector in selectors:
            locator = page.locator(selector).first

            try:
                if await locator.is_visible(timeout=1500):
                    return locator
            except Exception:
                pass

        return None

    user_input = await find_visible(
        username_selectors
    )

    if not user_input:
        raise RuntimeError(
            "Username field not found."
        )

    await user_input.fill(username)

    password_input = await find_visible(
        password_selectors
    )

    if not password_input:
        for selector in [
            'button:has-text("Next")',
            'button:has-text("Continue")',
            'button[type="submit"]',
        ]:
            try:
                button = page.locator(selector).first

                if await button.is_visible(timeout=1000):
                    await button.click()
                    break
            except Exception:
                pass

        password_input = await find_visible(
            password_selectors
        )

    if not password_input:
        raise RuntimeError(
            "Password field not found."
        )

    await password_input.fill(password)
    await password_input.press("Enter")

    await page.wait_for_url(
        "**me.sap.com/**",
        timeout=120000
    )

    return SAPSession(
        p,
        browser,
        context
    )
