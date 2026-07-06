import ipaddress


def normalize_cidrs(values):
    if not isinstance(values, (list, tuple)) or not values:
        raise ValueError("CIDR list is required")

    networks = []
    for value in values:
        try:
            network = ipaddress.ip_network(str(value).strip(), strict=False)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid CIDR: {value}") from exc
        networks.append(network)

    unique = {str(network): network for network in networks}
    return [str(network) for network in sorted(unique.values(), key=lambda item: (item.version, int(item.network_address), item.prefixlen))]


def validate_non_overlapping_cidrs(candidate_cidrs, existing_configs, exclude_id=None):
    candidates = [ipaddress.ip_network(value, strict=False) for value in normalize_cidrs(candidate_cidrs)]
    for config_id, cidrs in existing_configs:
        if exclude_id is not None and int(config_id) == int(exclude_id):
            continue
        for existing_value in cidrs or []:
            existing = ipaddress.ip_network(existing_value, strict=False)
            for candidate in candidates:
                if candidate.version == existing.version and candidate.overlaps(existing):
                    raise ValueError(f"CIDR overlap: {candidate} and {existing}")
