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
        browser = await p.chromium.launch(headless=True) # Set to False for debugging if needed

        # Use existing session if available
        context_args = {}
        if os.path.exists(STORAGE_STATE):
            context_args["storage_state"] = STORAGE_STATE

        context = await browser.new_context(**context_args)
        page = await context.new_page()

        try:
            # 1. Login
            await page.goto("https://www.woohoo.in/account")
            await asyncio.sleep(2)

            # Check if already logged in (if we see logout or account details)
            if await page.query_selector("a[href*='logout']"):
                logger.info("Already logged in.")
            else:
                await page.fill("#mobile", woohoo_config["mobile"])
                await page.click("button:has-text('LOGIN')")
                await asyncio.sleep(2)

                # Check for password or OTP
                if await page.query_selector("input[type='password']"):
                    await page.fill("input[type='password']", woohoo_config["password"])
                    await page.click("button:has-text('LOGIN')")
                    await asyncio.sleep(2)

                # Check for OTP
                if await page.query_selector("input[placeholder*='OTP']"):
                    otp = await get_otp_from_admin(chat_id, client)
                    if not otp:
                        return None
                    await page.fill("input[placeholder*='OTP']", otp)
                    await page.click("button:has-text('VERIFY')") # Adjust selector if needed
                    await asyncio.sleep(2)

                # Save session
                await context.storage_state(path=STORAGE_STATE)

            # 2. Go to Amazon Voucher page
            await page.goto("https://www.woohoo.in/amazon-pay-digital-gift-voucher")
            await asyncio.sleep(2)

            # Fill Denomination
            await page.fill("#customPriceText", str(config.PREMIUM_PRICE_INR))

            # Delivery Options: Send as Gift (already selected by default usually, but let's be sure)
            await page.click("#GIFT")

            # Delivery Mode: Both
            await page.click("#deliveryModeBoth")

            # Gifting Details
            await page.fill("#name", gifting_details["name"])
            await page.fill("#email", gifting_details["email"])
            await page.fill("#receiver-mobile", gifting_details["mobile"])
            await page.fill("#message", gifting_details["message"])

            # Gift Now
            await page.click("#giftNow")

            # Click PAY NOW
            await page.click("button:has-text('PAY NOW')")
            await asyncio.sleep(5) # Wait for checkout page to load

            # 3. Checkout Page - Select Payment Options
            # User said: select "Stored Payment Options Plural - Pay via UPI"
            # and then "pay by any upi app"

            # Wait for checkout page components
            await page.wait_for_selector("text=Pay via UPI", timeout=30000)

            # Select "Pay via UPI"
            await page.click("text=Pay via UPI")
            await asyncio.sleep(1)

            # Select "pay by any upi app"
            await page.click("text=pay by any upi app")
            await asyncio.sleep(2)

            # Sometimes there is a "Pay" or "Continue" button after selecting the option
            pay_button = await page.query_selector("button:has-text('Pay Now'), button:has-text('PAY NOW'), button:has-text('Proceed to Pay')")
            if pay_button:
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
