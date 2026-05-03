from app import create_app

app = create_app()
with app.app_context():
    from app.models.db_asset import DatabaseCluster
    from app.services.topology_history import list_topology_history
    clusters = DatabaseCluster.query.filter(DatabaseCluster.db_type.in_(["mongodb", "redis"])).all()
    print("cluster count:", len(clusters))
    for c in clusters:
        print("=>", c.id, c.name, c.db_type)
        try:
            data = list_topology_history(c.id, 1, 10)
            print("   items:", len(data.get("items", [])), "total:", data.get("total"))
        except Exception as e:
            import traceback
            traceback.print_exc()
            print("   FAIL:", repr(e))
