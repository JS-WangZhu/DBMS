import pytest


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
