import base64
import hashlib
import hmac
import time
import uuid
from urllib.parse import quote

import requests


ALIDNS_ENDPOINT = "https://alidns.aliyuncs.com/"


def _percent_encode(value):
    return quote(str(value), safe="").replace("+", "%20").replace("*", "%2A").replace("%7E", "~")


def _signed_params(config, action, params):
    request_params = {
        "AccessKeyId": config.access_key,
        "Action": action,
        "Format": "JSON",
        "SignatureMethod": "HMAC-SHA1",
        "SignatureNonce": str(uuid.uuid4()),
        "SignatureVersion": "1.0",
        "Timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "Version": "2015-01-09",
    }
    request_params.update({key: value for key, value in params.items() if value is not None and value != ""})
    canonicalized = "&".join(
        f"{_percent_encode(key)}={_percent_encode(request_params[key])}"
        for key in sorted(request_params)
    )
    string_to_sign = "GET&%2F&" + _percent_encode(canonicalized)
    key = (config.secret_key + "&").encode("utf-8")
    digest = hmac.new(key, string_to_sign.encode("utf-8"), hashlib.sha1).digest()
    request_params["Signature"] = base64.b64encode(digest).decode("utf-8")
    return request_params


def call_alidns_api(config, action, params, timeout=10):
    signed = _signed_params(config, action, params)
    response = requests.get(ALIDNS_ENDPOINT, params=signed, timeout=timeout)
    try:
        payload = response.json()
    except ValueError:
        payload = {"Message": response.text}
    if response.status_code >= 400 or "Code" in payload:
        message = payload.get("Message") or payload.get("Code") or "Aliyun DNS API error"
        raise RuntimeError(message)
    return payload
