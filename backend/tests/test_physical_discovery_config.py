import importlib
import importlib.util

import pytest


def _service():
    spec = importlib.util.find_spec("app.services.physical_discovery_config")
    assert spec is not None, "physical discovery config service must exist"
    return importlib.import_module("app.services.physical_discovery_config")


def test_normalize_cidrs_canonicalizes_and_deduplicates():
    service = _service()

    assert service.normalize_cidrs(["10.20.1.8/16", "10.20.0.0/16", "192.0.2.0/24"]) == [
        "10.20.0.0/16",
        "192.0.2.0/24",
    ]


def test_normalize_cidrs_rejects_invalid_or_empty_values():
    service = _service()

    with pytest.raises(ValueError, match="CIDR"):
        service.normalize_cidrs([])
    with pytest.raises(ValueError, match="CIDR"):
        service.normalize_cidrs(["not-a-network"])


def test_validate_non_overlapping_cidrs_rejects_overlap():
    service = _service()

    with pytest.raises(ValueError, match="overlap"):
        service.validate_non_overlapping_cidrs(
            ["10.20.0.0/16"],
            [(7, ["10.20.8.0/24"])],
        )


def test_validate_non_overlapping_cidrs_allows_excluded_config():
    service = _service()

    service.validate_non_overlapping_cidrs(
        ["10.20.0.0/16"],
        [(7, ["10.20.0.0/16"])],
        exclude_id=7,
    )
