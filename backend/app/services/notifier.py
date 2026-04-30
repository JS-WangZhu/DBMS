import json
import smtplib
import ssl
import urllib.request
from datetime import datetime
from email.mime.text import MIMEText

from flask import current_app

from app.models.notify_target import BackupNotifyTarget


def _to_channel_set(policy):
    channels = []
    extra = policy.extra_json or {}
    notify_cfg = extra.get("notify") or {}

    if isinstance(notify_cfg.get("channels"), list):
        channels = notify_cfg.get("channels")
    elif current_app.config.get("BACKUP_NOTIFY_CHANNELS"):
        channels = [item.strip() for item in current_app.config.get("BACKUP_NOTIFY_CHANNELS", "").split(",") if item.strip()]

    return set(channels)


def _get_target_rows(policy):
    extra = policy.extra_json or {}
    notify_cfg = extra.get("notify") or {}
    ids = notify_cfg.get("target_ids") or []
    valid_ids = []
    for item in ids:
        try:
            valid_ids.append(int(item))
        except Exception:
            continue

    if not valid_ids:
        return []

    rows = BackupNotifyTarget.query.filter(BackupNotifyTarget.id.in_(valid_ids), BackupNotifyTarget.enabled.is_(True)).all()
    return rows


def _send_wecom_markdown(content: str, webhook: str = None):
    webhook_url = webhook or current_app.config.get("WECHAT_WEBHOOK_URL")
    if not webhook_url:
        return {"ok": False, "message": "WECHAT_WEBHOOK_URL not configured"}

    payload = {"msgtype": "markdown", "markdown": {"content": content}}
    data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(webhook_url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=8) as resp:
        body = resp.read().decode("utf-8")

    return {"ok": True, "message": body}


def _send_email(subject: str, content: str, recipients=None):
    host = current_app.config.get("SMTP_HOST")
    port = current_app.config.get("SMTP_PORT")
    user = current_app.config.get("SMTP_USER")
    password = current_app.config.get("SMTP_PASSWORD")
    use_tls = current_app.config.get("SMTP_USE_TLS", True)
    sender = current_app.config.get("SMTP_FROM") or user

    if recipients is None:
        to_raw = current_app.config.get("SMTP_TO", "")
        recipients = [item.strip() for item in to_raw.split(",") if item.strip()]

    if not host or not sender or not recipients:
        return {"ok": False, "message": "SMTP config incomplete"}

    msg = MIMEText(content, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ",".join(recipients)

    if use_tls:
        server = smtplib.SMTP(host, port, timeout=8)
        server.starttls(context=ssl.create_default_context())
    else:
        server = smtplib.SMTP(host, port, timeout=8)

    if user and password:
        server.login(user, password)
    server.sendmail(sender, recipients, msg.as_string())
    server.quit()
    return {"ok": True, "message": "email sent"}


def notify_ha_switch_completion(config, cluster, switch_type: str, result: dict, operator_name: str = None):
    if not config:
        return {"ok": False, "message": "ha config not found", "results": {"targets": []}}

    target_ids = config.get_notify_target_ids() if hasattr(config, "get_notify_target_ids") else []
    if not target_ids:
        return {"ok": False, "message": "no notify targets configured", "results": {"targets": []}}

    targets = (
        BackupNotifyTarget.query.filter(
            BackupNotifyTarget.id.in_(target_ids),
            BackupNotifyTarget.enabled.is_(True),
            BackupNotifyTarget.channel == "wecom",
        )
        .order_by(BackupNotifyTarget.id.asc())
        .all()
    )
    if not targets:
        return {"ok": False, "message": "no enabled wecom targets configured", "results": {"targets": []}}

    switch_label = {
        "normal": "在线切换",
        "failure": "故障切换",
        "promote": "推广",
        "repair": "集群修复",
    }.get(switch_type, switch_type or "未知动作")
    rebuild = result.get("other_replica_rebuild") or {}
    rebuild_ok = len(rebuild.get("rebuilt") or [])
    rebuild_failed = len(rebuild.get("failed") or [])
    switch_script = result.get("switch_script") or {}
    business = cluster.business_line or cluster.namespace or "-"
    finished_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        "# MySQL HA切换完成",
        f"> 集群: <font color=\"comment\">{business}/{cluster.environment or '-'}/{cluster.name}</font>",
        f"> 模式: <font color=\"warning\">{switch_label}</font>",
        f"> 高可用域名: <font color=\"comment\">{cluster.ha_domain or '-'}</font>",
        f"> 新主库ID: <font color=\"info\">{result.get('new_master_instance_id') or '-'}</font>",
        f"> 原主库ID: <font color=\"comment\">{result.get('old_master_instance_id') or '-'}</font>",
        f"> 其他从库重挂: <font color=\"info\">成功 {rebuild_ok} 台，失败 {rebuild_failed} 台</font>",
        f"> 切换脚本: <font color=\"comment\">{switch_script.get('script_name') or '-'}</font>",
        f"> 执行人: <font color=\"comment\">{operator_name or '系统'}</font>",
        f"> 完成时间: <font color=\"comment\">{finished_at}</font>",
    ]
    failed_rows = rebuild.get("failed") or []
    if failed_rows:
        details = "; ".join(
            f"{item.get('instance_name') or item.get('instance_id')}: {item.get('error') or '-'}" for item in failed_rows[:5]
        )
        lines.append(f"> 重挂失败详情: <font color=\"warning\">{details}</font>")
    content = "\n".join(lines)

    results = {"targets": []}
    for target in targets:
        try:
            send_result = _send_wecom_markdown(content=content, webhook=target.address)
        except Exception as exc:
            send_result = {"ok": False, "message": str(exc)}
        results["targets"].append(
            {
                "target_id": target.id,
                "name": target.name,
                "channel": target.channel,
                "address": target.address,
                "result": send_result,
            }
        )

    ok = any(item.get("result", {}).get("ok") for item in results["targets"])
    return {"ok": ok, "results": results}


def notify_backup_failure(policy, instance, error_message, command=None):
    channels = _to_channel_set(policy)
    targets = _get_target_rows(policy)
    results = {"targets": []}

    instance_desc = f"{instance.db_type}:{instance.host_input}:{instance.port}" if instance else f"policy:{policy.id}"
    content = (
        f"备份失败告警\n"
        f"策略: {policy.name}(#{policy.id})\n"
        f"目标: {instance_desc}\n"
        f"错误: {error_message}\n"
        f"命令: {' '.join(command or [])}"
    )

    if targets:
        for target in targets:
            if target.channel == "wecom":
                try:
                    send_result = _send_wecom_markdown(content=content, webhook=target.address)
                except Exception as exc:
                    send_result = {"ok": False, "message": str(exc)}
            elif target.channel == "email":
                try:
                    send_result = _send_email(subject=f"[DBMS] 备份失败 #{policy.id}", content=content, recipients=[target.address])
                except Exception as exc:
                    send_result = {"ok": False, "message": str(exc)}
            else:
                send_result = {"ok": False, "message": f"unsupported channel: {target.channel}"}

            results["targets"].append(
                {
                    "target_id": target.id,
                    "name": target.name,
                    "channel": target.channel,
                    "address": target.address,
                    "result": send_result,
                }
            )

    # fallback global channels when no explicit target configured
    if not targets:
        if not channels:
            return {"ok": False, "message": "no notification channels configured"}

        if "wecom" in channels:
            try:
                results["wecom"] = _send_wecom_markdown(content)
            except Exception as exc:
                results["wecom"] = {"ok": False, "message": str(exc)}

        if "email" in channels:
            try:
                results["email"] = _send_email(subject=f"[DBMS] 备份失败 #{policy.id}", content=content)
            except Exception as exc:
                results["email"] = {"ok": False, "message": str(exc)}

    ok = False
    if targets:
        ok = any(item.get("result", {}).get("ok") for item in results["targets"])
    else:
        ok = any(item.get("ok") for key, item in results.items() if key != "targets")

    return {"ok": ok, "results": results}


def test_notify_target(target: BackupNotifyTarget, content: str = None):
    message = content or "DBMS 通知测试\n该消息用于验证通知通道是否可用。"
    if target.channel == "wecom":
        try:
            send_result = _send_wecom_markdown(content=message, webhook=target.address)
        except Exception as exc:
            send_result = {"ok": False, "message": str(exc)}
    elif target.channel == "email":
        try:
            send_result = _send_email(subject="[DBMS] 通知测试", content=message, recipients=[target.address])
        except Exception as exc:
            send_result = {"ok": False, "message": str(exc)}
    else:
        send_result = {"ok": False, "message": f"unsupported channel: {target.channel}"}

    return {
        "target_id": target.id,
        "name": target.name,
        "channel": target.channel,
        "address": target.address,
        "result": send_result,
    }


def notify_with_targets(target_ids, title: str, content: str):
    valid_ids = []
    for item in target_ids or []:
        try:
            valid_ids.append(int(item))
        except Exception:
            continue
    if not valid_ids:
        return {"ok": False, "message": "no notify targets configured", "results": {"targets": []}}

    targets = (
        BackupNotifyTarget.query
        .filter(BackupNotifyTarget.id.in_(valid_ids), BackupNotifyTarget.enabled.is_(True))
        .order_by(BackupNotifyTarget.id.asc())
        .all()
    )
    if not targets:
        return {"ok": False, "message": "no enabled notify targets", "results": {"targets": []}}

    results = {"targets": []}
    for target in targets:
        if target.channel == "wecom":
            message = f"# {title}\n{content}"
            try:
                send_result = _send_wecom_markdown(content=message, webhook=target.address)
            except Exception as exc:
                send_result = {"ok": False, "message": str(exc)}
        elif target.channel == "email":
            try:
                send_result = _send_email(subject=f"[DBMS] {title}", content=content, recipients=[target.address])
            except Exception as exc:
                send_result = {"ok": False, "message": str(exc)}
        else:
            send_result = {"ok": False, "message": f"unsupported channel: {target.channel}"}
        results["targets"].append(
            {
                "target_id": target.id,
                "name": target.name,
                "channel": target.channel,
                "address": target.address,
                "result": send_result,
            }
        )

    ok = any(item.get("result", {}).get("ok") for item in results["targets"])
    return {"ok": ok, "results": results}
