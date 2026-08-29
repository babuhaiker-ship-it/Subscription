from config import MAIN_BOT_USERNAME

# Localization data for English and Hindi
STRINGS = {
    "en": {
        "welcome": f"Welcome to **{MAIN_BOT_USERNAME}'s Premium Bot**! 💎\n\nGet exclusive access to premium content, special features, and more by joining our premium plan.",
        "btn_get_premium": "💎 Get Premium Access",
        "btn_change_lang": "🌐 Change Language",
        "select_lang": "Please select your preferred language:",
        "select_plan": "💎 **Select a Subscription Plan:**\n\nChoose the plan that fits you best:",
        "select_method": "💳 **Select Payment Method:**\n\nPlan: **{plan_name}** (${price_usd:.2f} / ₹{price})\nChoose how you would like to pay:",
        "lang_set": "Language set to English! ✅",
        "pay_instr": "To get premium access, please follow these steps:\n\n1.  Pay ₹{price} to the following UPI ID: `{upi_id}`\n2.  You can also scan the QR code below.\n\n⚠️ **Important:** This message will disappear in 10 minutes. Please complete your payment and submit the proof quickly.",
        "btn_pay_upi": "🇮🇳 Pay via UPI (₹{price})",
        "btn_pay_btc": "₿ Pay via Bitcoin (${price_usd:.2f})",
        "btn_check_btc": "🔄 Check Payment Status",
        "btc_instr": "₿ **Bitcoin Payment Invoice**\n\nPlan: **{plan_name}** ({days} Days)\nAmount: `{btc_amount:.8f} BTC` (${price_usd:.2f})\n\n📍 **Bitcoin Address:**\n`{address}`\n\n⏰ **Expires at:** `{expiry_str}` UTC\n\n⚠️ Send exact BTC amount to the address. Click **Check Payment Status** after sending.",
        "btn_i_have_paid": "✅ I have paid",
        "ask_txn": "Please send your **UTR / Transaction ID** to verify your payment:\n\nExample: `609376545020`",
        "verifying": "⏳ Verifying your payment... please wait.",
        "success": f"🎉 **Payment Verified!**\n\nYou now have 30 days of premium access. Go to {MAIN_BOT_USERNAME} and send /start to begin!",
        "error_not_found": "❌ **Payment Not Found!**\n\nWe couldn't find an unclaimed payment with that ID. Please ensure you entered the correct UTR/Transaction ID and that you paid exactly ₹{price}.",
        "error_claimed": "❌ **Already Claimed!**\n\nThis transaction has already been used to claim premium access.",
        "error_expired": "❌ **Transaction Expired!**\n\nThis transaction is too old. Payments must be claimed within 24 hours.",
        "error_amount": "❌ **Wrong Amount!**\n\nThe amount for this transaction doesn't match the required ₹{price}.",
        "error_invalid_format": "❌ **Invalid Format!**\n\nPlease send your 12-digit UTR or Transaction ID (e.g., `609376545020`).",
        "admin_stats": "📊 **Bot Statistics**\n\nTotal Users: {total_users}\nPremium Users: {premium_users}\nTotal Revenue: ₹{revenue}",
        "admin_help": "🛠 **Admin Control Panel**\n\n**General Commands:**\n/stats - View bot statistics\n/setprice 199 - Update price to ₹199\n/setupi name@upi - Update UPI ID\n/setwelcome en <text> - Set English welcome text\n/setsuccess hi <text> - Set Hindi success text\n/addadmin <user_id> - Add a new admin\n\n**Setup:**\n- **Database Channel:** Forward a message from it & reply `/setdatabase`.\n- **Payment Group:** Forward a message from it & reply `/setupidatabase`.\n\n**How to update images:**\n1. Simply **send a photo** to this bot chat.\n2. A menu will appear asking where you want to show it.\n3. The bot will automatically copy it to your channel and set it up!",
        "help_user": "**How to use this bot:**\n\n1. Click '💎 Get Premium Access'.\n2. Pay the required amount to the UPI ID.\n3. Send your **Transaction ID / UTR** (e.g., `609376545020`).\n4. Wait for verification (takes a few seconds).\n5. Enjoy premium access!",
    },
    "hi": {
        "welcome": f"**{MAIN_BOT_USERNAME} के प्रीमियम बॉट** में आपका स्वागत है! 💎\n\nहमारे प्रीमियम प्लान में शामिल होकर विशेष सामग्री और सुविधाओं तक पहुँच प्राप्त करें।",
        "btn_get_premium": "💎 प्रीमियम एक्सेस प्राप्त करें",
        "btn_change_lang": "🌐 भाषा बदलें",
        "select_lang": "कृपया अपनी पसंदीदा भाषा चुनें:",
        "select_plan": "💎 **एक सदस्यता योजना चुनें:**\n\nवह प्लान चुनें जो आपके लिए सबसे उपयुक्त हो:",
        "select_method": "💳 **भुगतान विधि चुनें:**\n\nप्लान: **{plan_name}** (${price_usd:.2f} / ₹{price})\nआप कैसे भुगतान करना चाहते हैं चुनें:",
        "lang_set": "भाषा हिंदी में सेट हो गई है! ✅",
        "pay_instr": "प्रीमियम एक्सेस प्राप्त करने के लिए, कृपया इन चरणों का पालन करें:\n\n1.  इस UPI ID पर ₹{price} का भुगतान करें: `{upi_id}`\n2.  आप नीचे दिए गए QR कोड को भी स्कैन कर सकते हैं।\n\n⚠️ **महत्वपूर्ण:** यह संदेश 10 मिनट में गायब हो जाएगा। कृपया अपना भुगतान पूरा करें और प्रमाण जल्दी जमा करें।",
        "btn_pay_upi": "🇮🇳 UPI से भुगतान करें (₹{price})",
        "btn_pay_btc": "₿ बिटकोइन (BTC) से भुगतान करें (${price_usd:.2f})",
        "btn_check_btc": "🔄 भुगतान स्थिति जांचें",
        "btc_instr": "₿ **बिटकोइन भुगतान बीजक**\n\nप्लान: **{plan_name}** ({days} दिन)\nराशि: `{btc_amount:.8f} BTC` (${price_usd:.2f})\n\n📍 **बिटकोइन पता:**\n`{address}`\n\n⏰ **समाप्ति समय:** `{expiry_str}` UTC\n\n⚠️ कृपया सटीक BTC राशि इस पते पर भेजें। भेजने के बाद **भुगतान स्थिति जांचें** पर क्लिक करें।",
        "btn_i_have_paid": "✅ मैंने भुगतान कर दिया है",
        "ask_txn": "अपने भुगतान को सत्यापित करने के लिए कृपया अपनी **UTR / ट्रांजेक्शन आईडी** भेजें:\n\nउदाहरण: `609376545020`",
        "verifying": "⏳ आपके भुगतान की पुष्टि की जा रही है... कृपया प्रतीक्षा करें।",
        "success": f"🎉 **भुगतान सत्यापित!**\n\nअब आपके पास 30 दिनों का प्रीमियम एक्सेस है। {MAIN_BOT_USERNAME} पर जाएं और शुरू करने के लिए /start भेजें!",
        "error_not_found": "❌ **भुगतान नहीं मिला!**\n\nहमें उस आईडी के साथ कोई लावारिस भुगतान नहीं मिला। कृपया सुनिश्चित करें कि आपने सही UTR/ट्रांजेक्शन आईडी दर्ज की है और आपने ठीक ₹{price} का भुगतान किया है।",
        "error_claimed": "❌ **पहले ही दावा किया जा चुका है!**\n\nइस ट्रांजेक्शन का उपयोग पहले ही प्रीमियम एक्सेस के लिए किया जा चुका है।",
        "error_expired": "❌ **लेन-देन समाप्त!**\n\nयह लेन-देन बहुत पुराना है। भुगतान का दावा 24 घंटों के भीतर किया जाना चाहिए।",
        "error_amount": "❌ **गलत राशि!**\n\nइस ट्रांजेक्शन की राशि आवश्यक ₹{price} से मेल नहीं खाती।",
        "error_invalid_format": "❌ **अवैध प्रारूप!**\n\nकृपया अपनी 12-अंकीय UTR या ट्रांजेक्शन आईडी भेजें (जैसे, `609376545020`)।",
        "admin_stats": "📊 **बॉट आँकड़े**\n\nकुल उपयोगकर्ता: {total_users}\nप्रीमियम उपयोगकर्ता: {premium_users}\nकुल राजस्व: ₹{revenue}",
        "admin_help": "🛠 **एडमिन कंट्रोल पैनल**\n\n**सामान्य कमांड:**\n/stats - बॉट आँकड़े देखें\n/setprice 199 - मूल्य को ₹199 तक अपडेट करें\n/setupi name@upi - UPI ID अपडेट करें\n/setwelcome en <text> - अंग्रेजी स्वागत टेक्स्ट सेट करें\n/setsuccess hi <text> - हिंदी सफलता टेक्स्ट सेट करें\n/addadmin <user_id> - नया एडमिन जोड़ें\n\n**सेटअप:**\n- **डेटाबेस चैनल:** वहां से संदेश फॉरवर्ड करें और `/setdatabase` रिप्लाई दें।\n- **पेमेंट ग्रुप:** वहां से संदेश फॉरवर्ड करें और `/setupidatabase` रिप्लाई दें।\n\n**इमेज कैसे अपडेट करें:**\n1. बस इस बॉट चैट में **एक फोटो भेजें**।\n2. एक मेनू दिखाई देगा जिसमें पूछा जाएगा कि आप इसे कहाँ दिखाना चाहते हैं।\n3. बॉट इसे स्वचालित रूप से आपके चैनल पर कॉपी कर देगा और सेटअप कर देगा!",
        "help_user": "**इस बॉट का उपयोग कैसे करें:**\n\n1. '💎 प्रीमियम एक्सेस प्राप्त करें' पर क्लिक करें।\n2. UPI ID पर आवश्यक राशि का भुगतान करें।\n3. अपनी **ट्रांजेक्शन आईडी / UTR** भेजें (जैसे, `609376545020`)।\n4. सत्यापन की प्रतीक्षा करें (कुछ सेकंड लगते हैं)।\n5. प्रीमियम एक्सेस का आनंद लें!",
    }
}

def get_string(key, lang="en", **kwargs):
    """Retrieves a localized string and formats it if necessary."""
    text = STRINGS.get(lang, STRINGS["en"]).get(key, STRINGS["en"][key])
    return text.format(**kwargs) if kwargs else text
