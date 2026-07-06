from app.extensions import db
from app.models.db_asset import DatabaseInstance
from app.models.physical_discovery import PhysicalDiscoveryDetail, PhysicalDiscoveryRun, VCenterConfig
from app.utils.crypto import encrypt_secret


def test_run_batches_once_updates_auto_and_preserves_manual_or_failed(app):
    from app.services.physical_discovery import run_discovery

    calls = []

    class FakeClient:
        def __init__(self, **kwargs):
            calls.append(("connect", kwargs["address"]))

        def query_vm_host_facts(self):
            calls.append(("query", None))
            return [
                {"vm_ips": ["10.20.1.8"], "vsan_enabled": False, "management_ip": "192.0.2.10"},
            ]

        def close(self):
            calls.append(("disconnect", None))

    with app.app_context():
        vc = VCenterConfig(
            name="vc-a",
            address="vc-a.example.com",
            port=443,
            cidrs_json=["10.20.0.0/16"],
            username="readonly",
            password_encrypted=encrypt_secret("secret"),
            enabled=True,
        )
        auto_ok = DatabaseInstance(
            name="auto-ok", db_type="mysql", host_input="10.20.1.8", port=3306,
            extra_json={"physical_discovery_mode": "auto", "physical_address": "old"},
        )
        auto_missing = DatabaseInstance(
            name="auto-missing", db_type="redis", host_input="10.20.1.9", port=6379,
            extra_json={"physical_discovery_mode": "auto", "physical_address": "keep-me"},
        )
        manual = DatabaseInstance(
            name="manual", db_type="mongodb", host_input="10.20.1.8", port=27017,
            extra_json={"physical_discovery_mode": "manual", "physical_address": "manual-value"},
        )
        db.session.add_all([vc, auto_ok, auto_missing, manual])
        db.session.commit()

        run = run_discovery(vcenter_id=vc.id, trigger_type="manual", client_factory=FakeClient)

        db.session.refresh(auto_ok)
        db.session.refresh(auto_missing)
        db.session.refresh(manual)
        assert auto_ok.extra_json["physical_address"] == "192.0.2.10"
        assert auto_missing.extra_json["physical_address"] == "keep-me"
        assert manual.extra_json["physical_address"] == "manual-value"
        assert [name for name, _ in calls] == ["connect", "query", "disconnect"]
        assert run.status == "partial_success"
        assert PhysicalDiscoveryRun.query.count() == 1
        assert PhysicalDiscoveryDetail.query.filter_by(status="failed").count() == 1
