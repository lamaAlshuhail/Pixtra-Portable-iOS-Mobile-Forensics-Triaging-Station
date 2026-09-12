import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


APP_CATALOG: dict[str, tuple[str, str, str]] = {
    "net.whatsapp.WhatsApp": ("WhatsApp", "Communication", "Meta"),
    "com.burbn.instagram": ("Instagram", "Social", "Meta"),
    "com.facebook.Facebook": ("Facebook", "Social", "Meta"),
    "com.facebook.Messenger": ("Messenger", "Communication", "Meta"),
    "com.tinyspeck.chatlyio": ("Slack", "Communication", "Salesforce"),
    "ph.telegra.Telegraph": ("Telegram", "Communication", "Telegram FZ"),
    "org.thoughtcrime.signal": ("Signal", "Communication", "Signal Foundation"),
    "com.toyopagroup.picaboo": ("Snapchat", "Social", "Snap Inc"),
    "com.zhiliaoapp.musically": ("TikTok", "Social", "ByteDance"),
    "com.atebits.Tweetie2": ("X (Twitter)", "Social", "X Corp"),
    "com.reddit.Reddit": ("Reddit", "Social", "Reddit Inc"),
    "com.linkedin.LinkedIn": ("LinkedIn", "Social", "Microsoft"),
    "ph.threads.Threads": ("Threads", "Social", "Meta"),
    "com.bluesky.app": ("Bluesky", "Social", "Bluesky"),
    "com.discord": ("Discord", "Communication", "Discord Inc"),
    "co.hinge.app": ("Hinge", "Dating", "Match Group"),
    "com.cardify.tinder": ("Tinder", "Dating", "Match Group"),
    "com.bumble.app": ("Bumble", "Dating", "Bumble Inc"),

    "com.openai.chat": ("ChatGPT", "AI Assistant", "OpenAI"),
    "com.google.gemini": ("Gemini", "AI Assistant", "Google"),
    "com.google.Bard": ("Gemini (Bard)", "AI Assistant", "Google"),
    "ai.perplexity.app": ("Perplexity", "AI Assistant", "Perplexity"),
    "com.microsoft.Copilot.app": ("Microsoft Copilot", "AI Assistant", "Microsoft"),
    "com.character.app": ("Character.AI", "AI Assistant", "Character Technologies"),
    "ai.deepseek.chat": ("DeepSeek", "AI Assistant", "DeepSeek"),
    "ai.x.grok": ("Grok", "AI Assistant", "xAI"),

    "com.google.chrome.ios": ("Chrome", "Browser", "Google"),
    "org.mozilla.ios.Firefox": ("Firefox", "Browser", "Mozilla"),
    "com.brave.ios.browser": ("Brave", "Browser", "Brave"),
    "com.duckduckgo.mobile.ios": ("DuckDuckGo", "Browser", "DuckDuckGo"),
    "com.opera.OperaTouch": ("Opera", "Browser", "Opera"),

    "com.google.Gmail": ("Gmail", "Email", "Google"),
    "com.microsoft.Office.Outlook": ("Outlook", "Email", "Microsoft"),
    "com.readdle.smartemail7": ("Spark", "Email", "Readdle"),
    "com.airmail.proton": ("Proton Mail", "Email", "Proton"),

    "com.getdropbox.Dropbox": ("Dropbox", "Storage", "Dropbox"),
    "com.microsoft.skydrive": ("OneDrive", "Storage", "Microsoft"),
    "com.google.Drive": ("Google Drive", "Storage", "Google"),
    "com.apple.iCloudDriveApp": ("iCloud Drive", "Storage", "Apple"),

    "com.spotify.client": ("Spotify", "Music", "Spotify"),
    "com.google.ios.youtube": ("YouTube", "Video", "Google"),
    "com.google.youtubekids": ("YouTube Kids", "Video", "Google"),
    "com.netflix.Netflix": ("Netflix", "Video", "Netflix"),
    "com.amazon.aiv.AIVApp": ("Prime Video", "Video", "Amazon"),
    "com.disney.disneyplus": ("Disney+", "Video", "Disney"),
    "com.hulu.plus": ("Hulu", "Video", "Disney"),
    "com.shazamPro.shazam-iphone": ("Shazam", "Music", "Apple"),
    "com.audible.iphone": ("Audible", "Audio", "Amazon"),

    "com.microsoft.Office.Word": ("Word", "Productivity", "Microsoft"),
    "com.microsoft.Office.Excel": ("Excel", "Productivity", "Microsoft"),
    "com.microsoft.Office.Powerpoint": ("PowerPoint", "Productivity", "Microsoft"),
    "com.google.Docs": ("Google Docs", "Productivity", "Google"),
    "com.google.Sheets": ("Google Sheets", "Productivity", "Google"),
    "com.notion.id": ("Notion", "Productivity", "Notion Labs"),
    "md.obsidian": ("Obsidian", "Productivity", "Obsidian"),
    "com.todoist.app": ("Todoist", "Productivity", "Doist"),
    "com.evernote.iPhone.Evernote": ("Evernote", "Productivity", "Evernote"),
    "com.culturedcode.ThingsiPhone": ("Things 3", "Productivity", "Cultured Code"),

    "com.paypal.PPClient": ("PayPal", "Finance", "PayPal"),
    "com.venmo.TouchFree": ("Venmo", "Finance", "PayPal"),
    "com.squareup.cash": ("Cash App", "Finance", "Block Inc"),

    "com.ubercab.UberClient": ("Uber", "Transport", "Uber"),
    "com.lyft.iphone": ("Lyft", "Transport", "Lyft"),
    "com.airbnb.app": ("Airbnb", "Travel", "Airbnb"),
    "com.booking.BookingApp": ("Booking.com", "Travel", "Booking Holdings"),
    "com.flightradar24.flightradar24Free": ("Flightradar24", "Travel", "Flightradar24"),
    "com.googleMaps.Maps": ("Google Maps", "Navigation", "Google"),
    "com.waze.iphone": ("Waze", "Navigation", "Google"),

    "com.amazon.Amazon": ("Amazon", "Shopping", "Amazon"),
    "com.shein.app": ("SHEIN", "Shopping", "SHEIN"),
    "com.alibaba.aliexpresshd": ("AliExpress", "Shopping", "Alibaba"),

    "com.faceapp.FaceApp": ("FaceApp", "Photo", "FaceApp"),
    "com.lightricks.facetune2": ("Facetune", "Photo", "Lightricks"),
    "com.lightricks.videoleap": ("Videoleap", "Video Editing", "Lightricks"),
    "com.adobe.AdobeLightroomCC": ("Lightroom", "Photo", "Adobe"),
    "com.adobe.PSMobile": ("Photoshop Express", "Photo", "Adobe"),
    "com.canva.canvaeditor": ("Canva", "Design", "Canva"),

    "com.apple.Music": ("Apple Music", "Music", "Apple"),
    "com.apple.mobilesafari": ("Safari", "Browser", "Apple"),
    "com.apple.MobileStore": ("App Store", "System", "Apple"),
    "com.apple.mobilemail": ("Mail", "Email", "Apple"),
    "com.apple.MobileSMS": ("Messages", "Communication", "Apple"),
    "com.apple.calculator": ("Calculator", "Utility", "Apple"),
    "com.apple.mobilenotes": ("Notes", "Productivity", "Apple"),
    "com.apple.mobilephone": ("Phone", "Communication", "Apple"),
    "com.apple.mobilecal": ("Calendar", "Productivity", "Apple"),
    "com.apple.weather": ("Weather", "Utility", "Apple"),
    "com.apple.AppStore": ("App Store", "System", "Apple"),
    "com.apple.podcasts": ("Podcasts", "Audio", "Apple"),
    "com.apple.iBooks": ("Books", "Reading", "Apple"),
    "com.apple.Health": ("Health", "Health", "Apple"),
    "com.apple.Fitness": ("Fitness", "Health", "Apple"),
    "com.apple.Maps": ("Maps", "Navigation", "Apple"),
    "com.apple.findmy": ("Find My", "System", "Apple"),
    "com.apple.shortcuts": ("Shortcuts", "Utility", "Apple"),
    "com.apple.Translate": ("Translate", "Utility", "Apple"),
    "com.apple.reminders": ("Reminders", "Productivity", "Apple"),
    "com.apple.tv": ("Apple TV", "Video", "Apple"),
    "com.apple.news": ("News", "News", "Apple"),
    "com.apple.stocks": ("Stocks", "Finance", "Apple"),
    "com.apple.Wallet": ("Wallet", "Finance", "Apple"),
    "com.apple.Passbook": ("Wallet", "Finance", "Apple"),

    "com.king.candycrushsaga": ("Candy Crush Saga", "Game", "King"),
    "com.miHoYo.GenshinImpact": ("Genshin Impact", "Game", "miHoYo"),
    "com.mojang.minecraftpe": ("Minecraft", "Game", "Mojang"),
    "com.supercell.clashofclans": ("Clash of Clans", "Game", "Supercell"),
    "com.tencent.ig": ("PUBG Mobile", "Game", "Tencent"),
    "com.activision.callofduty.shooter": ("Call of Duty Mobile", "Game", "Activision"),

    "com.pinterest.iphone": ("Pinterest", "Social", "Pinterest"),
    "com.tencent.xin": ("WeChat", "Communication", "Tencent"),
    "com.kakao.talk": ("KakaoTalk", "Communication", "Kakao"),
    "jp.naver.line": ("LINE", "Communication", "LINE Corp"),
    "com.zoom.us.zoom": ("Zoom", "Video Conferencing", "Zoom"),
    "com.skype.skype": ("Skype", "Communication", "Microsoft"),
    "com.cisco.webex.webexmeetings": ("Webex", "Video Conferencing", "Cisco"),
    "us.zoom.videomeetings": ("Zoom", "Video Conferencing", "Zoom"),
    "com.google.GoogleMobile": ("Google", "Search", "Google"),
    "com.shazam.Shazam": ("Shazam", "Music", "Apple"),
    "com.duolingo.DuolingoMobile": ("Duolingo", "Education", "Duolingo"),
    "club.sharbatly": ("Sharbatly Club", "Lifestyle", "Sharbatly"),
    "com.devhd.feedly": ("Feedly", "News", "Feedly Inc"),
    "com.pocketcasts.app": ("Pocket Casts", "Audio", "Automattic"),
    "com.overcast.Overcast": ("Overcast", "Audio", "Overcast Radio"),
}


def _load_overrides() -> None:
    path = os.environ.get("PIXTRA_APP_CATALOG_FILE")
    if not path or not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        for bundle, val in data.items():
            if isinstance(val, (list, tuple)) and len(val) == 3:
                APP_CATALOG[bundle] = (str(val[0]), str(val[1]), str(val[2]))
    except Exception as e:
        logger.warning(f"Could not load app catalog overrides from {path}: {e}")


_load_overrides()


def lookup(bundle_id: Optional[str]) -> dict:
    if not bundle_id:
        return {
            "display_name": "",
            "category": "Unknown",
            "vendor": "",
            "is_known": False,
        }
    hit = APP_CATALOG.get(bundle_id)
    if hit:
        return {
            "display_name": hit[0],
            "category": hit[1],
            "vendor": hit[2],
            "is_known": True,
        }
    if bundle_id.startswith(("com.apple.", "com.apple",)):
        tail = bundle_id.split(".")[-1]
        pretty = tail.replace("-", " ").title()
        return {
            "display_name": pretty,
            "category": "System",
            "vendor": "Apple",
            "is_known": True,
        }
    return {
        "display_name": "",
        "category": "Unknown",
        "vendor": "",
        "is_known": False,
    }
