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
    4. Select UPI -> QR Code
    5. Take screenshot of QR and send to user
    6. Wait for success redirection
    """
    woohoo_config = await database.get_woohoo_config()
    gifting_details = await database.get_gifting_details()

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
            logger.info(f"Filling denomination: {config.PREMIUM_PRICE_INR}")
            await page.wait_for_selector("#customPriceText")
            await page.fill("#customPriceText", str(config.PREMIUM_PRICE_INR))

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
            logger.info("On checkout page. Selecting UPI...")

            # Select UPI
            upi_option = await page.wait_for_selector("text=/Pay via UPI/i", timeout=30000)
            if upi_option:
                logger.info("Found UPI option, clicking...")
                await upi_option.click(force=True)
                await asyncio.sleep(2)

            # Select QR Code
            logger.info("Looking for QR Code option...")
            qr_option = await page.wait_for_selector("text=/QR Code/i", timeout=15000)
            if qr_option:
                logger.info("Found QR Code option, clicking...")
                await qr_option.click(force=True)
                await asyncio.sleep(2)

            # Click final Pay button if it exists
            pay_button = await page.query_selector("button:has-text('Pay Now'), button:has-text('PAY NOW'), button:has-text('Proceed to Pay'), button:has-text('PAY')")
            if pay_button:
                logger.info("Found Pay button, clicking...")
                await pay_button.click(force=True)
                await asyncio.sleep(5)

            # Wait for QR code element to appear
            logger.info("Waiting for QR code to appear...")
            # Common QR selectors
            qr_element = None
            for selector in ["img[src*='qr']", ".qr-code", "canvas", "#qr-code", ".qrCode"]:
                qr_element = await page.query_selector(selector)
                if qr_element:
                    break

            if not qr_element:
                 # Try to wait a bit more
                 try:
                     qr_element = await page.wait_for_selector("img[src*='qr'], .qr-code, canvas, #qr-code", timeout=30000)
                 except:
                     pass

            if qr_element:
                qr_path = f"qr_{chat_id}.png"
                await qr_element.screenshot(path=qr_path)
                logger.info(f"QR code screenshot saved: {qr_path}")

                # Send QR to user via bot
                await client.send_photo(
                    chat_id,
                    qr_path,
                    caption=f"✅ **QR Code Generated!**\n\nPlease scan this QR code to pay **₹{config.PREMIUM_PRICE_INR}**.\n\n⏳ You have 5 minutes to complete the payment. The bot will automatically grant access once detected."
                )
                if os.path.exists(qr_path):
                    os.remove(qr_path)
            else:
                logger.error("QR element not found.")
                # We can't proceed without QR
                return "QR_NOT_FOUND"

            # 4. Wait for Redirection (Success)
            logger.info("Waiting for payment success redirection (max 5 mins)...")
            try:
                # Success usually redirects to a page with "thank you" or "success" or "confirmation"
                await page.wait_for_function(
                    "() => document.body.innerText.toLowerCase().includes('thank you') || "
                    "window.location.href.toLowerCase().includes('success') || "
                    "window.location.href.toLowerCase().includes('order-confirmation') || "
                    "window.location.href.toLowerCase().includes('confirmation')",
                    timeout=300000 # 5 minutes
                )
                logger.info("Payment success detected!")
                return "SUCCESS"
            except Exception as e:
                logger.warning(f"Wait for redirect timed out or failed: {e}")
                return "TIMEOUT"

        except Exception as e:
            logger.error(f"Automation error: {e}")
            error_ss = f"error_{chat_id}.png"
            await page.screenshot(path=error_ss)
            return "FAILED"
        finally:
            await browser.close()
