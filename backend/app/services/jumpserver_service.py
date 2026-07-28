import string
from urllib.parse import quote, urlparse

import requests


DEFAULT_WEB_URL_TEMPLATE = "{base_url}/luna/?asset={asset_id}"


def normalize_base_url(value):
    base_url = str(value or "").strip().rstrip("/")
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("base_url must be an absolute http or https URL")
    if parsed.username or parsed.password:
        raise ValueError("base_url must not contain credentials")
    if parsed.query or parsed.fragment:
        raise ValueError("base_url must not contain a query string or fragment")
    return base_url


def validate_web_url_template(value, base_url):
    template = str(value or DEFAULT_WEB_URL_TEMPLATE).strip()
    if "{base_url}" not in template or "{asset_id}" not in template:
        raise ValueError("web_url_template must contain {base_url} and {asset_id}")
    try:
        fields = list(string.Formatter().parse(template))
    except ValueError as exc:
        raise ValueError("web_url_template is invalid") from exc
    for _literal, field_name, format_spec, conversion in fields:
        if field_name is not None and field_name not in {"base_url", "asset_id"}:
            raise ValueError("web_url_template contains unsupported placeholders")
        if format_spec or conversion:
            raise ValueError("web_url_template contains unsupported formatting")
    try:
        rendered = template.format(base_url=base_url, asset_id="asset-id")
    except (KeyError, ValueError) as exc:
        raise ValueError("web_url_template contains unsupported placeholders") from exc

    base = urlparse(base_url)
    target = urlparse(rendered)
    if target.scheme != base.scheme or target.netloc != base.netloc:
        raise ValueError("web_url_template must point to the configured JumpServer host")
    return template


def build_jumpserver_access_url(config, asset_id):
    base_url = normalize_base_url(config.base_url)
    template = validate_web_url_template(config.web_url_template, base_url)
    encoded_asset_id = quote(str(asset_id or "").strip(), safe="")
    if not encoded_asset_id:
        raise ValueError("jumpserver asset id is required")
    return template.format(base_url=base_url, asset_id=encoded_asset_id)


def test_jumpserver_connection(config, timeout=5):
    base_url = normalize_base_url(config.base_url)
    response = requests.get(
        base_url,
        timeout=timeout,
        verify=bool(config.verify_ssl),
        allow_redirects=True,
    )
    if response.status_code >= 500:
        raise ValueError(f"JumpServer returned HTTP {response.status_code}")
    return response.status_code
