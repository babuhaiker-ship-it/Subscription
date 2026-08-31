from config import MAIN_BOT_USERNAME

# Localization data for English and Hindi
STRINGS = {
    "en": {
        "welcome": "⚡ **Welcome to Payment Bot!** 💎\n\nUnlock instant, exclusive premium access by choosing a plan below.\n\n👤 **Status:** {status_badge}\n📅 **Expires:** `{expiry_str}`",
        "btn_get_premium": "💎 Upgrade to Premium",
        "btn_my_profile": "👤 My Profile & Status",
        "btn_change_lang": "🌐 Language Settings",
        "select_lang": "🌐 **Select Your Language:**",
        "select_plan": "💎 **Choose Subscription Plan:**\n\nSelect a duration that best suits your needs:",
        "select_method": "💳 **Payment Checkout:**\n\n📦 **Plan:** {plan_name} ({days} Days)\n💵 **Amount:** `${price_usd:.2f}`\n\nClick below to generate your secure Bitcoin deposit invoice:",
        "lang_set": "Language updated to English! ✅",
        "btn_pay_btc": "₿ Pay with Bitcoin (${price_usd:.2f})",
        "btn_check_btc": "🔄 Check Payment Status",
        "btn_back": "🔙 Main Menu",
        "btc_instr": "₿ **Bitcoin Payment Invoice**\n\n📦 **Plan:** {plan_name} ({days} Days)\n💰 **Amount:** `{btc_amount:.8f} BTC` (${price_usd:.2f})\n\n📍 **Bitcoin Deposit Address:**\n`{address}`\n\n⏰ **Invoice Expiry:** `{expiry_str}` UTC\n\n📲 *Scan QR code below or copy the address above. Send exact amount and click 'Check Payment Status' after sending.*",
        "profile_text": "👤 **User Profile & Subscription:**\n\n🆔 **User ID:** `{user_id}`\n✨ **Status:** {status_badge}\n📅 **Valid Until:** `{expiry_str}`",
        "verifying": "⏳ Verifying your payment... please wait.",
        "success": "🎉 **Payment Verified!**\n\nYour premium access has been activated! Send /start anytime to view your status.",
        "error_not_found": "❌ **Payment Not Found!**\n\nWe couldn't find an unclaimed payment with that ID. Please ensure you entered the correct Transaction ID.",
        "error_claimed": "❌ **Already Claimed!**\n\nThis transaction has already been used to claim premium access.",
        "error_expired": "❌ **Transaction Expired!**\n\nThis transaction is too old. Payments must be claimed within 24 hours.",
        "error_amount": "❌ **Wrong Amount!**\n\nThe amount for this transaction doesn't match the required amount.",
        "error_invalid_format": "❌ **Invalid Format!**\n\nPlease send your valid Transaction ID.",
        "admin_stats": "📊 **Bot Statistics**\n\nTotal Users: {total_users}\nPremium Users: {premium_users}\nTotal Revenue: ${revenue}",
        "admin_help": "🛠 **Admin Control Panel**\n\n**Commands:**\n/managesub - Manage plans (Add, Edit, Delete)\n/btcsettings - Configure Bitcoin & XPUB settings\n/stats - View bot statistics\n/setprice usd 3.99 - Update default price in USD\n/setwelcome en <text> - Custom welcome text\n/setsuccess en <text> - Custom success text\n/addadmin <user_id> - Add a new admin",
        "help_user": "**How to use this bot:**\n\n1. Click '💎 Get Premium Access'.\n2. Select your plan and preferred payment method.\n3. Complete payment and verify status.\n4. Enjoy premium access!",
    },
    "hi": {
        "welcome": "⚡ **पेमेंट बॉट में आपका स्वागत है!** 💎\n\nनीचे योजना चुनकर तुरंत प्रीमियम एक्सेस प्राप्त करें।\n\n👤 **स्थिति:** {status_badge}\n📅 **समाप्ति तिथि:** `{expiry_str}`",
        "btn_get_premium": "💎 प्रीमियम अपग्रेड करें",
        "btn_my_profile": "👤 मेरी प्रोफ़ाइल",
        "btn_change_lang": "🌐 भाषा सेटिंग्स",
        "select_lang": "🌐 **अपनी भाषा चुनें:**",
        "select_plan": "💎 **सदस्यता योजना चुनें:**",
        "select_method": "💳 **भुगतान चेकआउट:**\n\n📦 **प्लान:** {plan_name} ({days} दिन)\n💵 **राशि:** `${price_usd:.2f}`",
        "lang_set": "भाषा हिंदी में सेट हो गई है! ✅",
        "btn_pay_btc": "₿ बिटकोइन से भुगतान करें (${price_usd:.2f})",
        "btn_check_btc": "🔄 भुगतान स्थिति जांचें",
        "btn_back": "🔙 मुख्य मेनू",
        "btc_instr": "₿ **बिटकोइन भुगतान बीजक**\n\n📦 **प्लान:** {plan_name} ({days} दिन)\n💰 **राशि:** `{btc_amount:.8f} BTC` (${price_usd:.2f})\n\n📍 **बिटकोइन जमा पता:**\n`{address}`\n\n⏰ **समाप्ति समय:** `{expiry_str}` UTC",
        "profile_text": "👤 **उपयोगकर्ता प्रोफ़ाइल:**\n\n🆔 **आईडी:** `{user_id}`\n✨ **स्थिति:** {status_badge}\n📅 **वैध तिथि:** `{expiry_str}`",
        "verifying": "⏳ आपके भुगतान की पुष्टि की जा रही है... कृपया प्रतीक्षा करें।",
        "success": "🎉 **भुगतान सत्यापित!**\n\nआपका प्रीमियम एक्सेस सक्रिय हो गया है!",
        "error_not_found": "❌ **भुगतान नहीं मिला!**\n\nहमें उस आईडी के साथ कोई लावारिस भुगतान नहीं मिला।",
        "error_claimed": "❌ **पहले ही दावा किया जा चुका है!**",
        "error_expired": "❌ **लेन-देन समाप्त!**",
        "error_amount": "❌ **गलत राशि!**",
        "error_invalid_format": "❌ **अवैध प्रारूप!**",
        "admin_stats": "📊 **बॉट आँकड़े**\n\nकुल उपयोगकर्ता: {total_users}\nप्रीमियम उपयोगकर्ता: {premium_users}\nकुल राजस्व: ${revenue}",
        "admin_help": "🛠 **एडमिन कंट्रोल पैनल**\n\n/managesub - योजनाएं प्रबंधित करें\n/btcsettings - बिटकोइन सेटिंग्स\n/stats - आँकड़े",
        "help_user": "**इस बॉट का उपयोग कैसे करें:**\n\n1. '💎 प्रीमियम एक्सेस प्राप्त करें' पर क्लिक करें।\n2. अपनी योजना चुनें और भुगतान पूरा करें!",
    }
}

def get_string(key, lang="en", **kwargs):
    """Retrieves a localized string and formats it if necessary."""
    text = STRINGS.get(lang, STRINGS["en"]).get(key, STRINGS["en"][key])
    return text.format(**kwargs) if kwargs else text
