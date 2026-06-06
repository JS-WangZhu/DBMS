from flask import Blueprint, request
from sqlalchemy import or_

from app.api.routes.common import active_user_required, admin_required
from app.extensions import db
from app.models.aliyun_dns import AliyunDomainConfig
from app.services.aliyun_dns import call_alidns_api
from app.services.audit import log_audit
from app.utils.response import error_response, ok_response

bp = Blueprint("aliyun_dns", __name__, url_prefix="/aliyun-dns")


def _page_params():
    try:
        page = int(request.args.get("page", "1"))
    except ValueError:
        page = 1
    try:
        page_size = int(request.args.get("page_size", "20"))
    except ValueError:
        page_size = 20
    return max(page, 1), min(max(page_size, 1), 200)


def _normalize_domains(raw):
    if isinstance(raw, str):
        raw = raw.replace("\n", ",").split(",")
    if not isinstance(raw, list):
        raw = []
    domains = []
    seen = set()
    for item in raw:
        domain = str(item or "").strip().lower()
        if not domain or domain in seen:
            continue
        seen.add(domain)
        domains.append(domain)
    return domains


def _get_enabled_config(config_id):
    try:
        parsed_id = int(config_id)
    except (TypeError, ValueError):
        return None
    return AliyunDomainConfig.query.filter_by(id=parsed_id, enabled=True).first()


def _config_for_domain(config_id, domain):
    config = _get_enabled_config(config_id)
    if not config:
        return None, error_response("domain config not found or disabled", code=404)
    if not config.manages_domain(domain):
        return None, error_response("domain is not managed by this config", code=400)
    return config, None


def _record_payload(payload, require_domain=False):
    domain = (payload.get("domain") or "").strip().lower()
    rr = (payload.get("rr") or payload.get("RR") or "").strip()
    record_type = (payload.get("type") or payload.get("Type") or "").strip().upper()
    value = (payload.get("value") or payload.get("Value") or "").strip()
    ttl = payload.get("ttl", payload.get("TTL", 600))
    line = (payload.get("line") or payload.get("Line") or "").strip()
    priority = payload.get("priority", payload.get("Priority"))

    if require_domain and not domain:
        return None, "domain is required"
    if not rr:
        return None, "rr is required"
    if not record_type:
        return None, "type is required"
    if not value:
        return None, "value is required"
    try:
        ttl = int(ttl)
    except (TypeError, ValueError):
        return None, "ttl must be an integer"

    params = {"RR": rr, "Type": record_type, "Value": value, "TTL": ttl}
    if line:
        params["Line"] = line
    if priority not in (None, ""):
        try:
            params["Priority"] = int(priority)
        except (TypeError, ValueError):
            return None, "priority must be an integer"
    return {"domain": domain, "params": params}, None


@bp.get("/configs")
@active_user_required
def list_configs():
    page, page_size = _page_params()
    keyword = (request.args.get("keyword") or "").strip()
    enabled = request.args.get("enabled")
    query = AliyunDomainConfig.query
    if enabled is not None:
        query = query.filter_by(enabled=(enabled.lower() == "true"))
    if keyword:
        query = query.filter(
            or_(
                AliyunDomainConfig.name.like(f"%{keyword}%"),
                AliyunDomainConfig.description.like(f"%{keyword}%"),
            )
        )
    total = query.count()
    rows = query.order_by(AliyunDomainConfig.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return ok_response(data={"items": [row.to_dict() for row in rows], "total": total, "page": page, "page_size": page_size})


@bp.post("/configs")
@admin_required
def create_config():
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    access_key = (payload.get("access_key") or "").strip()
    secret_key = (payload.get("secret_key") or "").strip()
    domains = _normalize_domains(payload.get("domains"))
    if not name:
        return error_response("name is required", code=400)
    if not access_key:
        return error_response("access_key is required", code=400)
    if not secret_key:
        return error_response("secret_key is required", code=400)
    if not domains:
        return error_response("domains is required", code=400)
    if AliyunDomainConfig.query.filter_by(name=name).first():
        return error_response("name already exists", code=400)
    item = AliyunDomainConfig(
        name=name,
        description=(payload.get("description") or "").strip(),
        access_key=access_key,
        secret_key=secret_key,
        domains=domains,
        enabled=bool(payload.get("enabled", True)),
    )
    db.session.add(item)
    db.session.commit()
    log_audit(user_id=None, action="aliyun_dns.config.create", target_type="aliyun_domain_config", target_id=str(item.id))
    return ok_response(data=item.to_dict(), code=201)


@bp.patch("/configs/<int:config_id>")
@admin_required
def update_config(config_id):
    payload = request.get_json(silent=True) or {}
    item = AliyunDomainConfig.query.get_or_404(config_id)
    if "name" in payload:
        name = (payload.get("name") or "").strip()
        if not name:
            return error_response("name is required", code=400)
        existing = AliyunDomainConfig.query.filter_by(name=name).first()
        if existing and existing.id != item.id:
            return error_response("name already exists", code=400)
        item.name = name
    for field in ["description", "access_key"]:
        if field in payload:
            setattr(item, field, (payload.get(field) or "").strip())
    if "secret_key" in payload and (payload.get("secret_key") or "").strip():
        item.secret_key = (payload.get("secret_key") or "").strip()
    if "domains" in payload:
        domains = _normalize_domains(payload.get("domains"))
        if not domains:
            return error_response("domains is required", code=400)
        item.domains = domains
    if "enabled" in payload:
        item.enabled = bool(payload.get("enabled"))
    db.session.commit()
    log_audit(user_id=None, action="aliyun_dns.config.update", target_type="aliyun_domain_config", target_id=str(item.id))
    return ok_response(data=item.to_dict())


@bp.delete("/configs/<int:config_id>")
@admin_required
def delete_config(config_id):
    item = AliyunDomainConfig.query.get_or_404(config_id)
    db.session.delete(item)
    db.session.commit()
    log_audit(user_id=None, action="aliyun_dns.config.delete", target_type="aliyun_domain_config", target_id=str(config_id))
    return ok_response(message="deleted")


@bp.get("/records")
@active_user_required
def list_records():
    config, err = _config_for_domain(request.args.get("config_id"), request.args.get("domain"))
    if err:
        return err
    page, page_size = _page_params()
    params = {
        "DomainName": request.args.get("domain").strip().lower(),
        "PageNumber": page,
        "PageSize": page_size,
        "RRKeyWord": (request.args.get("rr_keyword") or "").strip(),
        "TypeKeyWord": (request.args.get("type_keyword") or "").strip(),
        "ValueKeyWord": (request.args.get("value_keyword") or "").strip(),
    }
    try:
        data = call_alidns_api(config, "DescribeDomainRecords", params)
    except RuntimeError as exc:
        return error_response(str(exc), code=502)
    records = data.get("DomainRecords", {}).get("Record", [])
    total = data.get("TotalCount", len(records))
    return ok_response(data={"items": records, "total": total, "page": page, "page_size": page_size, "raw": data})


@bp.post("/records")
@admin_required
def create_record():
    payload = request.get_json(silent=True) or {}
    record, message = _record_payload(payload, require_domain=True)
    if message:
        return error_response(message, code=400)
    config, err = _config_for_domain(payload.get("config_id"), record["domain"])
    if err:
        return err
    params = {"DomainName": record["domain"], **record["params"]}
    try:
        data = call_alidns_api(config, "AddDomainRecord", params)
    except RuntimeError as exc:
        return error_response(str(exc), code=502)
    log_audit(user_id=None, action="aliyun_dns.record.create", target_type="domain", target_id=record["domain"], detail=params)
    return ok_response(data=data, code=201)


@bp.patch("/records/<record_id>")
@admin_required
def update_record(record_id):
    payload = request.get_json(silent=True) or {}
    record, message = _record_payload(payload, require_domain=True)
    if message:
        return error_response(message, code=400)
    config, err = _config_for_domain(payload.get("config_id"), record["domain"])
    if err:
        return err
    params = {"RecordId": record_id, **record["params"]}
    try:
        data = call_alidns_api(config, "UpdateDomainRecord", params)
    except RuntimeError as exc:
        return error_response(str(exc), code=502)
    log_audit(user_id=None, action="aliyun_dns.record.update", target_type="dns_record", target_id=record_id, detail=params)
    return ok_response(data=data)


@bp.delete("/records/<record_id>")
@admin_required
def delete_record(record_id):
    config, err = _config_for_domain(request.args.get("config_id"), request.args.get("domain"))
    if err:
        return err
    try:
        data = call_alidns_api(config, "DeleteDomainRecord", {"RecordId": record_id})
    except RuntimeError as exc:
        return error_response(str(exc), code=502)
    log_audit(user_id=None, action="aliyun_dns.record.delete", target_type="dns_record", target_id=record_id)
    return ok_response(data=data)
