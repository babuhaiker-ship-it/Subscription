from config import MAIN_BOT_USERNAME

# Localization data for English and Hindi
STRINGS = {
    "en": {
        "welcome": f"Welcome to **{MAIN_BOT_USERNAME}'s Premium Bot**! 💎\n\nGet exclusive access to premium content, special features, and more by joining our premium plan.",
        "btn_get_premium": "💎 Get Premium Access",
        "btn_change_lang": "🌐 Change Language",
        "select_lang": "Please select your preferred language:",
        "lang_set": "Language set to English! ✅",
        "pay_instr": "To get premium access, please follow these steps:\n\n1.  Pay ₹{price} to the following UPI ID: `{upi_id}`\n2.  You can also scan the QR code below.\n\n⚠️ **Important:** This message will disappear in 10 minutes. Please complete your payment and submit the proof quickly.",
        "btn_i_have_paid": "✅ I have paid",
        "ask_txn": "Please send your **Transaction ID** and **Amount** together like this:\n\n`423567890123 {price}`",
        "verifying": "⏳ Verifying your payment... please wait.",
        "success": f"🎉 **Payment Verified!**\n\nYou now have 30 days of premium access. Go to {MAIN_BOT_USERNAME} and send /start to begin!",
        "error_not_found": "❌ **Payment Not Found!**\n\nWe couldn't find a payment with that Transaction ID. Please make sure you entered it correctly and that you paid the exact amount.",
        "error_claimed": "❌ **Already Claimed!**\n\nThis transaction has already been used to claim premium access.",
        "error_expired": "❌ **Transaction Expired!**\n\nThis transaction is too old. Payments must be claimed within 24 hours.",
        "error_amount": "❌ **Wrong Amount!**\n\nThe amount for this transaction doesn't match the required ₹{price}.",
        "error_invalid_format": "❌ **Invalid Format!**\n\nPlease send your Transaction ID and Amount together (e.g., `423567890123 {price}`).",
        "admin_stats": "📊 **Bot Statistics**\n\nTotal Users: {total_users}\nPremium Users: {premium_users}\nTotal Revenue: ₹{revenue}",
        "admin_help": "Admin Commands:\n/stats - View bot statistics\n/setprice <amount> - Update premium price\n/setupi <upi_id> - Update UPI ID\n/setqr <channel_id> <message_id> - Set QR image source",
    },
    "hi": {
        "welcome": f"**{MAIN_BOT_USERNAME} के प्रीमियम बॉट** में आपका स्वागत है! 💎\n\nहमारे प्रीमियम प्लान में शामिल होकर विशेष सामग्री और सुविधाओं तक पहुँच प्राप्त करें।",
        "btn_get_premium": "💎 प्रीमियम एक्सेस प्राप्त करें",
        "btn_change_lang": "🌐 भाषा बदलें",
        "select_lang": "कृपया अपनी पसंदीदा भाषा चुनें:",
        "lang_set": "भाषा हिंदी में सेट हो गई है! ✅",
        "pay_instr": "प्रीमियम एक्सेस प्राप्त करने के लिए, कृपया इन चरणों का पालन करें:\n\n1.  इस UPI ID पर ₹{price} का भुगतान करें: `{upi_id}`\n2.  आप नीचे दिए गए QR कोड को भी स्कैन कर सकते हैं।\n\n⚠️ **महत्वपूर्ण:** यह संदेश 10 मिनट में गायब हो जाएगा। कृपया अपना भुगतान पूरा करें और प्रमाण जल्दी जमा करें।",
        "btn_i_have_paid": "✅ मैंने भुगतान कर दिया है",
        "ask_txn": "कृपया अपनी **लेन-देन आईडी (Transaction ID)** और **राशि (Amount)** इस तरह एक साथ भेजें:\n\n`423567890123 {price}`",
        "verifying": "⏳ आपके भुगतान की पुष्टि की जा रही है... कृपया प्रतीक्षा करें।",
        "success": f"🎉 **भुगतान सत्यापित!**\n\nअब आपके पास 30 दिनों का प्रीमियम एक्सेस है। {MAIN_BOT_USERNAME} पर जाएं और शुरू करने के लिए /start भेजें!",
        "error_not_found": "❌ **भुगतान नहीं मिला!**\n\nहमें उस ट्रांजेक्शन आईडी के साथ कोई भुगतान नहीं मिला। कृपया सुनिश्चित करें कि आपने इसे सही ढंग से दर्ज किया है और आपने सटीक राशि का भुगतान किया है।",
        "error_claimed": "❌ **पहले ही दावा किया जा चुका है!**\n\nइस ट्रांजेक्शन का उपयोग पहले ही प्रीमियम एक्सेस के लिए किया जा चुका है।",
        "error_expired": "❌ **लेन-देन समाप्त!**\n\nयह लेन-देन बहुत पुराना है। भुगतान का दावा 24 घंटों के भीतर किया जाना चाहिए।",
        "error_amount": "❌ **गलत राशि!**\n\nइस ट्रांजेक्शन की राशि आवश्यक ₹{price} से मेल नहीं खाती।",
        "error_invalid_format": "❌ **अवैध प्रारूप!**\n\nकृपया अपनी ट्रांजेक्शन आईडी और राशि एक साथ भेजें (जैसे, `423567890123 {price}`).",
        "admin_stats": "📊 **बॉट आँकड़े**\n\nकुल उपयोगकर्ता: {total_users}\nप्रीमियम उपयोगकर्ता: {premium_users}\nकुल राजस्व: ₹{revenue}",
        "admin_help": "एडमिन कमांड:\n/stats - बॉट आँकड़े देखें\n/setprice <राशि> - प्रीमियम मूल्य अपडेट करें\n/setupi <upi_id> - UPI ID अपडेट करें\n/setqr <channel_id> <message_id> - QR इमेज स्रोत सेट करें",
    }
}

def get_string(key, lang="en", **kwargs):
    """Retrieves a localized string and formats it if necessary."""
    text = STRINGS.get(lang, STRINGS["en"]).get(key, STRINGS["en"][key])
    return text.format(**kwargs) if kwargs else text
