import pytest
from types import SimpleNamespace


def test_vsan_fact_returns_fixed_vsan_value():
    from app.services.vcenter_readonly import resolve_physical_address

    assert resolve_physical_address({"vsan_enabled": True, "management_ip": "192.0.2.1"}) == "vSAN"


def test_non_vsan_fact_returns_management_ip():
    from app.services.vcenter_readonly import resolve_physical_address

    assert resolve_physical_address({"vsan_enabled": False, "management_ip": "192.0.2.1"}) == "192.0.2.1"


def test_non_vsan_fact_without_management_ip_fails():
    from app.services.vcenter_readonly import resolve_physical_address

    with pytest.raises(ValueError, match="Management"):
        resolve_physical_address({"vsan_enabled": False, "management_ip": None})


def test_non_vsan_fact_falls_back_to_ip_host_name():
    from app.services.vcenter_readonly import resolve_physical_address

    assert resolve_physical_address({
        "vsan_enabled": False,
        "management_ip": None,
        "host_name": "192.0.2.20",
    }) == "192.0.2.20"


def test_management_ip_falls_back_to_vmk0_when_service_mapping_is_missing():
    from app.services.vcenter_readonly import _management_ip

    host = SimpleNamespace(
        name="esxi.example.com",
        config=SimpleNamespace(
            virtualNicManagerInfo=SimpleNamespace(netConfig=[]),
            network=SimpleNamespace(vnic=[
                SimpleNamespace(
                    key="key-vim.host.VirtualNic-vmk0",
                    device="vmk0",
                    spec=SimpleNamespace(ip=SimpleNamespace(ipAddress="192.0.2.30")),
                ),
                SimpleNamespace(
                    key="key-vim.host.VirtualNic-vmk1",
                    device="vmk1",
                    spec=SimpleNamespace(ip=SimpleNamespace(ipAddress="198.51.100.30")),
                ),
            ]),
        ),
    )

    assert _management_ip(host) == "192.0.2.30"


def test_readonly_client_call_trace_contains_no_mutation_and_closes():
    from app.services.vcenter_readonly import ReadOnlyVCenterClient

    calls = []

    def connect(**kwargs):
        calls.append("connect")
        return object()

    def query(session):
        calls.append("query")
        return [{"vm_ips": ["10.20.1.8"], "vsan_enabled": True}]

    def disconnect(session):
        calls.append("disconnect")

    client = ReadOnlyVCenterClient(
        address="vc.example.com",
        username="readonly",
        password="secret",
        connector=connect,
        query_executor=query,
        disconnector=disconnect,
    )
    try:
        assert client.query_vm_host_facts()[0]["vm_ips"] == ["10.20.1.8"]
    finally:
        client.close()

    assert calls == ["connect", "query", "disconnect"]
    assert not any(word in " ".join(calls) for word in ["reconfigure", "power", "migrate", "snapshot"])


def test_readonly_client_can_stream_facts_without_collecting_first():
    from app.services.vcenter_readonly import ReadOnlyVCenterClient

    consumed = []

    def query(_session):
        consumed.append("first")
        yield {"vm_ips": ["10.20.1.8"]}
        consumed.append("second")
        yield {"vm_ips": ["10.20.1.9"]}

    client = ReadOnlyVCenterClient(
        address="vc.example.com",
        username="readonly",
        password="secret",
        connector=lambda **_kwargs: object(),
        query_executor=query,
        disconnector=lambda _session: None,
    )
    iterator = client.iter_vm_host_facts()

    assert next(iterator)["vm_ips"] == ["10.20.1.8"]
    assert consumed == ["first"]
    assert next(iterator)["vm_ips"] == ["10.20.1.9"]
    assert consumed == ["first", "second"]
