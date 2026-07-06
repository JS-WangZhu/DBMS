import importlib
import importlib.util

from app.extensions import db
from app.models.db_asset import DatabaseInstance
from app.services.instance_service import _normalize_extra_json


def _instance(extra_json=None):
    return DatabaseInstance(
        name="mysql-1",
        db_type="mysql",
        host_input="10.20.1.8",
        port=3306,
        extra_json=extra_json,
    )


def test_instance_missing_discovery_mode_defaults_to_auto(app):
    with app.app_context():
        row = _instance()
        db.session.add(row)
        db.session.commit()

        assert row.to_dict()["extra_json"]["physical_discovery_mode"] == "auto"


def test_instance_extra_normalization_preserves_address_and_manual_mode():
    normalized = _normalize_extra_json(
        {"physical_address": "192.0.2.10", "physical_discovery_mode": "manual"}
    )

    assert normalized["physical_address"] == "192.0.2.10"
    assert normalized["physical_discovery_mode"] == "manual"


def test_invalid_discovery_mode_normalizes_to_auto():
    normalized = _normalize_extra_json({"physical_discovery_mode": "unexpected"})

    assert normalized["physical_discovery_mode"] == "auto"


def test_physical_discovery_models_exist_and_mask_password(app):
    spec = importlib.util.find_spec("app.models.physical_discovery")
    assert spec is not None, "physical discovery models must be implemented"
    module = importlib.import_module("app.models.physical_discovery")

    with app.app_context():
        config = module.PhysicalDiscoveryConfig()
        vcenter = module.VCenterConfig(
            name="vc-a",
            address="vc-a.example.com",
            username="readonly",
            password_encrypted="ciphertext",
            cidrs_json=["10.20.0.0/16"],
        )
        db.session.add_all([config, vcenter])
        db.session.commit()

        assert config.to_dict()["enabled"] is False
        payload = vcenter.to_dict()
        assert payload["password_configured"] is True
        assert "password" not in payload
        assert "password_encrypted" not in payload
