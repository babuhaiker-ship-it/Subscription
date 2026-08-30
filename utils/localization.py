from config import MAIN_BOT_USERNAME

# Localization data for English and Hindi
STRINGS = {
    "en": {
        "welcome": "Welcome to **Payment Bot**! 💎\n\nGet exclusive access to premium content, special features, and more by joining our premium plan.",
        "btn_get_premium": "💎 Get Premium Access",
        "btn_change_lang": "🌐 Change Language",
        "select_lang": "Please select your preferred language:",
        "select_plan": "💎 **Select a Subscription Plan:**\n\nChoose the plan that fits you best:",
        "select_method": "💳 **Select Payment Method:**\n\nPlan: **{plan_name}** (${price_usd:.2f})\nChoose how you would like to pay:",
        "lang_set": "Language set to English! ✅",
        "pay_instr": "To get premium access, please follow these steps:\n\n1. Pay ${price_usd:.2f} to our payment method.\n2. Submit payment proof when finished.",
        "btn_pay_btc": "₿ Pay via Bitcoin (${price_usd:.2f})",
        "btn_check_btc": "🔄 Check Payment Status",
        "btc_instr": "₿ **Bitcoin Payment Invoice**\n\nPlan: **{plan_name}** ({days} Days)\nAmount: `{btc_amount:.8f} BTC` (${price_usd:.2f})\n\n📍 **Bitcoin Address:**\n`{address}`\n\n⏰ **Expires at:** `{expiry_str}` UTC\n\n⚠️ Send exact BTC amount to the address. Click **Check Payment Status** after sending.",
        "btn_i_have_paid": "✅ I have paid",
        "ask_txn": "Please send your **Transaction ID / Reference** to verify your payment:",
        "verifying": "⏳ Verifying your payment... please wait.",
        "success": "🎉 **Payment Verified!**\n\nYou now have premium access. Send /start to begin!",
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
        "welcome": "**पेमेंट बॉट** में आपका स्वागत है! 💎\n\nहमारे प्रीमियम प्लान में शामिल होकर विशेष सामग्री और सुविधाओं तक पहुँच प्राप्त करें।",
        "btn_get_premium": "💎 प्रीमियम एक्सेस प्राप्त करें",
        "btn_change_lang": "🌐 भाषा बदलें",
        "select_lang": "कृपया अपनी पसंदीदा भाषा चुनें:",
        "select_plan": "💎 **एक सदस्यता योजना चुनें:**\n\nवह प्लान चुनें जो आपके लिए सबसे उपयुक्त हो:",
        "select_method": "💳 **भुगतान विधि चुनें:**\n\nप्लान: **{plan_name}** (${price_usd:.2f})\nआप कैसे भुगतान करना चाहते हैं चुनें:",
        "lang_set": "भाषा हिंदी में सेट हो गई है! ✅",
        "pay_instr": "प्रीमियम एक्सेस प्राप्त करने के लिए, कृपया भुगतान पूरा करें।",
        "btn_pay_btc": "₿ बिटकोइन (BTC) से भुगतान करें (${price_usd:.2f})",
        "btn_check_btc": "🔄 भुगतान स्थिति जांचें",
        "btc_instr": "₿ **बिटकोइन भुगतान बीजक**\n\nप्लान: **{plan_name}** ({days} दिन)\nराशि: `{btc_amount:.8f} BTC` (${price_usd:.2f})\n\n📍 **बिटकोइन पता:**\n`{address}`\n\n⏰ **समाप्ति समय:** `{expiry_str}` UTC\n\n⚠️ कृपया सटीक BTC राशि इस पते पर भेजें। भेजने के बाद **भुगतान स्थिति जांचें** पर क्लिक करें।",
        "btn_i_have_paid": "✅ मैंने भुगतान कर दिया है",
        "ask_txn": "अपने भुगतान को सत्यापित करने के लिए कृपया अपनी **ट्रांजेक्शन आईडी** भेजें:",
        "verifying": "⏳ आपके भुगतान की पुष्टि की जा रही है... कृपया प्रतीक्षा करें।",
        "success": "🎉 **भुगतान सत्यापित!**\n\nअब आपके पास प्रीमियम एक्सेस है। शुरू करने के लिए /start भेजें!",
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
