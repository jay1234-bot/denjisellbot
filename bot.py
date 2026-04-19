import asyncio
import io
import json
import logging
import os
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone, timedelta
from html import escape
from typing import Any, Dict, List, Optional

import qrcode
from PIL import Image

from telegram import (
    Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update, InputMediaPhoto
)
from telegram.ext import (
    Application, ApplicationBuilder, CallbackQueryHandler, CommandHandler,
    ConversationHandler, MessageHandler, ContextTypes, filters
)

# Prevent local "telethon.py" from shadowing the real telethon package.
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_ORIG_SYS_PATH = list(sys.path)
sys.path = [p for p in sys.path if os.path.abspath(p or ".") != _SCRIPT_DIR]
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError, FloodWaitError
sys.path = _ORIG_SYS_PATH

from pymongo import ASCENDING, MongoClient, ReturnDocument
from pymongo.errors import ConnectionFailure, PyMongoError, ServerSelectionTimeoutError

from i18n import (
    apply_custom_emoji_html,
    ibutton,
    ibutton_raw,
    sc,
    t,
    t_plain,
    welcome_default_template,
)

# ─── CONFIG ─────────────────────────────────────────────────────────────────
BOT_TOKEN = "8638333892:AAGNOYyLWE2KuQJF8gmCvVbkc-aP0tpVcBI"
ADMIN_IDS = [8746242371, 8333954027]
ADMIN_GROUP_ID = -1003564044316
# Successful buy logs will be sent here (set your channel/group id)
LOG_GROUP_ID = -1003929185913
STORE_BOT_USERNAME = "XR_OTP_BOT"
START_IMAGE_URL = "https://te.legra.ph/file/3e40a408286d4eda24191.jpg"
API_ID    = 22091901
API_HASH  = "54b0cd5fb47a40265b197f1a110b20b8"
UPI_ID = "maurya.xq@fam"
# Set MONGODB_URI in the environment to your Atlas connection string (do not commit secrets).
MONGODB_URI = os.environ.get("MONGODB_URI", "mongodb+srv://k05170492_db_user:xwiVDkW69VgeSSTE@cluster0.etkmxtd.mongodb.net/telegram_bot?retryWrites=true&w=majority").strip()
GITHUB_REPO_OWNER = os.environ.get("GITHUB_REPO_OWNER", "jay1234-bot")
GITHUB_REPO_NAME = os.environ.get("GITHUB_REPO_NAME", "denjisellbot")
GITHUB_DEFAULT_BRANCH = os.environ.get("GITHUB_DEFAULT_BRANCH", "main")
IST = timezone(timedelta(hours=5, minutes=30))

_mongo_client: Optional[MongoClient] = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── CONVERSATION STATES ────────────────────────────────────────────────────
(
    ADD_ACC_COUNTRY, ADD_ACC_PHONE, ADD_ACC_SESSION, ADD_ACC_2FA,
    DEPOSIT_UPI_AMOUNT, DEPOSIT_SCREENSHOT,
    BUY_SCREENSHOT,
    SET_PRICE_USDT, SET_PRICE_INR,
    BROADCAST_MSG, BROADCAST_CONFIRM,
    SEARCH_USER, EDIT_BALANCE,
    REMOVE_ACCOUNT,
    WELCOME_MSG_INPUT,
    INR_RATE_INPUT,
    ORDERS_SEARCH_ID,
    SET_PRICE_COUNTRY,
    ADMIN_ADD_COUNTRY_CODE,
) = range(19)

# ─── 120 COUNTRIES ──────────────────────────────────────────────────────────
COUNTRIES = [
    ("AF","Afghanistan","🇦🇫"), ("AL","Albania","🇦🇱"), ("DZ","Algeria","🇩🇿"),
    ("AD","Andorra","🇦🇩"), ("AO","Angola","🇦🇴"), ("AR","Argentina","🇦🇷"),
    ("AM","Armenia","🇦🇲"), ("AU","Australia","🇦🇺"), ("AT","Austria","🇦🇹"),
    ("AZ","Azerbaijan","🇦🇿"), ("BH","Bahrain","🇧🇭"), ("BD","Bangladesh","🇧🇩"),
    ("BY","Belarus","🇧🇾"), ("BE","Belgium","🇧🇪"), ("BZ","Belize","🇧🇿"),
    ("BJ","Benin","🇧🇯"), ("BT","Bhutan","🇧🇹"), ("BO","Bolivia","🇧🇴"),
    ("BA","Bosnia","🇧🇦"), ("BR","Brazil","🇧🇷"), ("BN","Brunei","🇧🇳"),
    ("BG","Bulgaria","🇧🇬"), ("KH","Cambodia","🇰🇭"), ("CM","Cameroon","🇨🇲"),
    ("CA","Canada","🇨🇦"), ("CL","Chile","🇨🇱"), ("CN","China","🇨🇳"),
    ("CO","Colombia","🇨🇴"), ("CD","Congo DRC","🇨🇩"), ("CR","Costa Rica","🇨🇷"),
    ("HR","Croatia","🇭🇷"), ("CU","Cuba","🇨🇺"), ("CY","Cyprus","🇨🇾"),
    ("CZ","Czech Republic","🇨🇿"), ("DK","Denmark","🇩🇰"), ("DO","Dominican Republic","🇩🇴"),
    ("EC","Ecuador","🇪🇨"), ("EG","Egypt","🇪🇬"), ("SV","El Salvador","🇸🇻"),
    ("EE","Estonia","🇪🇪"), ("ET","Ethiopia","🇪🇹"), ("FI","Finland","🇫🇮"),
    ("FR","France","🇫🇷"), ("GA","Gabon","🇬🇦"), ("GE","Georgia","🇬🇪"),
    ("DE","Germany","🇩🇪"), ("GH","Ghana","🇬🇭"), ("GR","Greece","🇬🇷"),
    ("GT","Guatemala","🇬🇹"), ("GN","Guinea","🇬🇳"), ("HT","Haiti","🇭🇹"),
    ("HN","Honduras","🇭🇳"), ("HK","Hong Kong","🇭🇰"), ("HU","Hungary","🇭🇺"),
    ("IS","Iceland","🇮🇸"), ("IN","India","🇮🇳"), ("ID","Indonesia","🇮🇩"),
    ("IR","Iran","🇮🇷"), ("IQ","Iraq","🇮🇶"), ("IE","Ireland","🇮🇪"),
    ("IL","Israel","🇮🇱"), ("IT","Italy","🇮🇹"), ("JM","Jamaica","🇯🇲"),
    ("JP","Japan","🇯🇵"), ("JO","Jordan","🇯🇴"), ("KZ","Kazakhstan","🇰🇿"),
    ("KE","Kenya","🇰🇪"), ("KW","Kuwait","🇰🇼"), ("KG","Kyrgyzstan","🇰🇬"),
    ("LA","Laos","🇱🇦"), ("LV","Latvia","🇱🇻"), ("LB","Lebanon","🇱🇧"),
    ("LY","Libya","🇱🇾"), ("LT","Lithuania","🇱🇹"), ("MY","Malaysia","🇲🇾"),
    ("MV","Maldives","🇲🇻"), ("ML","Mali","🇲🇱"), ("MT","Malta","🇲🇹"),
    ("MX","Mexico","🇲🇽"), ("MD","Moldova","🇲🇩"), ("MN","Mongolia","🇲🇳"),
    ("MA","Morocco","🇲🇦"), ("MZ","Mozambique","🇲🇿"), ("MM","Myanmar","🇲🇲"),
    ("NP","Nepal","🇳🇵"), ("NL","Netherlands","🇳🇱"), ("NZ","New Zealand","🇳🇿"),
    ("NI","Nicaragua","🇳🇮"), ("NE","Niger","🇳🇪"), ("NG","Nigeria","🇳🇬"),
    ("KP","North Korea","🇰🇵"), ("NO","Norway","🇳🇴"), ("OM","Oman","🇴🇲"),
    ("PK","Pakistan","🇵🇰"), ("PS","Palestine","🇵🇸"), ("PA","Panama","🇵🇦"),
    ("PY","Paraguay","🇵🇾"), ("PE","Peru","🇵🇪"), ("PH","Philippines","🇵🇭"),
    ("PL","Poland","🇵🇱"), ("PT","Portugal","🇵🇹"), ("QA","Qatar","🇶🇦"),
    ("RO","Romania","🇷🇴"), ("RU","Russia","🇷🇺"), ("RW","Rwanda","🇷🇼"),
    ("SA","Saudi Arabia","🇸🇦"), ("SN","Senegal","🇸🇳"), ("RS","Serbia","🇷🇸"),
    ("SG","Singapore","🇸🇬"), ("SK","Slovakia","🇸🇰"), ("SI","Slovenia","🇸🇮"),
    ("SO","Somalia","🇸🇴"), ("ZA","South Africa","🇿🇦"), ("KR","South Korea","🇰🇷"),
    ("ES","Spain","🇪🇸"), ("LK","Sri Lanka","🇱🇰"), ("SD","Sudan","🇸🇩"),
    ("SE","Sweden","🇸🇪"), ("CH","Switzerland","🇨🇭"), ("SY","Syria","🇸🇾"),
    ("TW","Taiwan","🇹🇼"), ("TJ","Tajikistan","🇹🇯"), ("TZ","Tanzania","🇹🇿"),
    ("TH","Thailand","🇹🇭"), ("TN","Tunisia","🇹🇳"), ("TR","Turkey","🇹🇷"),
    ("TM","Turkmenistan","🇹🇲"), ("UG","Uganda","🇺🇬"), ("UA","Ukraine","🇺🇦"),
    ("AE","UAE","🇦🇪"), ("GB","United Kingdom","🇬🇧"), ("US","United States","🇺🇸"),
    ("UY","Uruguay","🇺🇾"), ("UZ","Uzbekistan","🇺🇿"), ("VE","Venezuela","🇻🇪"),
    ("VN","Vietnam","🇻🇳"), ("YE","Yemen","🇾🇪"), ("ZM","Zambia","🇿🇲"),
    ("ZW","Zimbabwe","🇿🇼"),
]

# ─── DIALING CODE → COUNTRY MAP ──────────────────────────────────────────────
DIALING_CODE_MAP = {
    "1868": ("TT","Trinidad and Tobago","🇹🇹"),
    "1876": ("JM","Jamaica","🇯🇲"),
    "1784": ("VC","St. Vincent","🇻🇨"),
    "1767": ("DM","Dominica","🇩🇲"),
    "1758": ("LC","Saint Lucia","🇱🇨"),
    "1721": ("SX","Sint Maarten","🇸🇽"),
    "1670": ("MP","Northern Mariana Islands","🇲🇵"),
    "1664": ("MS","Montserrat","🇲🇸"),
    "1649": ("TC","Turks and Caicos","🇹🇨"),
    "1473": ("GD","Grenada","🇬🇩"),
    "1441": ("BM","Bermuda","🇧🇲"),
    "1345": ("KY","Cayman Islands","🇰🇾"),
    "1340": ("VI","U.S. Virgin Islands","🇻🇮"),
    "1284": ("VG","British Virgin Islands","🇻🇬"),
    "1268": ("AG","Antigua and Barbuda","🇦🇬"),
    "1246": ("BB","Barbados","🇧🇧"),
    "1242": ("BS","Bahamas","🇧🇸"),
    "998": ("UZ","Uzbekistan","🇺🇿"),
    "996": ("KG","Kyrgyzstan","🇰🇬"),
    "995": ("GE","Georgia","🇬🇪"),
    "994": ("AZ","Azerbaijan","🇦🇿"),
    "993": ("TM","Turkmenistan","🇹🇲"),
    "992": ("TJ","Tajikistan","🇹🇯"),
    "977": ("NP","Nepal","🇳🇵"),
    "976": ("MN","Mongolia","🇲🇳"),
    "975": ("BT","Bhutan","🇧🇹"),
    "974": ("QA","Qatar","🇶🇦"),
    "973": ("BH","Bahrain","🇧🇭"),
    "972": ("IL","Israel","🇮🇱"),
    "971": ("AE","UAE","🇦🇪"),
    "970": ("PS","Palestine","🇵🇸"),
    "968": ("OM","Oman","🇴🇲"),
    "967": ("YE","Yemen","🇾🇪"),
    "966": ("SA","Saudi Arabia","🇸🇦"),
    "965": ("KW","Kuwait","🇰🇼"),
    "964": ("IQ","Iraq","🇮🇶"),
    "963": ("SY","Syria","🇸🇾"),
    "962": ("JO","Jordan","🇯🇴"),
    "961": ("LB","Lebanon","🇱🇧"),
    "960": ("MV","Maldives","🇲🇻"),
    "886": ("TW","Taiwan","🇹🇼"),
    "880": ("BD","Bangladesh","🇧🇩"),
    "856": ("LA","Laos","🇱🇦"),
    "855": ("KH","Cambodia","🇰🇭"),
    "853": ("MO","Macau","🇲🇴"),
    "852": ("HK","Hong Kong","🇭🇰"),
    "850": ("KP","North Korea","🇰🇵"),
    "673": ("BN","Brunei","🇧🇳"),
    "670": ("TL","East Timor","🇹🇱"),
    "509": ("HT","Haiti","🇭🇹"),
    "507": ("PA","Panama","🇵🇦"),
    "506": ("CR","Costa Rica","🇨🇷"),
    "505": ("NI","Nicaragua","🇳🇮"),
    "504": ("HN","Honduras","🇭🇳"),
    "503": ("SV","El Salvador","🇸🇻"),
    "502": ("GT","Guatemala","🇬🇹"),
    "501": ("BZ","Belize","🇧🇿"),
    "423": ("LI","Liechtenstein","🇱🇮"),
    "421": ("SK","Slovakia","🇸🇰"),
    "420": ("CZ","Czech Republic","🇨🇿"),
    "389": ("MK","North Macedonia","🇲🇰"),
    "387": ("BA","Bosnia","🇧🇦"),
    "386": ("SI","Slovenia","🇸🇮"),
    "385": ("HR","Croatia","🇭🇷"),
    "383": ("XK","Kosovo","🇽🇰"),
    "382": ("ME","Montenegro","🇲🇪"),
    "381": ("RS","Serbia","🇷🇸"),
    "380": ("UA","Ukraine","🇺🇦"),
    "378": ("SM","San Marino","🇸🇲"),
    "377": ("MC","Monaco","🇲🇨"),
    "376": ("AD","Andorra","🇦🇩"),
    "375": ("BY","Belarus","🇧🇾"),
    "374": ("AM","Armenia","🇦🇲"),
    "373": ("MD","Moldova","🇲🇩"),
    "372": ("EE","Estonia","🇪🇪"),
    "371": ("LV","Latvia","🇱🇻"),
    "370": ("LT","Lithuania","🇱🇹"),
    "269": ("KM","Comoros","🇰🇲"),
    "268": ("SZ","Eswatini","🇸🇿"),
    "267": ("BW","Botswana","🇧🇼"),
    "266": ("LS","Lesotho","🇱🇸"),
    "265": ("MW","Malawi","🇲🇼"),
    "264": ("NA","Namibia","🇳🇦"),
    "263": ("ZW","Zimbabwe","🇿🇼"),
    "262": ("RE","Réunion","🇷🇪"),
    "261": ("MG","Madagascar","🇲🇬"),
    "260": ("ZM","Zambia","🇿🇲"),
    "258": ("MZ","Mozambique","🇲🇿"),
    "257": ("BI","Burundi","🇧🇮"),
    "256": ("UG","Uganda","🇺🇬"),
    "255": ("TZ","Tanzania","🇹🇿"),
    "254": ("KE","Kenya","🇰🇪"),
    "253": ("DJ","Djibouti","🇩🇯"),
    "252": ("SO","Somalia","🇸🇴"),
    "251": ("ET","Ethiopia","🇪🇹"),
    "250": ("RW","Rwanda","🇷🇼"),
    "249": ("SD","Sudan","🇸🇩"),
    "248": ("SC","Seychelles","🇸🇨"),
    "247": ("AC","Ascension Island","🇦🇨"),
    "246": ("IO","British Indian Ocean Territory","🇮🇴"),
    "245": ("GW","Guinea-Bissau","🇬🇼"),
    "244": ("AO","Angola","🇦🇴"),
    "243": ("CD","Congo DRC","🇨🇩"),
    "242": ("CG","Republic of Congo","🇨🇬"),
    "241": ("GA","Gabon","🇬🇦"),
    "240": ("GQ","Equatorial Guinea","🇬🇶"),
    "239": ("ST","São Tomé and Príncipe","🇸🇹"),
    "238": ("CV","Cape Verde","🇨🇻"),
    "237": ("CM","Cameroon","🇨🇲"),
    "236": ("CF","Central African Republic","🇨🇫"),
    "235": ("TD","Chad","🇹🇩"),
    "234": ("NG","Nigeria","🇳🇬"),
    "233": ("GH","Ghana","🇬🇭"),
    "232": ("SL","Sierra Leone","🇸🇱"),
    "231": ("LR","Liberia","🇱🇷"),
    "230": ("MU","Mauritius","🇲🇺"),
    "229": ("BJ","Benin","🇧🇯"),
    "228": ("TG","Togo","🇹🇬"),
    "227": ("NE","Niger","🇳🇪"),
    "226": ("BF","Burkina Faso","🇧🇫"),
    "225": ("CI","Ivory Coast","🇨🇮"),
    "224": ("GN","Guinea","🇬🇳"),
    "223": ("ML","Mali","🇲🇱"),
    "222": ("MR","Mauritania","🇲🇷"),
    "221": ("SN","Senegal","🇸🇳"),
    "220": ("GM","Gambia","🇬🇲"),
    "218": ("LY","Libya","🇱🇾"),
    "216": ("TN","Tunisia","🇹🇳"),
    "213": ("DZ","Algeria","🇩🇿"),
    "212": ("MA","Morocco","🇲🇦"),
    "98":  ("IR","Iran","🇮🇷"),
    "95":  ("MM","Myanmar","🇲🇲"),
    "94":  ("LK","Sri Lanka","🇱🇰"),
    "93":  ("AF","Afghanistan","🇦🇫"),
    "92":  ("PK","Pakistan","🇵🇰"),
    "91":  ("IN","India","🇮🇳"),
    "90":  ("TR","Turkey","🇹🇷"),
    "86":  ("CN","China","🇨🇳"),
    "84":  ("VN","Vietnam","🇻🇳"),
    "82":  ("KR","South Korea","🇰🇷"),
    "81":  ("JP","Japan","🇯🇵"),
    "66":  ("TH","Thailand","🇹🇭"),
    "65":  ("SG","Singapore","🇸🇬"),
    "64":  ("NZ","New Zealand","🇳🇿"),
    "63":  ("PH","Philippines","🇵🇭"),
    "62":  ("ID","Indonesia","🇮🇩"),
    "61":  ("AU","Australia","🇦🇺"),
    "60":  ("MY","Malaysia","🇲🇾"),
    "58":  ("VE","Venezuela","🇻🇪"),
    "57":  ("CO","Colombia","🇨🇴"),
    "56":  ("CL","Chile","🇨🇱"),
    "55":  ("BR","Brazil","🇧🇷"),
    "54":  ("AR","Argentina","🇦🇷"),
    "53":  ("CU","Cuba","🇨🇺"),
    "52":  ("MX","Mexico","🇲🇽"),
    "51":  ("PE","Peru","🇵🇪"),
    "49":  ("DE","Germany","🇩🇪"),
    "48":  ("PL","Poland","🇵🇱"),
    "47":  ("NO","Norway","🇳🇴"),
    "46":  ("SE","Sweden","🇸🇪"),
    "45":  ("DK","Denmark","🇩🇰"),
    "44":  ("GB","United Kingdom","🇬🇧"),
    "43":  ("AT","Austria","🇦🇹"),
    "41":  ("CH","Switzerland","🇨🇭"),
    "40":  ("RO","Romania","🇷🇴"),
    "39":  ("IT","Italy","🇮🇹"),
    "36":  ("HU","Hungary","🇭🇺"),
    "34":  ("ES","Spain","🇪🇸"),
    "33":  ("FR","France","🇫🇷"),
    "32":  ("BE","Belgium","🇧🇪"),
    "31":  ("NL","Netherlands","🇳🇱"),
    "30":  ("GR","Greece","🇬🇷"),
    "27":  ("ZA","South Africa","🇿🇦"),
    "20":  ("EG","Egypt","🇪🇬"),
    "7":   ("RU","Russia","🇷🇺"),
    "1":   ("US","United States","🇺🇸"),
}

def lookup_dialing_code(raw: str):
    digits = raw.strip().lstrip("+").strip()
    for length in (4, 3, 2, 1):
        prefix = digits[:length]
        if prefix in DIALING_CODE_MAP:
            return DIALING_CODE_MAP[prefix]
    return None

# ─── DATABASE (MongoDB) ───────────────────────────────────────────────────────
_mongo_tls_workaround_installed = False
_socket_getaddrinfo_orig: Any = None


def _coerce_tls12_on_ssl_context(ctx: Any) -> Any:
    """Harden PyMongo SSL contexts for Atlas from Docker/VPS (TLS 1.2, cipher policy)."""
    if ctx is None:
        return None
    import ssl as stdssl

    if isinstance(ctx, stdssl.SSLContext):
        if hasattr(stdssl, "TLSVersion"):
            try:
                ctx.minimum_version = stdssl.TLSVersion.TLSv1_2
                ctx.maximum_version = stdssl.TLSVersion.TLSv1_2
            except (ValueError, OSError, AttributeError):
                pass
        try:
            ctx.set_ciphers("DEFAULT:@SECLEVEL=1")
        except (ValueError, OSError, AttributeError):
            pass
        return ctx
    inner = getattr(ctx, "_ctx", None)
    if inner is not None:
        try:
            from OpenSSL import SSL as ossl

            if hasattr(ossl, "OP_NO_TLSv1_3"):
                inner.set_options(ossl.OP_NO_TLSv1_3)
        except Exception:
            pass
    return ctx


def _install_mongo_tls_workaround() -> None:
    """Patch PyMongo's SSL context factory (imported by name in client_options, not only ssl_support)."""
    global _mongo_tls_workaround_installed
    if _mongo_tls_workaround_installed:
        return
    if os.environ.get("MONGODB_TLS_NO_WORKAROUND", "").strip().lower() in ("1", "true", "yes"):
        return

    import pymongo.client_options as mco
    import pymongo.ssl_support as mss

    orig = mss.get_ssl_context

    def get_ssl_context_wrapped(*args: Any, **kwargs: Any) -> Any:
        return _coerce_tls12_on_ssl_context(orig(*args, **kwargs))

    mss.get_ssl_context = get_ssl_context_wrapped
    mco.get_ssl_context = get_ssl_context_wrapped
    import importlib

    for mod_name in ("pymongo.synchronous.encryption", "pymongo.asynchronous.encryption"):
        try:
            mod = importlib.import_module(mod_name)
            if hasattr(mod, "get_ssl_context"):
                setattr(mod, "get_ssl_context", get_ssl_context_wrapped)
        except Exception:
            pass

    _mongo_tls_workaround_installed = True
    logger.info("MongoDB TLS: SSL context workaround active (set MONGODB_TLS_NO_WORKAROUND=1 to disable).")


def _install_mongo_socket_ipv4_for_atlas() -> None:
    """Force IPv4 for *.mongodb.net — broken IPv6 routes on VPS often show up as TLSV1_ALERT_INTERNAL_ERROR."""
    global _socket_getaddrinfo_orig
    if _socket_getaddrinfo_orig is not None:
        return
    if os.environ.get("MONGODB_ALLOW_IPV6", "").strip().lower() in ("1", "true", "yes"):
        return

    import socket

    _socket_getaddrinfo_orig = socket.getaddrinfo

    def getaddrinfo_ipv4_for_atlas(
        host: Any,
        port: Any,
        family: int = 0,
        type: int = 0,
        proto: int = 0,
        flags: int = 0,
    ) -> Any:
        if isinstance(host, str) and ".mongodb.net" in host:
            if family in (0, socket.AF_UNSPEC):
                family = socket.AF_INET
        return _socket_getaddrinfo_orig(host, port, family, type, proto, flags)

    socket.getaddrinfo = getaddrinfo_ipv4_for_atlas  # type: ignore[method-assign]
    logger.info("MongoDB: forcing IPv4 for *.mongodb.net (set MONGODB_ALLOW_IPV6=1 to use IPv6 too).")


def _mongo_client_kwargs() -> Dict[str, Any]:
    """TLS options for Atlas from Docker/VPS (CA bundle, OCSP, timeouts)."""
    opts: Dict[str, Any] = {"serverSelectionTimeoutMS": 45_000}
    ca_env = os.environ.get("MONGODB_TLS_CA_FILE", "").strip()
    if ca_env and os.path.isfile(ca_env):
        opts["tlsCAFile"] = ca_env
    else:
        try:
            import certifi

            opts["tlsCAFile"] = certifi.where()
        except ImportError:
            pass
    if os.environ.get("MONGODB_TLS_STRICT", "").strip().lower() not in ("1", "true", "yes"):
        opts["tlsDisableOCSPEndpointCheck"] = True
    if os.environ.get("MONGODB_TLS_INSECURE", "").strip().lower() in ("1", "true", "yes"):
        opts["tlsInsecure"] = True
        logger.warning(
            "MONGODB_TLS_INSECURE is set — TLS verification is relaxed. Fix the host CA/TLS stack and unset this."
        )
    return opts


def get_mongo_client() -> MongoClient:
    global _mongo_client
    if not MONGODB_URI:
        raise RuntimeError(
            "MONGODB_URI is not set. Set the environment variable to your MongoDB connection string "
            "(e.g. mongodb+srv://user:pass@cluster/telegram_bot?retryWrites=true&w=majority)."
        )
    if _mongo_client is None:
        _install_mongo_tls_workaround()
        _install_mongo_socket_ipv4_for_atlas()
        base_opts = _mongo_client_kwargs()
        extra_opts_list: List[Dict[str, Any]] = [{}]
        if os.environ.get("MONGODB_NO_TLS_FALLBACK", "").strip().lower() not in ("1", "true", "yes"):
            extra_opts_list.append({"tlsInsecure": True})

        last_err: Optional[BaseException] = None
        for i, extra in enumerate(extra_opts_list):
            if extra.get("tlsInsecure"):
                logger.warning(
                    "MongoDB: retrying with tlsInsecure=True after TLS failure (MITM risk — "
                    "set MONGODB_NO_TLS_FALLBACK=1 to disable this fallback once the network is fixed)."
                )
            client: Optional[MongoClient] = None
            try:
                client = MongoClient(MONGODB_URI, **{**base_opts, **extra})
                client.admin.command("ping")
                _mongo_client = client
                return _mongo_client
            except (ServerSelectionTimeoutError, ConnectionFailure) as e:
                last_err = e
                if client is not None:
                    try:
                        client.close()
                    except Exception:
                        pass
                msg = str(e).lower()
                if i < len(extra_opts_list) - 1 and ("ssl" in msg or "tls" in msg):
                    continue
                raise
        if last_err is not None:
            raise last_err
        raise RuntimeError("MongoDB: could not establish client")
    return _mongo_client


def get_mongo():
    return get_mongo_client().get_default_database()


def next_seq(counter_name: str) -> int:
    doc = get_mongo().counters.find_one_and_update(
        {"_id": counter_name},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return int(doc["seq"])


def init_db():
    db = get_mongo()
    db.countries.create_index("code", unique=True)
    db.users.create_index("id", unique=True)
    db.accounts.create_index([("country_code", ASCENDING), ("is_sold", ASCENDING)])
    db.orders.create_index("user_id")
    db.orders.create_index("status")
    db.deposits.create_index("user_id")
    db.deposits.create_index("status")

    if db.countries.estimated_document_count() == 0:
        for i, (code, name, flag) in enumerate(COUNTRIES, 1):
            db.countries.insert_one(
                {
                    "_id": code,
                    "id": i,
                    "code": code,
                    "name": name,
                    "flag": flag,
                    "price_inr": 0.0,
                    "enabled": 1,
                }
            )

    db.settings.update_one({"_id": "maintenance"}, {"$setOnInsert": {"value": "0"}}, upsert=True)
    new_welcome = welcome_default_template()
    db.settings.update_one(
        {"_id": "welcome_message"},
        {"$setOnInsert": {"value": new_welcome}},
        upsert=True,
    )
    wm = db.settings.find_one({"_id": "welcome_message"})
    old_defaults = {
        "🏪 Welcome to NumberStore!\nBuy verified phone numbers instantly.\nFast • Secure • 24/7",
        "🏪 Welcome to NumberStore!",
    }
    if wm and wm.get("value") in old_defaults:
        db.settings.update_one({"_id": "welcome_message"}, {"$set": {"value": new_welcome}})


# ─── HELPERS ─────────────────────────────────────────────────────────────────
def now_ist():
    return datetime.now(IST)


def fmt_time(ts_str):
    if not ts_str:
        return "N/A"
    try:
        dt = datetime.fromisoformat(str(ts_str))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(IST).strftime("%d %b %Y %H:%M IST")
    except Exception:
        return str(ts_str)


def get_setting(key, default=""):
    doc = get_mongo().settings.find_one({"_id": key})
    return doc["value"] if doc and "value" in doc else default


def set_setting(key, value):
    get_mongo().settings.update_one(
        {"_id": key},
        {"$set": {"value": str(value)}},
        upsert=True,
    )


def register_user(user):
    db = get_mongo()
    now = now_ist().isoformat()
    db.users.update_one(
        {"id": user.id},
        {
            "$set": {"username": user.username or "", "first_name": user.first_name or ""},
            "$setOnInsert": {
                "id": user.id,
                "is_banned": 0,
                "total_purchases": 0,
                "wallet_balance": 0.0,
                "joined_at": now,
            },
        },
        upsert=True,
    )


def is_banned(user_id):
    doc = get_mongo().users.find_one({"id": user_id})
    return bool(doc and doc.get("is_banned") == 1)


def is_maintenance():
    return get_setting("maintenance", "0") == "1"


def is_admin(user_id):
    return user_id in ADMIN_IDS


def check_access(user_id):
    if is_banned(user_id):
        return t_plain("access.banned")
    if is_maintenance() and not is_admin(user_id):
        return t_plain("access.maintenance")
    return None


def get_country(code):
    doc = get_mongo().countries.find_one({"code": code})
    return dict(doc) if doc else None


def get_stock_count(code):
    return get_mongo().accounts.count_documents({"country_code": code, "is_sold": 0})


def list_browse_countries() -> List[Dict[str, Any]]:
    db = get_mongo()
    out = []
    for c in db.countries.find({"enabled": 1}).sort("name", ASCENDING):
        stock = db.accounts.count_documents({"country_code": c["code"], "is_sold": 0})
        if stock > 0:
            row = dict(c)
            row["stock_count"] = stock
            out.append(row)
    return out


def ensure_country_row(code: str, name: str, flag: str) -> Dict[str, Any]:
    db = get_mongo()
    existing = db.countries.find_one({"code": code})
    if existing:
        return dict(existing)
    max_doc = db.countries.find_one(sort=[("id", -1)])
    next_id = (max_doc["id"] if max_doc and max_doc.get("id") is not None else 0) + 1
    doc = {
        "_id": code,
        "id": next_id,
        "code": code,
        "name": name,
        "flag": flag,
        "price_inr": 0.0,
        "enabled": 1,
    }
    db.countries.insert_one(doc)
    return dict(doc)


def count_accounts_for_country(code: str) -> int:
    return get_mongo().accounts.count_documents({"country_code": code})


def insert_account(
    country_code: str,
    phone_number: str,
    session_string: str,
    two_fa_password: Optional[str],
    added_by: int,
    added_at: str,
) -> int:
    db = get_mongo()
    aid = next_seq("accounts")
    db.accounts.insert_one(
        {
            "_id": aid,
            "id": aid,
            "country_code": country_code,
            "phone_number": phone_number,
            "session_string": session_string,
            "two_fa_password": two_fa_password,
            "is_sold": 0,
            "sold_to": None,
            "sold_at": None,
            "added_by": added_by,
            "added_at": added_at,
        }
    )
    return aid


def delete_account_by_id(acc_id: int) -> None:
    get_mongo().accounts.delete_one({"_id": acc_id})


def find_account_by_phone_or_id(query_val: str) -> Optional[Dict[str, Any]]:
    db = get_mongo()
    if query_val.startswith("+"):
        doc = db.accounts.find_one({"phone_number": query_val.lstrip("+")})
        return dict(doc) if doc else None
    try:
        doc = db.accounts.find_one({"_id": int(query_val)})
    except ValueError:
        return None
    return dict(doc) if doc else None


def get_user_row(user_id: int) -> Optional[Dict[str, Any]]:
    doc = get_mongo().users.find_one({"id": user_id})
    return dict(doc) if doc else None


def get_wallet_balance(user_id: int) -> float:
    row = get_user_row(user_id)
    return float(row["wallet_balance"]) if row else 0.0


def wallet_buy_transaction(user_id: int, username: str, code: str, price: float) -> Optional[int]:
    """
    Atomically sell one account and debit wallet. Returns new order_id or None if failed.
    """
    db = get_mongo()
    client = get_mongo_client()
    now = now_ist().isoformat()
    try:
        with client.start_session() as session:
            with session.start_transaction():
                acc = db.accounts.find_one_and_update(
                    {"country_code": code, "is_sold": 0},
                    {"$set": {"is_sold": 1, "sold_to": user_id, "sold_at": now}},
                    sort=[("_id", ASCENDING)],
                    return_document=ReturnDocument.BEFORE,
                    session=session,
                )
                if not acc:
                    return None
                res = db.users.update_one(
                    {"id": user_id, "wallet_balance": {"$gte": price}},
                    {"$inc": {"wallet_balance": -price, "total_purchases": 1}},
                    session=session,
                )
                if res.modified_count != 1:
                    raise RuntimeError("wallet")
                oid = next_seq("orders")
                db.orders.insert_one(
                    {
                        "_id": oid,
                        "id": oid,
                        "user_id": user_id,
                        "username": username or "",
                        "account_id": acc["_id"],
                        "country_code": code,
                        "amount_inr": price,
                        "payment_method": "wallet",
                        "payment_screenshot": None,
                        "status": "approved",
                        "created_at": now,
                        "reviewed_by": None,
                        "reviewed_at": now,
                    },
                    session=session,
                )
                return oid
    except PyMongoError:
        logger.exception("wallet_buy_transaction")
        return None
    except RuntimeError:
        return None


def insert_pending_order(
    user_id: int,
    username: str,
    code: str,
    amount_inr: float,
    file_id: str,
    created_at: str,
) -> int:
    db = get_mongo()
    oid = next_seq("orders")
    db.orders.insert_one(
        {
            "_id": oid,
            "id": oid,
            "user_id": user_id,
            "username": username or "",
            "account_id": None,
            "country_code": code,
            "amount_inr": amount_inr,
            "payment_method": "upi",
            "payment_screenshot": file_id,
            "status": "pending",
            "created_at": created_at,
            "reviewed_by": None,
            "reviewed_at": None,
        }
    )
    return oid


def insert_pending_deposit(user_id: int, amount_inr: float, file_id: str, created_at: str) -> int:
    db = get_mongo()
    did = next_seq("deposits")
    db.deposits.insert_one(
        {
            "_id": did,
            "id": did,
            "user_id": user_id,
            "amount_inr": amount_inr,
            "payment_method": "upi",
            "screenshot": file_id,
            "status": "pending",
            "created_at": created_at,
            "reviewed_by": None,
            "reviewed_at": None,
        }
    )
    return did


def get_order_for_user(order_id: int, user_id: int) -> Optional[Dict[str, Any]]:
    doc = get_mongo().orders.find_one({"_id": order_id, "user_id": user_id})
    return dict(doc) if doc else None


def get_order_by_id(order_id: int) -> Optional[Dict[str, Any]]:
    doc = get_mongo().orders.find_one({"_id": order_id})
    return dict(doc) if doc else None


def get_account_by_id(acc_id: int) -> Optional[Dict[str, Any]]:
    doc = get_mongo().accounts.find_one({"_id": acc_id})
    return dict(doc) if doc else None


def order_id_for_account(acc_id: int) -> int:
    doc = get_mongo().orders.find_one({"account_id": acc_id, "status": "approved"})
    return int(doc["_id"]) if doc else 0


def orders_for_user(user_id: int) -> List[Dict[str, Any]]:
    db = get_mongo()
    cur = db.orders.find({"user_id": user_id}).sort("created_at", -1)
    rows = []
    for o in cur:
        d = dict(o)
        ch = get_country(d.get("country_code") or "")
        d["flag"] = ch["flag"] if ch else None
        d["cname"] = ch["name"] if ch else None
        rows.append(d)
    return rows


def deposits_for_user(user_id: int) -> List[Dict[str, Any]]:
    return [dict(x) for x in get_mongo().deposits.find({"user_id": user_id}).sort("created_at", -1)]


def approve_order_transaction(order_id: int, reviewer_id: int) -> Optional[Dict[str, Any]]:
    """
    Returns dict with keys: order, acc, country_code or None.
    """
    db = get_mongo()
    client = get_mongo_client()
    now = now_ist().isoformat()
    try:
        with client.start_session() as session:
            with session.start_transaction():
                order = db.orders.find_one({"_id": order_id, "status": "pending"}, session=session)
                if not order:
                    return None
                code = order["country_code"]
                acc = db.accounts.find_one_and_update(
                    {"country_code": code, "is_sold": 0},
                    {"$set": {"is_sold": 1, "sold_to": order["user_id"], "sold_at": now}},
                    sort=[("_id", ASCENDING)],
                    return_document=ReturnDocument.BEFORE,
                    session=session,
                )
                if not acc:
                    raise RuntimeError("no_stock")
                db.orders.update_one(
                    {"_id": order_id},
                    {
                        "$set": {
                            "status": "approved",
                            "account_id": acc["_id"],
                            "reviewed_by": reviewer_id,
                            "reviewed_at": now,
                        }
                    },
                    session=session,
                )
                db.users.update_one(
                    {"id": order["user_id"]},
                    {"$inc": {"total_purchases": 1}},
                    session=session,
                )
                return {"order": dict(order), "acc": dict(acc), "country_code": code}
    except PyMongoError:
        logger.exception("approve_order_transaction")
        return None
    except RuntimeError:
        return None


def reject_order_db(order_id: int, reviewer_id: int) -> Optional[Dict[str, Any]]:
    db = get_mongo()
    now = now_ist().isoformat()
    order = db.orders.find_one({"_id": order_id, "status": "pending"})
    if not order:
        return None
    db.orders.update_one(
        {"_id": order_id},
        {"$set": {"status": "rejected", "reviewed_by": reviewer_id, "reviewed_at": now}},
    )
    return dict(order)


def get_deposit_by_id(dep_id: int) -> Optional[Dict[str, Any]]:
    doc = get_mongo().deposits.find_one({"_id": dep_id})
    return dict(doc) if doc else None


def approve_deposit_db(dep_id: int, reviewer_id: int) -> Optional[Dict[str, Any]]:
    db = get_mongo()
    now = now_ist().isoformat()
    dep = db.deposits.find_one({"_id": dep_id, "status": "pending"})
    if not dep:
        return None
    db.deposits.update_one(
        {"_id": dep_id},
        {"$set": {"status": "approved", "reviewed_by": reviewer_id, "reviewed_at": now}},
    )
    db.users.update_one({"id": dep["user_id"]}, {"$inc": {"wallet_balance": dep["amount_inr"]}})
    return dict(dep)


def reject_deposit_db(dep_id: int, reviewer_id: int) -> Optional[Dict[str, Any]]:
    db = get_mongo()
    now = now_ist().isoformat()
    dep = db.deposits.find_one({"_id": dep_id, "status": "pending"})
    if not dep:
        return None
    db.deposits.update_one(
        {"_id": dep_id},
        {"$set": {"status": "rejected", "reviewed_by": reviewer_id, "reviewed_at": now}},
    )
    return dict(dep)


def list_countries_sorted() -> List[Dict[str, Any]]:
    return [dict(c) for c in get_mongo().countries.find().sort("name", ASCENDING)]


def set_country_price(code: str, price_inr: float) -> None:
    get_mongo().countries.update_one({"code": code}, {"$set": {"price_inr": price_inr}})


def toggle_country_enabled(code: str) -> None:
    db = get_mongo()
    row = db.countries.find_one({"code": code})
    if not row:
        return
    new_val = 0 if row.get("enabled") else 1
    db.countries.update_one({"code": code}, {"$set": {"enabled": new_val}})


def orders_admin_list(status_filter: str) -> List[Dict[str, Any]]:
    db = get_mongo()
    q: Dict[str, Any] = {}
    if status_filter != "all":
        q["status"] = status_filter
    cur = db.orders.find(q).sort("created_at", -1)
    rows = []
    for o in cur:
        d = dict(o)
        ch = get_country(d.get("country_code") or "")
        d["flag"] = ch["flag"] if ch else None
        d["cname"] = ch["name"] if ch else None
        rows.append(d)
    return rows


def ban_user(uid: int) -> None:
    get_mongo().users.update_one({"id": uid}, {"$set": {"is_banned": 1}})


def unban_user(uid: int) -> None:
    get_mongo().users.update_one({"id": uid}, {"$set": {"is_banned": 0}})


def adjust_wallet(uid: int, delta: float) -> float:
    db = get_mongo()
    db.users.update_one({"id": uid}, {"$inc": {"wallet_balance": delta}})
    row = db.users.find_one({"id": uid})
    return float(row["wallet_balance"]) if row else 0.0


def deposits_admin_list(status_filter: str) -> List[Dict[str, Any]]:
    db = get_mongo()
    q: Dict[str, Any] = {}
    if status_filter != "all":
        q["status"] = status_filter
    return [dict(x) for x in db.deposits.find(q).sort("created_at", -1)]


def admin_stats_row() -> Dict[str, Any]:
    db = get_mongo()
    total_users = db.users.count_documents({})
    total_stock = db.accounts.count_documents({})
    avail_stock = db.accounts.count_documents({"is_sold": 0})
    sold = db.accounts.count_documents({"is_sold": 1})
    agg = list(db.orders.aggregate([{"$match": {"status": "approved"}}, {"$group": {"_id": None, "s": {"$sum": "$amount_inr"}}}]))
    revenue = float(agg[0]["s"]) if agg else 0.0
    pending_orders = db.orders.count_documents({"status": "pending"})
    pending_deps = db.deposits.count_documents({"status": "pending"})
    banned = db.users.count_documents({"is_banned": 1})
    return {
        "total_users": total_users,
        "total_stock": total_stock,
        "avail_stock": avail_stock,
        "sold": sold,
        "revenue": revenue,
        "pending_orders": pending_orders,
        "pending_deps": pending_deps,
        "banned": banned,
    }


def broadcast_recipient_ids() -> List[int]:
    return [d["id"] for d in get_mongo().users.find({"is_banned": {"$ne": 1}}, {"id": 1})]


def count_active_users() -> int:
    return get_mongo().users.count_documents({"is_banned": {"$ne": 1}})


def find_user_by_id_or_username(query_val: str) -> Optional[Dict[str, Any]]:
    db = get_mongo()
    try:
        uid = int(query_val)
        doc = db.users.find_one({"id": uid})
    except ValueError:
        doc = db.users.find_one({"username": query_val})
    return dict(doc) if doc else None


def _github_api_url() -> str:
    return (
        f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/"
        f"commits/{GITHUB_DEFAULT_BRANCH}"
    )


def _github_raw_bot_url() -> str:
    return (
        f"https://raw.githubusercontent.com/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/"
        f"{GITHUB_DEFAULT_BRANCH}/bot.py"
    )


def fetch_github_latest_sha() -> str:
    req = urllib.request.Request(_github_api_url(), headers={"User-Agent": "NumberStoreBot/1.0"})
    with urllib.request.urlopen(req, timeout=45) as resp:
        data = json.loads(resp.read().decode())
    return str(data.get("sha") or "")


async def _async_git_pull_and_head() -> str:
    proc = await asyncio.create_subprocess_exec(
        "git", "-C", _SCRIPT_DIR, "pull", "--ff-only",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        err = (stderr or stdout or b"").decode("utf-8", errors="replace").strip()
        raise RuntimeError(err or "git pull failed")
    proc2 = await asyncio.create_subprocess_exec(
        "git", "-C", _SCRIPT_DIR, "rev-parse", "HEAD",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out2, err2 = await proc2.communicate()
    if proc2.returncode != 0:
        raise RuntimeError((err2 or b"").decode("utf-8", errors="replace").strip() or "git rev-parse failed")
    return out2.decode("utf-8", errors="replace").strip()


def local_deployed_sha() -> str:
    git_dir = os.path.join(_SCRIPT_DIR, ".git")
    if os.path.isdir(git_dir):
        try:
            out = subprocess.run(
                ["git", "-C", _SCRIPT_DIR, "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=20,
                check=True,
            )
            return out.stdout.strip()
        except Exception:
            pass
    return get_setting("deployed_bot_sha", "")


def download_bot_py_from_github() -> None:
    req = urllib.request.Request(_github_raw_bot_url(), headers={"User-Agent": "NumberStoreBot/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = resp.read()
    path = os.path.join(_SCRIPT_DIR, "bot.py")
    with open(path, "wb") as f:
        f.write(data)


async def update_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text(t("update.admin_only"), parse_mode="HTML")
        return
    status = await update.message.reply_text(t("update.checking"), parse_mode="HTML")
    try:
        remote_sha = await asyncio.to_thread(fetch_github_latest_sha)
    except Exception as e:
        logger.error("GitHub API error: %s", e)
        await status.edit_text(
            t("update.github_unreachable", error=escape(str(e))),
            parse_mode="HTML",
        )
        return
    if not remote_sha:
        await status.edit_text(t("update.no_commit"), parse_mode="HTML")
        return
    local_sha = local_deployed_sha()
    if local_sha and local_sha == remote_sha:
        await status.edit_text(
            t(
                "update.up_to_date",
                branch=escape(GITHUB_DEFAULT_BRANCH),
                sha_short=escape(remote_sha[:7]),
            ),
            parse_mode="HTML",
        )
        return
    await status.edit_text(t("update.pulling"), parse_mode="HTML")
    try:
        git_dir = os.path.join(_SCRIPT_DIR, ".git")
        if os.path.isdir(git_dir):
            new_sha = await _async_git_pull_and_head()
        else:
            await asyncio.to_thread(download_bot_py_from_github)
            new_sha = remote_sha
        set_setting("deployed_bot_sha", new_sha)
    except FileNotFoundError as e:
        logger.exception("Bot update failed (git missing?)")
        await status.edit_text(
            t("update.git_not_found") + f"\n<code>{escape(str(e))}</code>",
            parse_mode="HTML",
        )
        return
    except Exception as e:
        logger.exception("Bot update failed")
        await status.edit_text(
            t("update.failed", error=escape(str(e))),
            parse_mode="HTML",
        )
        return
    await status.edit_text(t("update.restarting"), parse_mode="HTML")
    await asyncio.sleep(0.6)
    script = os.path.abspath(__file__)
    os.execv(sys.executable, [sys.executable, script, *sys.argv[1:]])

def main_menu_kb():
    return InlineKeyboardMarkup(
        [
            [ibutton("menu.btn_browse", callback_data="browse_0")],
            [
                ibutton("menu.btn_wallet", callback_data="wallet"),
                ibutton("menu.btn_orders", callback_data="my_orders_0"),
            ],
            [ibutton("menu.btn_help", callback_data="help")],
        ]
    )


def render_welcome_message(user):
    full_name = " ".join(x for x in [getattr(user, "first_name", ""), getattr(user, "last_name", "")] if x) or "User"
    template = get_setting("welcome_message", welcome_default_template())
    safe_name = escape(full_name)
    raw = template.replace("{user_name}", safe_name)
    return apply_custom_emoji_html(raw)

async def safe_edit_callback_message(query, *, text: str, parse_mode: str, reply_markup=None):
    """
    If the callback message is a photo, Telegram only allows editing the caption.
    This prevents: 'There is no text in the message to edit'.
    """
    msg = getattr(query, "message", None)
    if msg is not None and getattr(msg, "photo", None):
        await query.edit_message_caption(
            caption=text,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
        )
    else:
        await query.edit_message_text(
            text,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
        )

def generate_upi_qr(amount, note):
    upi_url = f"upi://pay?pa={UPI_ID}&pn=NumberStore&am={amount}&cu=INR&tn={note}"
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(upi_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf

def status_emoji(status):
    return {"pending": "⏳", "approved": "✅", "rejected": "❌"}.get(status, "❓")

def _mask_phone_for_log(phone_number):
    phone = str(phone_number or "")
    tail = phone[-4:] if len(phone) >= 4 else phone
    return f"+••••••{tail}" if tail else "+••••"

def build_buy_log_text(country_name, country_flag, amount_inr, phone_number):
    safe_country = escape(country_name or "Unknown")
    return (
        "🛒 <b>ɴᴇᴡ sᴀʟᴇ ᴄᴏɴꜰɪʀᴍᴇᴅ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 <b>ᴄᴀᴛᴇɢᴏʀʏ:</b> {safe_country} {country_flag or ''}\n"
        f"💸 <b>ᴀᴍᴏᴜɴᴛ:</b> ₹{amount_inr:.2f}\n"
        f"📱 <b>ɴᴜᴍʙᴇʀ:</b> <code>{_mask_phone_for_log(phone_number)}</code>\n"
        f"🏷️ <b>sᴛᴏʀᴇ:</b> @{STORE_BOT_USERNAME}"
    )

async def send_buy_log(context: ContextTypes.DEFAULT_TYPE, country_name, country_flag, amount_inr, phone_number):
    if not LOG_GROUP_ID:
        return
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛒 ʙᴜʏ ɴᴏᴡ", url=f"https://t.me/{STORE_BOT_USERNAME}?start=buy")]
    ])
    try:
        await context.bot.send_message(
            chat_id=LOG_GROUP_ID,
            text=build_buy_log_text(country_name, country_flag, amount_inr, phone_number),
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=kb
        )
    except Exception as e:
        logger.error(f"Failed to send buy log: {e}")

# ─── GUARD DECORATOR ─────────────────────────────────────────────────────────
async def guard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return True
    register_user(user)
    err = check_access(user.id)
    if err:
        if update.callback_query:
            await update.callback_query.answer(err, show_alert=True)
        else:
            await update.effective_message.reply_text(err)
        return True
    return False

# ─── /start ──────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await guard(update, context):
        return
    user = update.effective_user
    if user:
        try:
            full_name = " ".join(x for x in [user.first_name, user.last_name] if x) or "User"
            mention = f"<a href='tg://user?id={user.id}'>{escape(full_name)}</a>"
            uname = f"@{escape(user.username)}" if user.username else "<i>not_set</i>"
            admin_log = (
                "🚀 <b>ɴᴇᴡ ʙᴏᴛ sᴛᴀʀᴛ</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 <b>ᴜsᴇʀ:</b> {mention}\n"
                f"🔖 <b>ᴜsᴇʀɴᴀᴍᴇ:</b> {uname}\n"
                f"🆔 <b>ɪᴅ:</b> <code>{user.id}</code>"
            )
            await context.bot.send_message(chat_id=ADMIN_GROUP_ID, text=admin_log, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Start log send failed: {e}")
    msg = render_welcome_message(user)
    # Send spoiler image with keyboard attached.
    # All callback handlers use safe edit helpers to avoid Telegram errors.
    await update.message.reply_photo(
        photo=START_IMAGE_URL,
        caption=msg,
        parse_mode="HTML",
        has_spoiler=True,
        reply_markup=main_menu_kb(),
    )

# ─── BROWSE NUMBERS ──────────────────────────────────────────────────────────
async def browse_numbers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if await guard(update, context):
        return

    page = int(query.data.split("_")[1])
    countries = list_browse_countries()

    per_page = 5
    total = len(countries)

    if total == 0:
        buttons = [[ibutton("common.main_menu", callback_data="main_menu")]]
        await safe_edit_callback_message(
            query,
            text=t("browse.no_stock"),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return

    pages = max(1, (total + per_page - 1) // per_page)
    page = max(0, min(page, pages - 1))
    start_i = page * per_page
    chunk = countries[start_i:start_i + per_page]

    parts = [t("browse.header")]
    for c in chunk:
        stock = c["stock_count"]
        price_inr = c["price_inr"] or 0
        parts.append(
            t(
                "browse.country_block",
                flag=c["flag"],
                name=escape(c["name"]),
                stock=stock,
                price=f"{price_inr:.0f}",
            )
        )
    parts.append(t("browse.footer", cur=page + 1, pages=pages))
    full_text = "\n".join(parts)

    buttons = []
    for c in chunk:
        stock = c["stock_count"]
        price_inr = c["price_inr"] or 0
        label = f"{c['flag']} {c['name']} • 📦{stock} • ₹{price_inr:.0f}"
        buttons.append(
            [
                ibutton_raw(
                    label,
                    callback_data=f"country_{c['code']}",
                    icon_slot="globe",
                    style="success",
                )
            ]
        )

    nav = []
    if page > 0:
        nav.append(ibutton("browse.btn_prev", callback_data=f"browse_{page-1}"))
        nav.append(
            ibutton(
                "browse.btn_page",
                callback_data="noop",
                cur=page + 1,
                pages=pages,
            )
        )
    if page < pages - 1:
        nav.append(ibutton("browse.btn_next", callback_data=f"browse_{page+1}"))

    if nav:
        buttons.append(nav)
    buttons.append([ibutton("common.main_menu", callback_data="main_menu")])

    await safe_edit_callback_message(
        query,
        text=full_text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons),
    )

async def oos_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer(t_plain("browse.oos_alert"), show_alert=True)

async def noop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()

# ─── COUNTRY DETAIL ──────────────────────────────────────────────────────────
async def country_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if await guard(update, context):
        return
    code = query.data.split("_", 1)[1]
    c = get_country(code)
    if not c:
        await safe_edit_callback_message(
            query,
            text=t("country.not_found"),
            parse_mode="HTML",
            reply_markup=None,
        )
        return
    stock = get_stock_count(code)

    if stock == 0:
        kb = InlineKeyboardMarkup([
            [ibutton("country.btn_back_browse", callback_data="browse_0")],
        ])
        await safe_edit_callback_message(
            query,
            text=t("country.oos", flag=c["flag"], name=escape(c["name"])),
            parse_mode="HTML",
            reply_markup=kb,
        )
        return

    wallet = get_wallet_balance(query.from_user.id)

    text = t(
        "country.detail",
        flag=c["flag"],
        name=escape(c["name"]),
        price=f"{c['price_inr']:.0f}",
        stock=stock,
    )
    kb = InlineKeyboardMarkup(
        [
            [ibutton("country.btn_pay_upi", callback_data=f"pay_method_{code}")],
            [
                ibutton(
                    "country.btn_wallet_buy",
                    callback_data=f"wallet_buy_{code}",
                    bal=f"{wallet:.2f}",
                )
            ],
            [ibutton("country.btn_back_browse", callback_data="browse_0")],
        ]
    )
    await safe_edit_callback_message(
        query,
        text=text,
        parse_mode="HTML",
        reply_markup=kb,
    )

# ─── WALLET BUY ──────────────────────────────────────────────────────────────
async def wallet_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if await guard(update, context):
        return
    code = query.data.split("_", 2)[2]
    c = get_country(code)
    user_id = query.from_user.id
    user_row = get_user_row(user_id)
    if not user_row:
        await safe_edit_callback_message(
            query,
            text=t("buy.user_not_found"),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                [[ibutton("country.btn_back_browse", callback_data=f"country_{code}")]]
            ),
        )
        return
    wallet = user_row["wallet_balance"]
    price = c["price_inr"]
    if wallet < price:
        kb = InlineKeyboardMarkup(
            [
                [ibutton("buy.btn_deposit", callback_data="deposit")],
                [ibutton("common.back", callback_data=f"country_{code}")],
            ]
        )
        await safe_edit_callback_message(
            query,
            text=t("buy.low_balance", need=price, have=wallet),
            parse_mode="HTML",
            reply_markup=kb,
        )
        return
    order_id = wallet_buy_transaction(
        user_id, query.from_user.username or "", code, float(price)
    )
    if not order_id:
        await safe_edit_callback_message(
            query,
            text=t("buy.no_accounts"),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                [[ibutton("common.back", callback_data=f"country_{code}")]]
            ),
        )
        return
    ord_row = get_order_by_id(order_id) or {}
    acc = get_account_by_id(ord_row.get("account_id")) if ord_row.get("account_id") else None
    if acc:
        await send_buy_log(context, c["name"], c["flag"], c["price_inr"], acc["phone_number"])
    kb = InlineKeyboardMarkup([[ibutton("buy.btn_reveal", callback_data=f"reveal_{order_id}")]])
    await safe_edit_callback_message(
        query,
        text=t("buy.success"),
        parse_mode="HTML",
        reply_markup=kb,
    )

# ─── PAY METHOD (UPI ONLY) ───────────────────────────────────────────────────
async def pay_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if await guard(update, context):
        return
    code = query.data.split("_", 2)[2]
    context.user_data["buy_country"] = code
    context.user_data["buy_method"] = "upi"
    c = get_country(code)
    note = f"Order for {c['name']}"
    qr_buf = generate_upi_qr(c["price_inr"], note)
    caption = t("buy.pay_caption", amount=c["price_inr"], upi=escape(UPI_ID))
    kb = InlineKeyboardMarkup(
        [
            [ibutton("buy.btn_upload", callback_data=f"buy_upload_{code}")],
            [ibutton("common.back", callback_data=f"country_{code}")],
        ]
    )
    await query.message.reply_photo(
        photo=qr_buf, caption=caption, parse_mode="HTML", reply_markup=kb
    )
    await query.message.delete()

async def buy_upload_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if await guard(update, context):
        return
    code = query.data.split("_", 2)[2]
    context.user_data["buy_country"] = code
    context.user_data["awaiting_buy_screenshot"] = True
    await query.edit_message_caption(
        caption=t("buy.upload_caption"),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            [[ibutton("buy.btn_cancel", callback_data=f"country_{code}")]]
        ),
    )

# ─── SCREENSHOT HANDLER ───────────────────────────────────────────────────────
async def screenshot_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await guard(update, context):
        return
    user = update.effective_user

    # Buy screenshot
    if context.user_data.get("awaiting_buy_screenshot"):
        context.user_data.pop("awaiting_buy_screenshot")
        code = context.user_data.get("buy_country")
        if not code:
            await update.message.reply_text(
                t("buy.session_expired"),
                parse_mode="HTML",
                reply_markup=main_menu_kb(),
            )
            return
        c = get_country(code)
        file_id = update.message.photo[-1].file_id if update.message.photo else None
        if not file_id:
            await update.message.reply_text(t("buy.need_photo"), parse_mode="HTML")
            return
        order_id = insert_pending_order(
            user.id,
            user.username or "",
            code,
            float(c["price_inr"]),
            file_id,
            now_ist().isoformat(),
        )
        text = (
            f"┌─────────────────────┐\n"
            f"🆕 NEW ORDER #{order_id}\n"
            f"├─────────────────────┤\n"
            f"👤 User: @{user.username or 'N/A'} (ID: {user.id})\n"
            f"🌍 Country: {c['flag']} {c['name']}\n"
            f"💰 Amount: ₹{c['price_inr']:.0f} INR\n"
            f"💳 Method: UPI\n"
            f"📅 Time: {now_ist().strftime('%d %b %Y %H:%M IST')}\n"
            f"└─────────────────────┘"
        )
        kb = InlineKeyboardMarkup([[
            ibutton_raw(
                f"✅ Approve #{order_id}",
                callback_data=f"approve_order_{order_id}",
                icon_slot="check",
                style="success",
            ),
            ibutton_raw(
                f"❌ Reject #{order_id}",
                callback_data=f"reject_order_{order_id}",
                icon_slot="cross",
                style="danger",
            ),
        ]])
        try:
            await context.bot.send_photo(chat_id=ADMIN_GROUP_ID, photo=file_id, caption=text, reply_markup=kb)
        except Exception as e:
            logger.error(f"Failed to forward to admin group: {e}")
        await update.message.reply_text(
            t("buy.submitted"),
            parse_mode="HTML",
            reply_markup=main_menu_kb(),
        )
        return

    # Deposit screenshot
    if context.user_data.get("awaiting_deposit_screenshot"):
        context.user_data.pop("awaiting_deposit_screenshot")
        dep_inr = context.user_data.get("dep_inr", 0)
        file_id = update.message.photo[-1].file_id if update.message.photo else None
        if not file_id:
            await update.message.reply_text(t("buy.need_photo"), parse_mode="HTML")
            return
        dep_id = insert_pending_deposit(user.id, float(dep_inr), file_id, now_ist().isoformat())
        text = (
            f"┌─────────────────────┐\n"
            f"💰 DEPOSIT REQUEST #{dep_id}\n"
            f"├─────────────────────┤\n"
            f"👤 User: @{user.username or 'N/A'} (ID: {user.id})\n"
            f"💵 Amount: ₹{dep_inr:.0f} INR\n"
            f"💳 Method: UPI\n"
            f"📅 Time: {now_ist().strftime('%d %b %Y %H:%M IST')}\n"
            f"└─────────────────────┘"
        )
        kb = InlineKeyboardMarkup([[
            ibutton_raw(
                f"✅ Approve Deposit #{dep_id}",
                callback_data=f"approve_deposit_{dep_id}",
                icon_slot="check",
                style="success",
            ),
            ibutton_raw(
                f"❌ Reject Deposit #{dep_id}",
                callback_data=f"reject_deposit_{dep_id}",
                icon_slot="cross",
                style="danger",
            ),
        ]])
        try:
            await context.bot.send_photo(chat_id=ADMIN_GROUP_ID, photo=file_id, caption=text, reply_markup=kb)
        except Exception as e:
            logger.error(f"Failed to forward deposit to admin group: {e}")
        await update.message.reply_text(
            t("buy.dep_submitted"),
            parse_mode="HTML",
            reply_markup=main_menu_kb(),
        )
        return

# ─── REVEAL NUMBER ────────────────────────────────────────────────────────────
async def reveal_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if await guard(update, context):
        return
    order_id = int(query.data.split("_")[1])
    user_id = query.from_user.id
    order = get_order_for_user(order_id, user_id)
    if not order or order["status"] != "approved":
        await safe_edit_callback_message(
            query,
            text=t("orders.not_approved"),
            parse_mode="HTML",
            reply_markup=None,
        )
        return
    acc = get_account_by_id(order.get("account_id")) if order.get("account_id") else None
    c = get_country(order["country_code"])
    if not acc:
        await safe_edit_callback_message(
            query,
            text="❌ Account data not found.",
            parse_mode="HTML",
            reply_markup=None,
        )
        return
    text = (
        f"📱 *Your Number Details*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📞 Number: `+{acc['phone_number']}`\n"
        f"🔐 2FA: `{acc['two_fa_password'] or 'Not set'}`\n"
        f"🌍 Country: {c['flag']} {c['name']}\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    kb = InlineKeyboardMarkup([
        [
            ibutton_raw(
                "📨 Get Latest OTP",
                callback_data=f"getotp_{acc['id']}",
                icon_slot="inbox",
                style="primary",
            )
        ],
        [
            ibutton_raw(
                "📦 My Orders",
                callback_data="my_orders_0",
                icon_slot="package",
                style="success",
            )
        ],
    ])
    await safe_edit_callback_message(
        query,
        text=text,
        parse_mode="Markdown",
        reply_markup=kb,
    )

# ─── GET OTP ──────────────────────────────────────────────────────────────────
async def get_otp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("⏳ Fetching OTP...")
    if await guard(update, context):
        return
    acc_id = int(query.data.split("_")[1])
    acc = get_account_by_id(acc_id)
    if not acc:
        await safe_edit_callback_message(
            query,
            text="❌ Account not found.",
            parse_mode="HTML",
            reply_markup=None,
        )
        return
    await safe_edit_callback_message(
        query,
        text="⏳ Connecting to fetch OTP...",
        parse_mode="HTML",
        reply_markup=None,
    )
    otp_code = None
    error_msg = None
    client = TelegramClient(StringSession(acc["session_string"]), API_ID, API_HASH)
    try:
        await client.connect()
        otp_code = await _fetch_otp(client)
    except FloodWaitError as e:
        error_msg = f"⏳ Please wait {e.seconds} seconds."
    except Exception as e:
        if "session" in str(e).lower() or "auth" in str(e).lower():
            error_msg = "❌ Session expired for this account."
        else:
            error_msg = "⚠️ Could not fetch OTP. Try again later."
        logger.error(f"OTP fetch error: {e}")
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass

    if error_msg:
        kb = InlineKeyboardMarkup(
            [
                [
                    ibutton_raw(
                        "🔙 Back",
                        callback_data=f"reveal_{_get_order_for_account(acc_id)}",
                        icon_slot="package",
                        style="primary",
                    )
                ]
            ]
        )
        await safe_edit_callback_message(
            query,
            text=error_msg,
            parse_mode="HTML",
            reply_markup=kb,
        )
        return

    text = (
        f"🔑 *Latest OTP:* `{otp_code or 'Not found'}`\n"
        f"📞 Number: `+{acc['phone_number']}`\n"
        f"🔐 2FA: `{acc['two_fa_password'] or 'Not set'}`\n"
        f"⏱ Fetched at: {now_ist().strftime('%H:%M:%S IST')}"
    )
    kb = InlineKeyboardMarkup([
        [
            ibutton_raw(
                "🔄 Refresh OTP",
                callback_data=f"getotp_{acc_id}",
                icon_slot="star",
                style="success",
            )
        ],
        [
            ibutton_raw(
                "🔙 Back",
                callback_data=f"getotp_back_{acc_id}",
                icon_slot="package",
                style="primary",
            )
        ],
    ])
    await safe_edit_callback_message(
        query,
        text=text,
        parse_mode="Markdown",
        reply_markup=kb,
    )

async def _fetch_otp(client):
    otp_pattern = re.compile(r'\b\d{4,6}\b')
    for sender in ["+42777", 777000]:
        try:
            msgs = await client.get_messages(sender, limit=5)
            for msg in msgs:
                if msg.text:
                    match = otp_pattern.search(msg.text)
                    if match:
                        return match.group()
        except Exception:
            continue
    return None

def _get_order_for_account(acc_id):
    return order_id_for_account(acc_id)

async def getotp_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    acc_id = int(query.data.split("_")[2])
    order_id = _get_order_for_account(acc_id)
    query.data = f"reveal_{order_id}"
    await reveal_number(update, context)

# ─── WALLET ───────────────────────────────────────────────────────────────────
async def wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if await guard(update, context):
        return
    bal = get_wallet_balance(query.from_user.id)
    text = t("wallet.panel", bal=bal)
    kb = InlineKeyboardMarkup(
        [
            [ibutton("wallet.btn_deposit", callback_data="deposit")],
            [ibutton("wallet.btn_dep_hist", callback_data="dep_hist_0")],
            [ibutton("common.main_menu", callback_data="main_menu")],
        ]
    )
    await safe_edit_callback_message(
        query,
        text=text,
        parse_mode="HTML",
        reply_markup=kb,
    )

# ─── DEPOSIT (UPI ONLY) ───────────────────────────────────────────────────────
async def deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if await guard(update, context):
        return
    context.user_data["awaiting_dep_amount"] = True
    await safe_edit_callback_message(
        query,
        text=t("wallet.deposit_prompt"),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            [[ibutton("buy.btn_cancel", callback_data="wallet")]]
        ),
    )

# ─── TEXT HANDLER ─────────────────────────────────────────────────────────────
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await guard(update, context):
        return
    user = update.effective_user

    # Admin: dialing code input
    if context.user_data.get("awaiting_admin_dialing_code"):
        raw = update.message.text.strip()
        result = lookup_dialing_code(raw)
        if not result:
            await update.message.reply_text(
                "❌ Country not found for that dialing code.\n\nPlease try again (e.g. +91, +1, +44, +92):",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="admin_stock")]])
            )
            return
        country_code_iso, country_name, country_flag = result
        c = get_country(country_code_iso)
        if not c:
            ensure_country_row(country_code_iso, country_name, country_flag)
            c = get_country(country_code_iso)

        context.user_data.pop("awaiting_admin_dialing_code")
        context.user_data["add_acc_country"] = country_code_iso
        context.user_data["add_acc_step"] = "phone"

        await update.message.reply_text(
            f"✅ *Country Verified!*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{country_flag} *{country_name}*  (Code: `{country_code_iso}`)\n"
            f"Dialing: `{raw}`\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📞 Now send the phone number in international format:\n"
            f"Example: `+{raw.lstrip('+').lstrip('0')}XXXXXXXXXX`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="admin_stock")]])
        )
        return

    # Admin: ISO code fallback
    if context.user_data.get("awaiting_admin_country_code"):
        code = update.message.text.strip().upper()
        c = get_country(code)
        if not c:
            await update.message.reply_text("❌ Invalid Country Code. Please enter a valid ISO code (e.g., IN, US, PK):")
            return
        context.user_data.pop("awaiting_admin_country_code")
        context.user_data["add_acc_country"] = code
        context.user_data["add_acc_step"] = "phone"
        await update.message.reply_text(f"✅ Country: {c['flag']} {c['name']}\n\nSend phone number (e.g. +91xxxxxxxxxx):")
        return

    # UPI deposit amount
    if context.user_data.get("awaiting_dep_amount"):
        try:
            amount = float(update.message.text.strip())
        except ValueError:
            await update.message.reply_text("❌ Please enter a valid number.")
            return
        if amount < 50:
            await update.message.reply_text("❌ Minimum deposit is ₹50. Enter again:")
            return
        context.user_data.pop("awaiting_dep_amount")
        context.user_data["dep_inr"] = amount
        note = f"Deposit by {user.id}"
        qr_buf = generate_upi_qr(amount, note)
        caption = t("buy.pay_caption", amount=amount, upi=escape(UPI_ID))
        context.user_data["awaiting_deposit_screenshot"] = True
        await update.message.reply_photo(
            photo=qr_buf,
            caption=caption,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                [[ibutton("buy.btn_upload", callback_data="upload_dep_screenshot")]]
            ),
        )
        return

    # Admin: edit balance
    if context.user_data.get("admin_edit_balance_uid"):
        uid = context.user_data.pop("admin_edit_balance_uid")
        try:
            delta = float(update.message.text.strip())
        except ValueError:
            await update.message.reply_text("❌ Invalid amount.")
            return
        new_bal = adjust_wallet(uid, delta)
        sign = "+" if delta >= 0 else ""
        await update.message.reply_text(
            f"✅ Balance updated: {sign}{delta:.2f} INR\nNew balance: ₹{new_bal:.2f}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin Menu", callback_data="admin_menu")]])
        )
        return

    # Admin: set price INR
    if context.user_data.get("admin_set_price_code") and context.user_data.get("awaiting_price_inr"):
        try:
            price = float(update.message.text.strip())
        except ValueError:
            await update.message.reply_text("❌ Invalid price.")
            return
        code = context.user_data.pop("admin_set_price_code")
        context.user_data.pop("awaiting_price_inr")
        set_country_price(code, float(price))
        c = get_country(code)
        await update.message.reply_text(
            f"✅ {c['flag']} {c['name']}: ₹{price:.0f} INR",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin Menu", callback_data="admin_menu")]])
        )
        return

    # Admin: add account steps
    if context.user_data.get("add_acc_step"):
        step = context.user_data["add_acc_step"]
        if step == "phone":
            phone = update.message.text.strip()
            if not phone.startswith("+"):
                await update.message.reply_text("❌ Phone must start with + (e.g. +91XXXXXXXXXX). Try again:")
                return
            context.user_data["add_acc_phone"] = phone
            context.user_data["add_acc_step"] = "session"
            await update.message.reply_text(
                "✅ Phone saved!\n\n🔑 Now send the *session string*:",
                parse_mode="Markdown"
            )
            return
        if step == "session":
            context.user_data["add_acc_session"] = update.message.text.strip()
            context.user_data["add_acc_step"] = "twofa"
            await update.message.reply_text(
                "✅ Session saved!\n\n🔐 Send *2FA password* or skip if not set:",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⏭ Skip 2FA", callback_data="add_acc_skip_2fa")]])
            )
            return
        if step == "twofa":
            context.user_data["add_acc_2fa"] = update.message.text.strip()
            context.user_data["add_acc_step"] = "price_inr"
            await update.message.reply_text(
                "✅ 2FA saved!\n\n💰 Enter *price in INR* for this number:",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⏭ Skip (use country price)", callback_data="add_acc_skip_price")]])
            )
            return
        if step == "price_inr":
            try:
                inr = float(update.message.text.strip())
            except ValueError:
                await update.message.reply_text("❌ Invalid price. Enter a number (e.g. 500):")
                return
            context.user_data["add_acc_price_inr"] = inr
            context.user_data["add_acc_step"] = None
            await update.message.reply_text(f"✅ Price set: ₹{inr:.0f} INR")
            await _finalize_add_account(update, context)
            return

    # Admin: remove account
    if context.user_data.get("awaiting_remove_acc"):
        context.user_data.pop("awaiting_remove_acc")
        query_val = update.message.text.strip()
        if not query_val.startswith("+"):
            try:
                int(query_val)
            except ValueError:
                await update.message.reply_text("❌ Invalid ID.")
                return
        acc = find_account_by_phone_or_id(query_val)
        if not acc:
            await update.message.reply_text("❌ Account not found.")
            return
        c = get_country(acc["country_code"])
        context.user_data["remove_acc_id"] = acc["id"]
        text = f"Account #{acc['id']}: {c['flag']} {c['name']}\n📞 +{acc['phone_number']}\nSold: {'Yes' if acc['is_sold'] else 'No'}"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🗑️ Confirm Delete", callback_data=f"confirm_del_{acc['id']}"),
             InlineKeyboardButton("🔙 Cancel", callback_data="admin_stock")],
        ])
        await update.message.reply_text(text, reply_markup=kb)
        return

    # Admin: broadcast
    if context.user_data.get("awaiting_broadcast"):
        context.user_data.pop("awaiting_broadcast")
        total = count_active_users()
        context.user_data["broadcast_msg_id"] = update.message.message_id
        context.user_data["broadcast_chat_id"] = update.message.chat_id
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"✅ Send to {total} users", callback_data="broadcast_confirm"),
             InlineKeyboardButton("❌ Cancel", callback_data="admin_menu")],
        ])
        await update.message.reply_text(f"📢 Send to {total} users?", reply_markup=kb)
        return

    # Admin: search user
    if context.user_data.get("awaiting_search_user"):
        context.user_data.pop("awaiting_search_user")
        query_val = update.message.text.strip().lstrip("@")
        row = find_user_by_id_or_username(query_val)
        if not row:
            await update.message.reply_text("❌ User not found.")
            return
        await _show_user_profile(update, context, dict(row), via_message=True)
        return

    # Admin: welcome message
    if context.user_data.get("awaiting_welcome_msg"):
        context.user_data.pop("awaiting_welcome_msg")
        set_setting("welcome_message", update.message.text)
        await update.message.reply_text(
            "✅ Welcome message updated!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin Menu", callback_data="admin_menu")]])
        )
        return

async def _finalize_add_account(update, context):
    code = context.user_data.pop("add_acc_country")
    phone = context.user_data.pop("add_acc_phone")
    session = context.user_data.pop("add_acc_session")
    twofa = context.user_data.pop("add_acc_2fa", None)
    price_inr = context.user_data.pop("add_acc_price_inr", None)
    context.user_data.pop("add_acc_step", None)
    phone = phone.lstrip("+")
    insert_account(
        code,
        phone,
        session,
        twofa,
        update.effective_user.id,
        now_ist().isoformat(),
    )
    if price_inr is not None:
        set_country_price(code, float(price_inr))
    stock = get_stock_count(code)
    c = get_country(code)
    inr_str = f"₹{price_inr:.0f}" if price_inr else f"₹{c['price_inr']:.0f}"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Another", callback_data="add_acc_start")],
        [InlineKeyboardButton("🔙 Admin Menu", callback_data="admin_menu")],
    ])
    msg = (
        f"✅ *Account Added Successfully!*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🌍 Country: {c['flag']} {c['name']}\n"
        f"📞 Phone: +{phone}\n"
        f"🔐 2FA: {twofa or 'Not set'}\n"
        f"💰 Price: {inr_str} INR\n"
        f"📦 Stock now: {stock}\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    if hasattr(update, "message") and update.message:
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=kb)
    else:
        await safe_edit_callback_message(
            update.callback_query,
            text=msg,
            parse_mode="Markdown",
            reply_markup=kb,
        )

# ─── UPLOAD DEP SCREENSHOT ────────────────────────────────────────────────────
async def upload_dep_screenshot_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["awaiting_deposit_screenshot"] = True
    await query.edit_message_caption(
        caption=(query.message.caption or "")
        + "\n"
        + t("buy.upload_caption"),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            [[ibutton("buy.btn_cancel", callback_data="wallet")]]
        ),
    )

# ─── ADD ACC SKIP PRICE ───────────────────────────────────────────────────────
async def add_acc_skip_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["add_acc_price_inr"] = None
    context.user_data["add_acc_step"] = None
    await _finalize_add_account(update, context)

# ─── MY ORDERS ────────────────────────────────────────────────────────────────
async def my_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if await guard(update, context):
        return
    page = int(query.data.split("_")[2])
    user_id = query.from_user.id
    orders = orders_for_user(user_id)
    if not orders:
        await safe_edit_callback_message(
            query,
            text=t("orders.none"),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                [[ibutton("common.main_menu", callback_data="main_menu")]]
            ),
        )
        return
    per_page = 5
    total = len(orders)
    pages = max(1, (total + per_page - 1) // per_page)
    page = max(0, min(page, pages - 1))
    chunk = orders[page * per_page:(page + 1) * per_page]
    buttons = []
    for o in chunk:
        status_e = status_emoji(o["status"])
        label = f"#{o['id']} | {o['flag'] or ''}{o['cname'] or '?'} | ₹{o['amount_inr']:.0f} | {status_e}"
        buttons.append(
            [
                ibutton_raw(
                    label,
                    callback_data=f"order_detail_{o['id']}",
                    icon_slot="package",
                    style="success",
                )
            ]
        )
    nav = []
    if page > 0:
        nav.append(ibutton("orders.btn_prev", callback_data=f"my_orders_{page-1}"))
        nav.append(
            ibutton(
                "browse.btn_page",
                callback_data="noop",
                cur=page + 1,
                pages=pages,
            )
        )
    if page < pages - 1:
        nav.append(ibutton("orders.btn_next", callback_data=f"my_orders_{page+1}"))
    if nav:
        buttons.append(nav)
    buttons.append([ibutton("common.main_menu", callback_data="main_menu")])
    await safe_edit_callback_message(
        query,
        text=t("orders.header"),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons),
    )

async def order_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if await guard(update, context):
        return
    order_id = int(query.data.split("_")[2])
    user_id = query.from_user.id
    o = get_order_for_user(order_id, user_id)
    if not o:
        await safe_edit_callback_message(
            query,
            text=t("orders.not_found"),
            parse_mode="HTML",
            reply_markup=None,
        )
        return
    o = dict(o)
    ch = get_country(o.get("country_code") or "")
    o["flag"] = ch["flag"] if ch else None
    o["cname"] = ch["name"] if ch else None
    text = t(
        "orders.detail",
        oid=o["id"],
        flag=o["flag"] or "",
        cname=escape(o["cname"] or "N/A"),
        amount=o["amount_inr"],
        status_emoji=status_emoji(o["status"]),
        status=sc(o["status"].title()),
        created=fmt_time(o["created_at"]),
    )
    buttons = []
    if o["status"] == "approved" and o["account_id"]:
        buttons.append([ibutton("orders.btn_reveal", callback_data=f"reveal_{o['id']}")])
    buttons.append([ibutton("orders.btn_back_orders", callback_data="my_orders_0")])
    await safe_edit_callback_message(
        query,
        text=text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons),
    )

# ─── DEPOSIT HISTORY ──────────────────────────────────────────────────────────
async def dep_hist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if await guard(update, context):
        return
    page = int(query.data.split("_")[2])
    user_id = query.from_user.id
    deps = deposits_for_user(user_id)
    if not deps:
        await safe_edit_callback_message(
            query,
            text=t("wallet.dep_empty"),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                [[ibutton("wallet.btn_back_wallet", callback_data="wallet")]]
            ),
        )
        return
    per_page = 5
    total = len(deps)
    pages = max(1, (total + per_page - 1) // per_page)
    page = max(0, min(page, pages - 1))
    chunk = deps[page * per_page:(page + 1) * per_page]
    lines = []
    for d in chunk:
        date = fmt_time(d["created_at"])[:11]
        lines.append(f"#{d['id']} | UPI | ₹{d['amount_inr']:.0f} | {status_emoji(d['status'])} | {date}")
    text = t("wallet.dep_header") + "\n" + "\n".join(lines)
    nav = []
    if page > 0:
        nav.append(ibutton("browse.btn_prev", callback_data=f"dep_hist_{page-1}"))
        nav.append(
            ibutton(
                "browse.btn_page",
                callback_data="noop",
                cur=page + 1,
                pages=pages,
            )
        )
    if page < pages - 1:
        nav.append(ibutton("browse.btn_next", callback_data=f"dep_hist_{page+1}"))
    buttons = []
    if nav:
        buttons.append(nav)
    buttons.append([ibutton("wallet.btn_back_wallet", callback_data="wallet")])
    await safe_edit_callback_message(
        query,
        text=text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons),
    )

# ─── HELP ─────────────────────────────────────────────────────────────────────
async def help_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = t("help.body")
    kb = InlineKeyboardMarkup(
        [
            [ibutton("help.btn_support", url="https://t.me/ll_PRIME_DENJI_ll")],
            [ibutton("help.btn_main", callback_data="main_menu")],
        ]
    )
    await safe_edit_callback_message(query, text=text, parse_mode="HTML", reply_markup=kb)

async def main_menu_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if await guard(update, context):
        return
    msg = render_welcome_message(update.effective_user)
    await safe_edit_callback_message(query, text=msg, parse_mode="HTML", reply_markup=main_menu_kb())

# ─── ADMIN GROUP APPROVALS ────────────────────────────────────────────────────
async def approve_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id not in ADMIN_IDS:
        await query.answer("❌ Not authorized.", show_alert=True)
        return
    await query.answer()
    order_id = int(query.data.split("_")[2])
    order_before = get_order_by_id(order_id)
    if not order_before or order_before["status"] != "pending":
        await query.edit_message_caption(caption=(query.message.caption or "") + "\n⚠️ Order already processed.")
        return
    result = approve_order_transaction(order_id, query.from_user.id)
    if not result:
        await query.answer("❌ No stock available!", show_alert=True)
        return
    order = result["order"]
    acc = result["acc"]
    c = get_country(order["country_code"])
    if c:
        await send_buy_log(context, c["name"], c["flag"], order["amount_inr"], acc["phone_number"])
    kb = InlineKeyboardMarkup([[ibutton("buy.btn_reveal", callback_data=f"reveal_{order_id}")]])
    try:
        await context.bot.send_message(
            chat_id=order["user_id"],
            text=f"✅ Order #{order_id} approved! Your number is ready.",
            reply_markup=kb
        )
    except Exception:
        pass
    await query.edit_message_caption(caption=(query.message.caption or "") + f"\n✅ Approved by @{query.from_user.username or query.from_user.id}")

async def reject_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id not in ADMIN_IDS:
        await query.answer("❌ Not authorized.", show_alert=True)
        return
    await query.answer()
    order_id = int(query.data.split("_")[2])
    order = reject_order_db(order_id, query.from_user.id)
    if not order:
        await query.edit_message_caption(caption=(query.message.caption or "") + "\n⚠️ Order already processed.")
        return
    try:
        await context.bot.send_message(
            chat_id=order["user_id"],
            text=f"❌ Order #{order_id} rejected. Contact support if needed.",
            reply_markup=main_menu_kb()
        )
    except Exception:
        pass
    await query.edit_message_caption(caption=(query.message.caption or "") + f"\n❌ Rejected by @{query.from_user.username or query.from_user.id}")

async def approve_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id not in ADMIN_IDS:
        await query.answer("❌ Not authorized.", show_alert=True)
        return
    await query.answer()
    dep_id = int(query.data.split("_")[2])
    dep = approve_deposit_db(dep_id, query.from_user.id)
    if not dep:
        await query.edit_message_caption(caption=(query.message.caption or "") + "\n⚠️ Already processed.")
        return
    try:
        await context.bot.send_message(
            chat_id=dep["user_id"],
            text=f"✅ Deposit of ₹{dep['amount_inr']:.0f} INR credited to your wallet!",
            reply_markup=main_menu_kb()
        )
    except Exception:
        pass
    await query.edit_message_caption(caption=(query.message.caption or "") + f"\n✅ Approved by @{query.from_user.username or query.from_user.id}")

async def reject_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id not in ADMIN_IDS:
        await query.answer("❌ Not authorized.", show_alert=True)
        return
    await query.answer()
    dep_id = int(query.data.split("_")[2])
    dep = reject_deposit_db(dep_id, query.from_user.id)
    if not dep:
        await query.edit_message_caption(caption=(query.message.caption or "") + "\n⚠️ Already processed.")
        return
    try:
        await context.bot.send_message(chat_id=dep["user_id"], text=f"❌ Deposit #{dep_id} rejected.")
    except Exception:
        pass
    await query.edit_message_caption(caption=(query.message.caption or "") + f"\n❌ Rejected by @{query.from_user.username or query.from_user.id}")

# ─── ADMIN PANEL ──────────────────────────────────────────────────────────────
async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Not authorized.")
        return
    await update.message.reply_text(
        t("admin_cmd.reply"),
        parse_mode="HTML",
        reply_markup=admin_main_kb(),
    )

def admin_main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📦 Stock", callback_data="admin_stock"),
         InlineKeyboardButton("🌍 Countries", callback_data="admin_countries"),
         InlineKeyboardButton("💰 Orders", callback_data="admin_orders_all_0")],
        [InlineKeyboardButton("👥 Users", callback_data="admin_users"),
         InlineKeyboardButton("💳 Deposits", callback_data="admin_deps_all_0"),
         InlineKeyboardButton("📊 Stats", callback_data="admin_stats")],
        [InlineKeyboardButton("⚙️ Settings", callback_data="admin_settings"),
         InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast"),
         InlineKeyboardButton("🔙 Close", callback_data="admin_close")],
    ])

async def admin_menu_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.answer("❌ Not authorized.", show_alert=True)
        return
    await query.edit_message_text("🔧 *Admin Panel*", parse_mode="Markdown", reply_markup=admin_main_kb())

async def admin_close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.delete_message()

# ── STOCK ─────────────────────────────────────────────────────────────────────
async def admin_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Account", callback_data="add_acc_start")],
        [InlineKeyboardButton("📋 View by Country", callback_data="view_stock_0")],
        [InlineKeyboardButton("🗑️ Remove Account", callback_data="remove_acc")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_menu")],
    ])
    await query.edit_message_text("📦 *Stock Manager*", parse_mode="Markdown", reply_markup=kb)

async def add_acc_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    context.user_data["awaiting_admin_dialing_code"] = True
    await query.edit_message_text(
        "🌍 *Add Account — Step 1/5*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Enter the *country dialing code*:\n\n"
        "Examples:\n"
        "• `+91` → 🇮🇳 India\n"
        "• `+1` → 🇺🇸 United States\n"
        "• `+44` → 🇬🇧 United Kingdom\n"
        "• `+92` → 🇵🇰 Pakistan\n"
        "• `+86` → 🇨🇳 China\n"
        "━━━━━━━━━━━━━━━━━━━━",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="admin_stock")]])
    )

async def add_acc_skip_2fa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["add_acc_2fa"] = None
    context.user_data["add_acc_step"] = "price_inr"
    await query.edit_message_text(
        "⏭ 2FA skipped!\n\n"
        "💰 *Step 4/5 — Enter price in INR:*\n\n"
        "Example: `500`",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⏭ Skip (use country price)", callback_data="add_acc_skip_price")]])
    )

async def view_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    page = int(query.data.split("_")[2])
    countries = list_countries_sorted()
    per_page = 8
    total = len(countries)
    pages = max(1, (total + per_page - 1) // per_page)
    page = max(0, min(page, pages - 1))
    chunk = countries[page * per_page:(page + 1) * per_page]
    lines = []
    for c in chunk:
        avail = get_stock_count(c["code"])
        total_acc = count_accounts_for_country(c["code"])
        lines.append(f"{c['flag']} {c['name']}: {avail} available / {total_acc} total")
    text = "📋 *Stock by Country*\n" + "\n".join(lines)
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ Prev", callback_data=f"view_stock_{page-1}"))
        nav.append(InlineKeyboardButton(f"{page+1}/{pages}", callback_data="noop"))
    if page < pages - 1:
        nav.append(InlineKeyboardButton("Next ▶️", callback_data=f"view_stock_{page+1}"))
    buttons = []
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="admin_stock")])
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))

async def remove_acc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    context.user_data["awaiting_remove_acc"] = True
    await query.edit_message_text(
        "Send account ID or phone number to remove:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="admin_stock")]])
    )

async def confirm_del(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    acc_id = int(query.data.split("_")[2])
    delete_account_by_id(acc_id)
    await query.edit_message_text("✅ Account deleted.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Stock", callback_data="admin_stock")]]))

# ── COUNTRIES ──────────────────────────────────────────────────────────────────
async def admin_countries(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Set Prices", callback_data="set_prices_0")],
        [InlineKeyboardButton("🔛 Enable / Disable", callback_data="toggle_countries_0")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_menu")],
    ])
    await query.edit_message_text("🌍 *Countries Manager*", parse_mode="Markdown", reply_markup=kb)

async def set_prices(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    page = int(query.data.split("_")[2])
    countries = list_countries_sorted()
    per_page = 8
    total = len(countries)
    pages = max(1, (total + per_page - 1) // per_page)
    chunk = countries[page * per_page:(page + 1) * per_page]
    buttons = []
    for i in range(0, len(chunk), 2):
        row = []
        for c in chunk[i:i+2]:
            row.append(InlineKeyboardButton(f"{c['flag']} {c['name']}", callback_data=f"setprice_{c['code']}"))
        buttons.append(row)
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"set_prices_{page-1}"))
        nav.append(InlineKeyboardButton(f"{page+1}/{pages}", callback_data="noop"))
    if page < pages - 1:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"set_prices_{page+1}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="admin_countries")])
    await query.edit_message_text("✏️ *Select country to set price (INR):*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))

async def setprice_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    code = query.data.split("setprice_")[1]
    context.user_data["admin_set_price_code"] = code
    context.user_data["awaiting_price_inr"] = True
    c = get_country(code)
    await query.edit_message_text(f"Setting price for {c['flag']} {c['name']}\nEnter INR price:")

async def toggle_countries(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    page = int(query.data.split("_")[2])
    countries = list_countries_sorted()
    per_page = 8
    total = len(countries)
    pages = max(1, (total + per_page - 1) // per_page)
    page = max(0, min(page, pages - 1))
    chunk = countries[page * per_page:(page + 1) * per_page]
    buttons = []
    for c in chunk:
        status_btn = "✅ ON" if c["enabled"] else "❌ OFF"
        buttons.append([InlineKeyboardButton(f"{c['flag']} {c['name']} [{status_btn}]", callback_data=f"togglec_{c['code']}")])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"toggle_countries_{page-1}"))
        nav.append(InlineKeyboardButton(f"{page+1}/{pages}", callback_data="noop"))
    if page < pages - 1:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"toggle_countries_{page+1}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="admin_countries")])
    await query.edit_message_text("🔛 *Enable/Disable Countries*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))

async def togglec_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    code = query.data.split("togglec_")[1]
    toggle_country_enabled(code)
    row = get_country(code) or {}
    new_val = row.get("enabled", 0)
    await query.answer(f"{'✅ Enabled' if new_val else '❌ Disabled'}")
    query.data = "toggle_countries_0"
    await toggle_countries(update, context)

# ── ORDERS (ADMIN) ─────────────────────────────────────────────────────────────
async def admin_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    parts = query.data.split("_")
    status_filter = parts[2]
    page = int(parts[3])
    orders = orders_admin_list(status_filter)
    filter_btns = [
        InlineKeyboardButton("⏳ Pending", callback_data="admin_orders_pending_0"),
        InlineKeyboardButton("✅ Approved", callback_data="admin_orders_approved_0"),
        InlineKeyboardButton("❌ Rejected", callback_data="admin_orders_rejected_0"),
    ]
    per_page = 5
    total = len(orders)
    pages = max(1, (total + per_page - 1) // per_page)
    page = max(0, min(page, pages - 1))
    chunk = orders[page * per_page:(page + 1) * per_page]
    buttons = [filter_btns]
    for o in chunk:
        row_btns = [InlineKeyboardButton(
            f"#{o['id']} {o['flag'] or ''}{o['cname'] or '?'} ₹{o['amount_inr']:.0f} {status_emoji(o['status'])}",
            callback_data=f"admin_order_view_{o['id']}"
        )]
        buttons.append(row_btns)
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"admin_orders_{status_filter}_{page-1}"))
        nav.append(InlineKeyboardButton(f"{page+1}/{pages}", callback_data="noop"))
    if page < pages - 1:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"admin_orders_{status_filter}_{page+1}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton("🔙 Admin Menu", callback_data="admin_menu")])
    await query.edit_message_text(f"💰 *Orders ({status_filter.title()})*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))

async def admin_order_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    order_id = int(query.data.split("_")[3])
    o = get_order_by_id(order_id)
    if o:
        ch = get_country(o.get("country_code") or "")
        o = dict(o)
        o["flag"] = ch["flag"] if ch else None
        o["cname"] = ch["name"] if ch else None
    if not o:
        await query.edit_message_text("Order not found.")
        return
    text = (
        f"📦 *Order #{o['id']}*\n"
        f"👤 User: {o['username']} (ID: {o['user_id']})\n"
        f"🌍 Country: {o['flag'] or ''} {o['cname'] or 'N/A'}\n"
        f"💰 ₹{o['amount_inr']:.0f} INR\n"
        f"💳 Method: UPI\n"
        f"📊 Status: {status_emoji(o['status'])} {o['status'].title()}\n"
        f"📅 {fmt_time(o['created_at'])}"
    )
    buttons = []
    if o["status"] == "pending":
        buttons.append([
            ibutton_raw(
                "✅ Approve",
                callback_data=f"approve_order_{order_id}",
                icon_slot="check",
                style="success",
            ),
            ibutton_raw(
                "❌ Reject",
                callback_data=f"reject_order_{order_id}",
                icon_slot="cross",
                style="danger",
            ),
        ])
    buttons.append(
        [ibutton_raw("🔙 Orders", callback_data="admin_orders_all_0", icon_slot="package", style="primary")]
    )
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))

# ── USERS (ADMIN) ──────────────────────────────────────────────────────────────
async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Search Users", callback_data="admin_search_user")],
        [InlineKeyboardButton("🚫 Ban Users", callback_data="admin_ban_user")],
        [InlineKeyboardButton("✅ Unban Users", callback_data="admin_unban_user")],
        [InlineKeyboardButton("💰 Edit Wallet Balance", callback_data="admin_edit_wallet")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_menu")],
    ])
    await query.edit_message_text("👥 *Users Manager*", parse_mode="Markdown", reply_markup=kb)

async def admin_search_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    context.user_data["awaiting_search_user"] = True
    await query.edit_message_text("Enter user ID or @username:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="admin_users")]]))

async def admin_ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    context.user_data["awaiting_search_user"] = True
    context.user_data["ban_action"] = "ban"
    await query.edit_message_text("Enter user ID or @username to ban:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="admin_users")]]))

async def admin_unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    context.user_data["awaiting_search_user"] = True
    context.user_data["ban_action"] = "unban"
    await query.edit_message_text("Enter user ID or @username to unban:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="admin_users")]]))

async def admin_edit_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    context.user_data["awaiting_search_user"] = True
    context.user_data["wallet_action"] = True
    await query.edit_message_text("Enter user ID or @username to edit wallet:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="admin_users")]]))

async def _show_user_profile(update, context, row, via_message=False):
    text = (
        f"👤 *{row['first_name']}* (@{row['username']})\n"
        f"ID: `{row['id']}`\n"
        f"💰 Wallet: ₹{row['wallet_balance']:.2f} INR\n"
        f"🛒 Purchases: {row['total_purchases']}\n"
        f"🚫 Banned: {'Yes' if row['is_banned'] else 'No'}\n"
        f"📅 Joined: {fmt_time(row['joined_at'])}"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚫 Ban", callback_data=f"ban_uid_{row['id']}"),
         InlineKeyboardButton("💰 Edit Balance", callback_data=f"editbal_uid_{row['id']}")],
        [InlineKeyboardButton("✅ Unban", callback_data=f"unban_uid_{row['id']}")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_users")],
    ])
    if via_message:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)
    else:
        await safe_edit_callback_message(
            update.callback_query,
            text=text,
            parse_mode="Markdown",
            reply_markup=kb,
        )

async def ban_uid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("❌ Not authorized.", show_alert=True)
        return
    uid = int(query.data.split("_")[2])
    ban_user(uid)
    await query.answer("🚫 User banned!", show_alert=True)

async def unban_uid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("❌ Not authorized.", show_alert=True)
        return
    uid = int(query.data.split("_")[2])
    unban_user(uid)
    await query.answer("✅ User unbanned!", show_alert=True)

async def editbal_uid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    uid = int(query.data.split("_")[2])
    context.user_data["admin_edit_balance_uid"] = uid
    await query.edit_message_text(
        "Enter amount to add or deduct (e.g. +500 or -200 INR):",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="admin_users")]])
    )

# ── DEPOSITS (ADMIN) ───────────────────────────────────────────────────────────
async def admin_deps(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    parts = query.data.split("_")
    status_filter = parts[2]
    page = int(parts[3])
    deps = deposits_admin_list(status_filter)
    filter_btns = [
        InlineKeyboardButton("⏳ Pending", callback_data="admin_deps_pending_0"),
        InlineKeyboardButton("✅ Approved", callback_data="admin_deps_approved_0"),
        InlineKeyboardButton("❌ Rejected", callback_data="admin_deps_rejected_0"),
    ]
    per_page = 5
    total = len(deps)
    pages = max(1, (total + per_page - 1) // per_page)
    page = max(0, min(page, pages - 1))
    chunk = deps[page * per_page:(page + 1) * per_page]
    buttons = [filter_btns]
    for d in chunk:
        row_btns = [InlineKeyboardButton(
            f"#{d['id']} uid:{d['user_id']} ₹{d['amount_inr']:.0f} {status_emoji(d['status'])}",
            callback_data=f"admin_dep_view_{d['id']}"
        )]
        buttons.append(row_btns)
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"admin_deps_{status_filter}_{page-1}"))
        nav.append(InlineKeyboardButton(f"{page+1}/{pages}", callback_data="noop"))
    if page < pages - 1:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"admin_deps_{status_filter}_{page+1}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton("🔙 Admin Menu", callback_data="admin_menu")])
    await query.edit_message_text(f"💳 *Deposits ({status_filter.title()})*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))

async def admin_dep_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    dep_id = int(query.data.split("_")[3])
    d = get_deposit_by_id(dep_id)
    if not d:
        await query.edit_message_text("Deposit not found.")
        return
    text = (
        f"💳 *Deposit #{d['id']}*\n"
        f"👤 User ID: {d['user_id']}\n"
        f"💵 ₹{d['amount_inr']:.0f} INR\n"
        f"💳 Method: UPI\n"
        f"📊 Status: {status_emoji(d['status'])} {d['status'].title()}\n"
        f"📅 {fmt_time(d['created_at'])}"
    )
    buttons = []
    if d["status"] == "pending":
        buttons.append([
            ibutton_raw(
                "✅ Approve",
                callback_data=f"approve_deposit_{dep_id}",
                icon_slot="check",
                style="success",
            ),
            ibutton_raw(
                "❌ Reject",
                callback_data=f"reject_deposit_{dep_id}",
                icon_slot="cross",
                style="danger",
            ),
        ])
    buttons.append(
        [ibutton_raw("🔙 Deposits", callback_data="admin_deps_all_0", icon_slot="wallet", style="success")]
    )
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))

# ── STATS ──────────────────────────────────────────────────────────────────────
async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    s = admin_stats_row()
    total_users = s["total_users"]
    total_stock = s["total_stock"]
    avail_stock = s["avail_stock"]
    sold = s["sold"]
    revenue = s["revenue"]
    pending_orders = s["pending_orders"]
    pending_deps = s["pending_deps"]
    banned = s["banned"]
    text = (
        f"📊 *Bot Statistics*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 Total Users: {total_users}\n"
        f"📦 Total Stock: {total_stock} (available: {avail_stock})\n"
        f"✅ Accounts Sold: {sold}\n"
        f"💵 Total Revenue: ₹{revenue:.0f} INR\n"
        f"⏳ Pending Orders: {pending_orders}\n"
        f"💳 Pending Deposits: {pending_deps}\n"
        f"🚫 Banned Users: {banned}\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin Menu", callback_data="admin_menu")]])
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)

# ── SETTINGS ───────────────────────────────────────────────────────────────────
async def admin_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    maintenance = get_setting("maintenance", "0")
    maint_label = "🔧 Maintenance: ON → Turn OFF" if maintenance == "1" else "🔧 Maintenance: OFF → Turn ON"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 Welcome Message", callback_data="edit_welcome_msg")],
        [InlineKeyboardButton(maint_label, callback_data="toggle_maintenance")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_menu")],
    ])
    await query.edit_message_text("⚙️ *Settings*", parse_mode="Markdown", reply_markup=kb)

async def edit_welcome_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    context.user_data["awaiting_welcome_msg"] = True
    await query.edit_message_text("Send new welcome message:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="admin_settings")]]))

async def toggle_maintenance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    current = get_setting("maintenance", "0")
    new_val = "0" if current == "1" else "1"
    set_setting("maintenance", new_val)
    status = "ON" if new_val == "1" else "OFF"
    await query.answer(f"🔧 Maintenance mode turned {status}!", show_alert=True)
    await admin_settings(update, context)

# ── BROADCAST ──────────────────────────────────────────────────────────────────
async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    context.user_data["awaiting_broadcast"] = True
    await query.edit_message_text(
        "📢 Send the message to broadcast:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_menu")]])
    )

async def broadcast_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    msg_id = context.user_data.get("broadcast_msg_id")
    chat_id = context.user_data.get("broadcast_chat_id")
    if not msg_id or not chat_id:
        await query.edit_message_text("❌ No message to broadcast.")
        return
    user_ids = broadcast_recipient_ids()
    success = 0
    for uid in user_ids:
        try:
            await context.bot.copy_message(chat_id=uid, from_chat_id=chat_id, message_id=msg_id)
            success += 1
        except Exception:
            pass
    await query.edit_message_text(f"✅ Broadcast sent to {success}/{len(user_ids)} users.")
    context.user_data.pop("broadcast_msg_id", None)
    context.user_data.pop("broadcast_chat_id", None)

# ─── /skip COMMAND ────────────────────────────────────────────────────────────
async def skip_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("add_acc_step") == "twofa":
        context.user_data["add_acc_2fa"] = None
        context.user_data["add_acc_step"] = "price_inr"
        await update.message.reply_text(
            "⏭ 2FA skipped!\n\n💰 Enter price in INR:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⏭ Skip (use country price)", callback_data="add_acc_skip_price")]])
        )

# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    async def _global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
        # Keep logs clean: avoid long stack traces in terminal.
        err = context.error
        logger.error(f"Bot error: {type(err).__name__}: {err}")

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_cmd))
    app.add_handler(CommandHandler("update", update_cmd))
    app.add_handler(CommandHandler("skip", skip_cmd))
    # Main navigation
    app.add_handler(CallbackQueryHandler(main_menu_cb, pattern="^main_menu$"))
    app.add_handler(CallbackQueryHandler(browse_numbers, pattern=r"^browse_\d+$"))
    app.add_handler(CallbackQueryHandler(oos_callback, pattern=r"^oos_"))
    app.add_handler(CallbackQueryHandler(noop_callback, pattern="^noop$"))
    app.add_handler(CallbackQueryHandler(country_detail, pattern=r"^country_[A-Z]+$"))
    app.add_handler(CallbackQueryHandler(wallet_buy, pattern=r"^wallet_buy_"))
    app.add_handler(CallbackQueryHandler(pay_method, pattern=r"^pay_method_"))
    app.add_handler(CallbackQueryHandler(buy_upload_prompt, pattern=r"^buy_upload_"))
    app.add_handler(CallbackQueryHandler(reveal_number, pattern=r"^reveal_\d+$"))
    app.add_handler(CallbackQueryHandler(get_otp, pattern=r"^getotp_\d+$"))
    app.add_handler(CallbackQueryHandler(getotp_back, pattern=r"^getotp_back_"))
    app.add_handler(CallbackQueryHandler(wallet, pattern="^wallet$"))
    app.add_handler(CallbackQueryHandler(deposit, pattern="^deposit$"))
    app.add_handler(CallbackQueryHandler(upload_dep_screenshot_cb, pattern="^upload_dep_screenshot$"))
    app.add_handler(CallbackQueryHandler(my_orders, pattern=r"^my_orders_\d+$"))
    app.add_handler(CallbackQueryHandler(order_detail, pattern=r"^order_detail_\d+$"))
    app.add_handler(CallbackQueryHandler(dep_hist, pattern=r"^dep_hist_\d+$"))
    app.add_handler(CallbackQueryHandler(help_cb, pattern="^help$"))
    # Admin group approvals
    app.add_handler(CallbackQueryHandler(approve_order, pattern=r"^approve_order_\d+$"))
    app.add_handler(CallbackQueryHandler(reject_order, pattern=r"^reject_order_\d+$"))
    app.add_handler(CallbackQueryHandler(approve_deposit, pattern=r"^approve_deposit_\d+$"))
    app.add_handler(CallbackQueryHandler(reject_deposit, pattern=r"^reject_deposit_\d+$"))
    # Admin panel
    app.add_handler(CallbackQueryHandler(admin_menu_cb, pattern="^admin_menu$"))
    app.add_handler(CallbackQueryHandler(admin_close, pattern="^admin_close$"))
    app.add_handler(CallbackQueryHandler(admin_stock, pattern="^admin_stock$"))
    app.add_handler(CallbackQueryHandler(add_acc_start, pattern="^add_acc_start$"))
    app.add_handler(CallbackQueryHandler(add_acc_skip_2fa, pattern="^add_acc_skip_2fa$"))
    app.add_handler(CallbackQueryHandler(add_acc_skip_price, pattern="^add_acc_skip_price$"))
    app.add_handler(CallbackQueryHandler(view_stock, pattern=r"^view_stock_\d+$"))
    app.add_handler(CallbackQueryHandler(remove_acc, pattern="^remove_acc$"))
    app.add_handler(CallbackQueryHandler(confirm_del, pattern=r"^confirm_del_\d+$"))
    app.add_handler(CallbackQueryHandler(admin_countries, pattern="^admin_countries$"))
    app.add_handler(CallbackQueryHandler(set_prices, pattern=r"^set_prices_\d+$"))
    app.add_handler(CallbackQueryHandler(setprice_cb, pattern=r"^setprice_"))
    app.add_handler(CallbackQueryHandler(toggle_countries, pattern=r"^toggle_countries_\d+$"))
    app.add_handler(CallbackQueryHandler(togglec_cb, pattern=r"^togglec_"))
    app.add_handler(CallbackQueryHandler(admin_orders, pattern=r"^admin_orders_[a-z]+_\d+$"))
    app.add_handler(CallbackQueryHandler(admin_order_view, pattern=r"^admin_order_view_\d+$"))
    app.add_handler(CallbackQueryHandler(admin_users, pattern="^admin_users$"))
    app.add_handler(CallbackQueryHandler(admin_search_user, pattern="^admin_search_user$"))
    app.add_handler(CallbackQueryHandler(admin_ban_user, pattern="^admin_ban_user$"))
    app.add_handler(CallbackQueryHandler(admin_unban_user, pattern="^admin_unban_user$"))
    app.add_handler(CallbackQueryHandler(admin_edit_wallet, pattern="^admin_edit_wallet$"))
    app.add_handler(CallbackQueryHandler(ban_uid, pattern=r"^ban_uid_\d+$"))
    app.add_handler(CallbackQueryHandler(unban_uid, pattern=r"^unban_uid_\d+$"))
    app.add_handler(CallbackQueryHandler(editbal_uid, pattern=r"^editbal_uid_\d+$"))
    app.add_handler(CallbackQueryHandler(admin_deps, pattern=r"^admin_deps_[a-z]+_\d+$"))
    app.add_handler(CallbackQueryHandler(admin_dep_view, pattern=r"^admin_dep_view_\d+$"))
    app.add_handler(CallbackQueryHandler(admin_stats, pattern="^admin_stats$"))
    app.add_handler(CallbackQueryHandler(admin_settings, pattern="^admin_settings$"))
    app.add_handler(CallbackQueryHandler(edit_welcome_msg, pattern="^edit_welcome_msg$"))
    app.add_handler(CallbackQueryHandler(toggle_maintenance, pattern="^toggle_maintenance$"))
    app.add_handler(CallbackQueryHandler(admin_broadcast, pattern="^admin_broadcast$"))
    app.add_handler(CallbackQueryHandler(broadcast_confirm, pattern="^broadcast_confirm$"))
    # Message handlers
    app.add_handler(MessageHandler(filters.PHOTO, screenshot_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    app.add_error_handler(_global_error_handler)
    logger.info("Bot started!")
    try:
        app.run_polling(drop_pending_updates=True)
    except Exception as e:
        # Common when 2 instances are started with the same token.
        if "Conflict" in str(e) and "getUpdates" in str(e):
            logger.error("Multiple bot instances detected. Stop older instance and restart.")
            return
        raise

if __name__ == "__main__":
    main()
