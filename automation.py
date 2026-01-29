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

async def generate_payment_link(chat_id, client):
    woohoo_config = await database.get_woohoo_config()
    gifting_details = await database.get_gifting_details()

    if not woohoo_config or not gifting_details:
        logger.error("Woohoo config or gifting details not found.")
        return None

    async with async_playwright() as p:
        logger.info("Launching browser...")
        try:
            browser = await p.chromium.launch(headless=True)
        except Exception as e:
            if "playwright install" in str(e).lower():
                raise Exception("Browsers not installed. Please run 'playwright install' on your server.")
            raise e

        # Use mobile-like settings as the site seems optimized for it
        context_args = {
            "viewport": {"width": 375, "height": 812},
            "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 13_2_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.0.3 Mobile/15E148 Safari/04.1"
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
                await page.click("button:has-text('LOGIN')")

                # Wait for password or OTP or next step
                await asyncio.sleep(3)

                # Check for password
                password_field = await page.query_selector("input[type='password']")
                if password_field:
                    logger.info("Entering password...")
                    await password_field.fill(woohoo_config["password"])
                    await page.click("button:has-text('LOGIN')")
                    await asyncio.sleep(3)

                # Check for OTP
                otp_field = await page.query_selector("input[placeholder*='OTP'], input[id*='otp'], input[name*='otp']")
                if otp_field:
                    logger.info("OTP required. Requesting from admin...")
                    otp = await get_otp_from_admin(chat_id, client)
                    if not otp:
                        logger.error("No OTP received from admin.")
                        return None
                    await otp_field.fill(otp)
                    # Find verify button
                    verify_btn = await page.query_selector("button:has-text('VERIFY'), button:has-text('SUBMIT'), button:has-text('LOGIN')")
                    if verify_btn:
                        await verify_btn.click()
                    await asyncio.sleep(5)

                # Save session
                await context.storage_state(path=STORAGE_STATE)

            # 2. Go to Amazon Voucher page
            logger.info("Navigating to Amazon Pay Voucher page...")
            await page.goto("https://www.woohoo.in/amazon-pay-digital-gift-voucher", wait_until="networkidle")

            # Fill Denomination
            logger.info(f"Filling denomination: {config.PREMIUM_PRICE_INR}")
            await page.wait_for_selector("#customPriceText")
            await page.fill("#customPriceText", str(config.PREMIUM_PRICE_INR))

            # Delivery Options: Send as Gift
            logger.info("Selecting 'Send as Gift'...")
            await page.click("#GIFT")

            # Delivery Mode: Both
            logger.info("Selecting 'Both' delivery mode...")
            await page.click("#deliveryModeBoth")

            # Gifting Details
            logger.info("Filling gifting details...")
            await page.fill("#name", gifting_details["name"])
            await page.fill("#email", gifting_details["email"])
            await page.fill("#receiver-mobile", gifting_details["mobile"])
            await page.fill("#message", gifting_details["message"])

            # Gift Now
            await page.click("#giftNow")

            # Click PAY NOW
            logger.info("Clicking PAY NOW...")
            await page.click("button:has-text('PAY NOW')")

            # Wait for checkout or login redirection (sometimes it asks to login again)
            await asyncio.sleep(5)

            # 3. Checkout Page - Select Payment Options
            logger.info("On checkout page. Selecting payment options...")

            # Try to find "Stored Payment Options" first if it needs to be expanded
            # User said "Stored Payment Options Plural"
            # We search for elements containing this text
            stored_options = await page.query_selector("text=/Stored Payment Options/i")
            if not stored_options:
                stored_options = await page.query_selector("text=/Stored Payment Option/i")

            if stored_options:
                logger.info("Found Stored Payment Options, clicking...")
                await stored_options.click()
                await asyncio.sleep(1)

            # Look for "Pay via UPI"
            # The user specifically mentioned "Stored Payment Options Plural - Pay via UPI"
            upi_option = await page.query_selector("text=/Pay via UPI/i")
            if not upi_option:
                upi_option = await page.wait_for_selector("text=/UPI/i", timeout=30000)

            if upi_option:
                logger.info("Found UPI option, clicking...")
                await upi_option.click()
                await asyncio.sleep(1)

            # Select "pay by any upi app"
            upi_app_option = await page.wait_for_selector("text=/any upi app/i", timeout=15000)
            if upi_app_option:
                logger.info("Found 'pay by any upi app', clicking...")
                await upi_app_option.click()
                await asyncio.sleep(2)

            # Sometimes there is a "Pay" or "Continue" button after selecting the option
            pay_button = await page.query_selector("button:has-text('Pay Now'), button:has-text('PAY NOW'), button:has-text('Proceed to Pay'), button:has-text('PAY')")
            if pay_button:
                logger.info("Found Pay button, clicking...")
                await pay_button.click()

            # Wait for redirection to the payment gateway (UPI app selector/link)
            # We want to capture the final URL which is the payment link
            try:
                await page.wait_for_function("() => window.location.href.includes('upi') || window.location.href.includes('checkout') || !window.location.href.includes('woohoo.in')", timeout=30000)
            except:
                pass

            payment_link = page.url
            logger.info(f"Generated payment link: {payment_link}")

            return payment_link

        except Exception as e:
            logger.error(f"Automation error: {e}")
            await page.screenshot(path="error.png")
            return None
        finally:
            await browser.close()
