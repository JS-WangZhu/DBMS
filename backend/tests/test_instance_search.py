from app.extensions import db
from app.models.db_asset import DatabaseCluster, DatabaseInstance
from app.services.instance_service import list_instances_paginated


def _matching_ids(keyword):
    rows, total, _page, _page_size = list_instances_paginated(
        db_type="mysql",
        keyword=keyword,
        page=1,
        page_size=20,
    )
    return [row.id for row in rows], total


def test_instance_keyword_fuzzy_matches_name_cluster_ip_and_domain(app):
    cluster = DatabaseCluster(name="订单核心集群", db_type="mysql")
    other_cluster = DatabaseCluster(name="报表集群", db_type="mysql")
    db.session.add_all([cluster, other_cluster])
    db.session.flush()

    target = DatabaseInstance(
        name="orders-primary-01",
        db_type="mysql",
        host_input="10.20.30.40",
        resolved_ip="172.16.8.25",
        port=3306,
        cluster_id=cluster.id,
        extra_json={"domain": "orders-db.prod.example.com"},
    )
    other = DatabaseInstance(
        name="report-secondary-01",
        db_type="mysql",
        host_input="10.99.1.10",
        resolved_ip="172.31.1.10",
        port=3306,
        cluster_id=other_cluster.id,
        extra_json={"domain": "report-db.internal.example.com"},
    )
    standalone = DatabaseInstance(
        name="standalone-node",
        db_type="mysql",
        host_input="standalone.example.net",
        resolved_ip="192.0.2.15",
        port=3306,
    )
    db.session.add_all([target, other, standalone])
    db.session.commit()

    for keyword in ("PRIMARY-01", "核心集", "16.8", "DB.PROD.EXAMPLE"):
        ids, total = _matching_ids(keyword)
        assert ids == [target.id]
        assert total == 1

    ids, total = _matching_ids("standalone.example")
    assert ids == [standalone.id]
    assert total == 1
