import ipaddress
import ssl


def resolve_physical_address(fact):
    if bool(fact.get("vsan_enabled")):
        return "vSAN"
    value = str(fact.get("management_ip") or "").strip()
    try:
        return str(ipaddress.ip_address(value))
    except ValueError as exc:
        raise ValueError("ESXi Management VMkernel IP is unavailable") from exc


def _vm_ips(vm):
    values = set()
    primary = getattr(getattr(vm, "guest", None), "ipAddress", None)
    if primary:
        values.add(str(primary))
    for network in getattr(getattr(vm, "guest", None), "net", None) or []:
        for value in getattr(network, "ipAddress", None) or []:
            try:
                values.add(str(ipaddress.ip_address(value)))
            except ValueError:
                continue
    return sorted(values)


def _management_ip(host):
    manager_info = getattr(getattr(host, "config", None), "virtualNicManagerInfo", None)
    selected = set()
    for config in getattr(manager_info, "netConfig", None) or []:
        if str(getattr(config, "nicType", "")).lower() == "management":
            selected.update(getattr(config, "selectedVnic", None) or [])
    network = getattr(getattr(host, "config", None), "network", None)
    for vnic in getattr(network, "vnic", None) or []:
        if getattr(vnic, "key", None) not in selected and getattr(vnic, "device", None) not in selected:
            continue
        value = getattr(getattr(getattr(vnic, "spec", None), "ip", None), "ipAddress", None)
        if value:
            return str(value)
    return None


def _vsan_enabled(host):
    parent = getattr(host, "parent", None)
    configuration = getattr(parent, "configurationEx", None) or getattr(parent, "configuration", None)
    info = getattr(configuration, "vsanConfigInfo", None)
    return bool(getattr(info, "enabled", False))


def _default_connect(**kwargs):
    from pyVim.connect import SmartConnect

    context = ssl.create_default_context() if kwargs["verify_ssl"] else ssl._create_unverified_context()
    return SmartConnect(
        host=kwargs["address"],
        port=kwargs["port"],
        user=kwargs["username"],
        pwd=kwargs["password"],
        sslContext=context,
        connectionPoolTimeout=kwargs["timeout"],
    )


def _default_disconnect(session):
    from pyVim.connect import Disconnect

    Disconnect(session)


def _default_query(session):
    """Read VM and host properties only; no vSphere mutation methods are called."""
    from pyVmomi import vim

    content = session.RetrieveContent()
    view = content.viewManager.CreateContainerView(content.rootFolder, [vim.VirtualMachine], True)
    try:
        facts = []
        for vm in list(view.view):
            host = getattr(getattr(vm, "runtime", None), "host", None)
            if host is None:
                continue
            facts.append(
                {
                    "vm_name": str(getattr(vm, "name", "")),
                    "vm_ips": _vm_ips(vm),
                    "host_name": str(getattr(host, "name", "")),
                    "management_ip": _management_ip(host),
                    "vsan_enabled": _vsan_enabled(host),
                }
            )
        return facts
    finally:
        view.Destroy()


class ReadOnlyVCenterClient:
    def __init__(
        self,
        address,
        username,
        password,
        port=443,
        verify_ssl=True,
        timeout=10,
        connector=None,
        query_executor=None,
        disconnector=None,
    ):
        self._disconnector = disconnector or _default_disconnect
        self._query_executor = query_executor or _default_query
        self._session = (connector or _default_connect)(
            address=address,
            port=int(port),
            username=username,
            password=password,
            verify_ssl=bool(verify_ssl),
            timeout=int(timeout),
        )

    def query_vm_host_facts(self):
        return list(self._query_executor(self._session))

    def close(self):
        if self._session is not None:
            session, self._session = self._session, None
            self._disconnector(session)
