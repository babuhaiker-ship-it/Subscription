import asyncio
import logging
from playwright.async_api import async_playwright
import database
from config import config
import os

logger = logging.getLogger(__name__)

STORAGE_STATE = "storage_state.json"

async def get_otp_from_admin(chat_id, client):
    from events import otp_events, otp_values

    admin_id = config.ADMIN_ID
    await database.set_user_state(admin_id, "awaiting_otp")
    await client.send_message(admin_id, f"⚠️ **OTP Required!**\n\nA login or payment attempt is requesting an OTP. Please send the OTP here.\n\nTarget User ID: `{chat_id}`")

    event = asyncio.Event()
    otp_events[admin_id] = event

    try:
        # Wait for 5 minutes
        await asyncio.wait_for(event.wait(), timeout=300)
        otp = otp_values.get(admin_id)
        return otp
    except asyncio.TimeoutError:
        logger.error("Timed out waiting for OTP from admin.")
        return None
    finally:
        await database.set_user_state(admin_id, None)
        otp_events.pop(admin_id, None)
        otp_values.pop(admin_id, None)

async def automate_payment_flow(chat_id, client):
    """
    Automates the Woohoo payment flow:
    1. Login to Woohoo (with Admin OTP if needed)
    2. Add Amazon Voucher to cart with details
    3. Proceed to checkout
    4. Select "Stored Payment Options Plural - Pay via UPI"
    5. Select "pay by any upi app"
    6. Capture and return the redirect link
    """
    woohoo_config = await database.get_woohoo_config()
    gifting_details = await database.get_gifting_details()
    price = await database.get_price()

    if not woohoo_config or not gifting_details:
        logger.error("Woohoo config or gifting details not found.")
        return "CONFIG_ERROR"

    async with async_playwright() as p:
        logger.info("Launching browser...")
        try:
            browser = await p.chromium.launch(headless=True)
        except Exception as e:
            if "playwright install" in str(e).lower():
                raise Exception("Browsers not installed. Please run 'playwright install' on your server.")
            raise e

        # Use Desktop settings
        context_args = {
            "viewport": {"width": 1920, "height": 1080},
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        if os.path.exists(STORAGE_STATE):
            context_args["storage_state"] = STORAGE_STATE

        context = await browser.new_context(**context_args)
        page = await context.new_page()

        try:
            # 1. Login
            logger.info("Navigating to Woohoo account page...")
            await page.goto("https://www.woohoo.in/account", wait_until="networkidle")

            # Check if already logged in
            if await page.query_selector("a[href*='logout']"):
                logger.info("Already logged in.")
            else:
                logger.info("Entering mobile/email...")
                await page.wait_for_selector("#mobile")
                await page.fill("#mobile", woohoo_config["mobile"])
                await page.click("button:has-text('LOGIN')", force=True)

                # Wait for password or OTP or next step
                await asyncio.sleep(3)

                # Check for password
                password_field = await page.query_selector("input[type='password']")
                if password_field:
                    logger.info("Entering password...")
                    await password_field.fill(woohoo_config["password"])
                    await page.click("button:has-text('LOGIN')", force=True)
                    await asyncio.sleep(3)

                # Check for OTP
                otp_field = await page.query_selector("input[placeholder*='OTP'], input[id*='otp'], input[name*='otp']")
                if otp_field:
                    logger.info("OTP required. Requesting from admin...")
                    otp = await get_otp_from_admin(chat_id, client)
                    if not otp:
                        logger.error("No OTP received from admin.")
                        return "OTP_FAILED"
                    await otp_field.fill(otp)
                    # Find verify button
                    verify_btn = await page.query_selector("button:has-text('VERIFY'), button:has-text('SUBMIT'), button:has-text('LOGIN')")
                    if verify_btn:
                        await verify_btn.click(force=True)
                    await asyncio.sleep(5)

                # Save session
                await context.storage_state(path=STORAGE_STATE)

            # 2. Go to Amazon Voucher page
            logger.info("Navigating to Amazon Pay Voucher page...")
            await page.goto("https://www.woohoo.in/amazon-pay-digital-gift-voucher", wait_until="networkidle")

            # Fill Denomination
            logger.info(f"Filling denomination: {price}")
            await page.wait_for_selector("#customPriceText")
            await page.fill("#customPriceText", str(price))

            # Delivery Options: Send as Gift
            logger.info("Selecting 'Send as Gift'...")
            await page.click("#GIFT", force=True)

            # Delivery Mode: Both
            logger.info("Selecting 'Both' delivery mode...")
            await page.click("#deliveryModeBoth", force=True)

            # Gifting Details
            logger.info("Filling gifting details...")
            await page.fill("#name", gifting_details["name"])
            await page.fill("#email", gifting_details["email"])
            await page.fill("#receiver-mobile", gifting_details["mobile"])
            await page.fill("#message", gifting_details["message"])

            # Gift Now
            await page.click("#giftNow", force=True)

            # Click PAY NOW
            logger.info("Clicking PAY NOW...")
            await page.click("button:has-text('PAY NOW')", force=True)

            # Wait for checkout or login redirection
            await asyncio.sleep(5)

            # 3. Checkout Page - Select Payment Options
            logger.info("On checkout page. Selecting UPI Payment...")

            # Select "Stored Payment Options Plural - Pay via UPI"
            # Using a regex to be flexible with exact text matches
            upi_selector = "text=/Stored Payment Options Plural - Pay via UPI/i"
            try:
                logger.info(f"Waiting for selector: {upi_selector}")
                upi_option = await page.wait_for_selector(upi_selector, timeout=30000)
                await upi_option.click(force=True)
            except Exception as e:
                logger.warning(f"Could not find 'Stored Payment Options Plural' with exact text, trying fallback: {e}")
                # Fallback to a broader search if exact text fails
                upi_option = await page.wait_for_selector("text=/Pay via UPI/i", timeout=15000)
                await upi_option.click(force=True)

            await asyncio.sleep(2)

            # Select "pay by any upi app"
            any_upi_selector = "text=/pay by any upi app/i"
            logger.info(f"Waiting for selector: {any_upi_selector}")
            any_upi_option = await page.wait_for_selector(any_upi_selector, timeout=30000)

            # We expect a redirect or a link to be generated after clicking
            logger.info("Clicking 'pay by any upi app' and capturing redirect...")

            payment_link = None

            try:
                # Some payment gateways might open in a new tab
                async with context.expect_page(timeout=30000) as new_page_info:
                    await any_upi_option.click(force=True)

                new_page = await new_page_info.value
                await new_page.wait_for_load_state("networkidle")
                payment_link = new_page.url
                logger.info(f"Captured new page URL: {payment_link}")
                await new_page.close()
            except Exception as e:
                logger.warning(f"No new page opened, checking current page navigation: {e}")
                try:
                    # If no new page, maybe it's a redirect in the same page
                    # We wait a bit to see if URL changes
                    for _ in range(10):
                        await asyncio.sleep(1)
                        if "woohoo.in" not in page.url and "http" in page.url:
                            payment_link = page.url
                            break

                    if not payment_link:
                        payment_link = page.url
                except Exception as ex:
                    logger.error(f"Error checking current page URL: {ex}")
                    payment_link = page.url

            if payment_link and "woohoo.in" not in payment_link:
                return payment_link

            # If still on woohoo, maybe it opened in a new tab or just updated URL
            await asyncio.sleep(5)
            payment_link = page.url

            if payment_link and "checkout" not in payment_link and "woohoo.in" not in payment_link:
                return payment_link

            # Last ditch effort: look for any 'upi://' link on the page
            content = await page.content()
            if "upi://" in content:
                import re
                matches = re.findall(r'upi://[^\s"\'>]+', content)
                if matches:
                    return matches[0]

            return payment_link

        except Exception as e:
            logger.error(f"Automation error: {e}")
            error_ss = f"error_{chat_id}.png"
            await page.screenshot(path=error_ss)
            return "FAILED"
        finally:
            await browser.close()
