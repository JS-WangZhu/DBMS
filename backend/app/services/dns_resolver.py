import socket


def list_host_addresses(host_input: str):
    try:
        addresses = socket.gethostbyname_ex(host_input)[2]
    except socket.gaierror:
        return []
    if not addresses:
        return []
    unique_addresses = []
    seen = set()
    for address in addresses:
        value = str(address or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        unique_addresses.append(value)
    return unique_addresses


def resolve_host(host_input: str):
    addresses = list_host_addresses(host_input)
    if not addresses:
        return None
    return addresses[0]


def instance_domain(instance):
    extra = instance.extra_json if isinstance(instance.extra_json, dict) else {}
    domain = str(extra.get("domain") or "").strip()
    return domain or None


def resolve_target_for_instance(instance):
    return instance_domain(instance) or instance.host_input


def resolve_and_update_instance(instance):
    old_ip = instance.resolved_ip
    new_ip = resolve_host(resolve_target_for_instance(instance))
    if new_ip:
        instance.resolved_ip = new_ip
    changed = bool(old_ip and new_ip and old_ip != new_ip)
    return changed, old_ip, new_ip


def refresh_all_dns(instances):
    results = []
    for instance in instances:
        changed, old_ip, new_ip = resolve_and_update_instance(instance)
        results.append(
            {
                "instance_id": instance.id,
                "host_input": instance.host_input,
                "host_domain": instance_domain(instance),
                "changed": changed,
                "old_ip": old_ip,
                "new_ip": new_ip,
            }
        )
    return results
