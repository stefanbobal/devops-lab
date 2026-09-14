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

    headless = (
        os.getenv("SAP_FOR_ME_HEADLESS", "true")
        .lower()
        != "false"
    )

    playwright = await async_playwright().start()

    browser = None
    page = None

    try:
        browser = await playwright.chromium.launch(
            headless=headless
        )

        context = await browser.new_context()
        page = await context.new_page()

        print("Opening SAP for Me...")

        await page.goto(
            "https://me.sap.com/",
            wait_until="domcontentloaded",
            timeout=120000,
        )

        await page.wait_for_timeout(2000)

        # Dismiss cookie banner if shown
        try:
            cookie_button = page.locator(
                "#truste-consent-button"
            ).first

            if await cookie_button.is_visible(
                timeout=5000
            ):
                print(
                    "Dismissing cookie consent banner..."
                )

                await cookie_button.click()

                await page.wait_for_timeout(1000)

        except Exception:
            pass

        # Instead of clicking Sign In, directly open /home.
        # The public Sign In link points there and SAP redirects
        # unauthenticated users to accounts.sap.com.
        print(
            "Opening authenticated SAP for Me home..."
        )

        await page.goto(
            "https://me.sap.com/home",
            wait_until="domcontentloaded",
            timeout=120000,
        )

        await page.wait_for_timeout(2000)

        print(
            "Post Sign-In URL:",
            page.url
        )

        print(
            "Post Sign-In title:",
            await page.title()
        )

        # SAP login page
        username_selectors = [
            'input[name="j_username"]',
            'input[type="email"]',
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
                locator = page.locator(
                    selector
                ).first

                try:
                    if await locator.is_visible(
                        timeout=2000
                    ):
                        print(
                            "Found selector:",
                            selector
                        )

                        return locator

                except Exception:
                    pass

            return None

        # Username
        user_input = await find_visible(
            username_selectors
        )

        if user_input is None:
            raise RuntimeError(
                "SAP username field not found."
            )

        print("Entering username...")

        await user_input.fill(
            username
        )

        # First Continue button
        continue_button = page.get_by_role(
            "button",
            name="Continue"
        ).first

        try:
            await continue_button.wait_for(
                state="visible",
                timeout=10000,
            )

            print(
                "Clicking first login step..."
            )

            await continue_button.click()

        except Exception:
            fallback = page.locator(
                'button[type="submit"]'
            ).first

            await fallback.click()

        await page.wait_for_timeout(
            1500
        )

        # Password
        password_input = await find_visible(
            password_selectors
        )

        if password_input is None:
            await page.wait_for_timeout(
                2000
            )

            password_input = (
                await find_visible(
                    password_selectors
                )
            )

        if password_input is None:
            raise RuntimeError(
                "SAP password field not found."
            )

        print("Entering password...")

        await password_input.fill(
            password
        )

        # Second Continue button
        continue_button = page.get_by_role(
            "button",
            name="Continue"
        ).first

        submitted = False

        try:
            await continue_button.wait_for(
                state="visible",
                timeout=10000,
            )

            print(
                "Submitting login..."
            )

            await continue_button.click()

            submitted = True

        except Exception:
            pass

        if not submitted:
            print(
                "Continue button not found; "
                "pressing Enter..."
            )

            await password_input.press(
                "Enter"
            )

        # Give SAP SSO a few seconds to redirect back
        await page.wait_for_timeout(5000)

        print("5s after submit URL:", page.url)
        print("5s after submit title:", await page.title())

        if "me.sap.com" not in page.url:
            raise RuntimeError(
             f"Login did not return to SAP for Me. Current URL: {page.url}"
            )

        print("SAP SSO redirect successful.")

        await page.wait_for_timeout(2000)

        print(
            "After login URL:",
            page.url
        )

        print(
            "After login title:",
            await page.title()
        )

        # Verify authenticated session
        print(
            "Verifying authenticated session..."
        )

        auth_check = await context.request.get(
            "https://me.sap.com/backend/raw/core/User?login=true"
        )

        print(
            "Auth verification HTTP status:",
            auth_check.status
        )

        if auth_check.status != 200:
            body = await auth_check.text()

            raise RuntimeError(
                "SAP authentication verification failed. "
                f"HTTP {auth_check.status}: "
                f"{body[:500]}"
            )

        print(
            "SAP for Me authentication successful."
        )

        return SAPSession(
            playwright=playwright,
            browser=browser,
            context=context,
        )

    except Exception:
        # Save debug artifacts if anything fails
        if page:
            try:
                os.makedirs(
                    "/debug",
                    exist_ok=True
                )

                await page.screenshot(
                    path="/debug/login-error.png",
                    full_page=True,
                )

                with open(
                    "/debug/login-error.html",
                    "w",
                    encoding="utf-8",
                ) as f:
                    f.write(
                        await page.content()
                    )

            except Exception:
                pass

        if browser:
            await browser.close()

        await playwright.stop()

        raise