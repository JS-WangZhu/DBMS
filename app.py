"""DBMS Unified Management Platform — Streamlit Web UI.

Launch with:
    streamlit run app.py
"""

from __future__ import annotations

import json
from typing import Any

import pandas as pd
import streamlit as st

# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="DBMS Unified Management Platform",
    page_icon="🗄️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DB_TYPES = ["MySQL", "Redis", "Doris", "MongoDB"]

DB_DEFAULTS: dict[str, dict[str, Any]] = {
    "MySQL": {"host": "127.0.0.1", "port": 3306, "user": "root", "password": "", "database": ""},
    "Redis": {"host": "127.0.0.1", "port": 6379, "password": "", "db": 0},
    "Doris": {"host": "127.0.0.1", "port": 9030, "user": "root", "password": "", "database": ""},
    "MongoDB": {
        "host": "127.0.0.1",
        "port": 27017,
        "user": "",
        "password": "",
        "auth_source": "admin",
        "database": "",
    },
}

# ---------------------------------------------------------------------------
# Session-state helpers
# ---------------------------------------------------------------------------


def _state(key: str, default: Any = None) -> Any:
    if key not in st.session_state:
        st.session_state[key] = default
    return st.session_state[key]


def _get_connector(db_type: str):
    """Return (and cache) a connector instance for *db_type*."""
    key = f"connector_{db_type}"
    return st.session_state.get(key)


def _set_connector(db_type: str, connector) -> None:
    st.session_state[f"connector_{db_type}"] = connector


def _is_connected(db_type: str) -> bool:
    conn = _get_connector(db_type)
    return conn is not None and conn.is_connected


# ---------------------------------------------------------------------------
# Connector factory
# ---------------------------------------------------------------------------


def _build_connector(db_type: str, cfg: dict[str, Any]):
    """Instantiate the correct connector from *cfg*."""
    if db_type in ("MySQL", "Doris"):
        if db_type == "MySQL":
            from connectors.mysql_connector import MySQLConnector
            return MySQLConnector(**cfg)
        else:
            from connectors.doris_connector import DorisConnector
            return DorisConnector(**cfg)
    elif db_type == "Redis":
        from connectors.redis_connector import RedisConnector
        return RedisConnector(**cfg)
    elif db_type == "MongoDB":
        from connectors.mongodb_connector import MongoDBConnector
        return MongoDBConnector(**cfg)
    raise ValueError(f"Unknown database type: {db_type}")


# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------


def _render_result(result: Any, label: str = "Result") -> None:
    """Render *result* as a table (if list-of-dicts) or a plain value."""
    if isinstance(result, list):
        if not result:
            st.info("Query returned no rows.")
            return
        if isinstance(result[0], dict):
            st.dataframe(pd.DataFrame(result), use_container_width=True)
            return
        st.write(result)
    elif isinstance(result, dict):
        st.json(result)
    else:
        st.code(str(result))


def _connection_form(db_type: str) -> None:
    """Render a connection form for *db_type* in the sidebar."""
    defaults = DB_DEFAULTS[db_type]
    st.sidebar.subheader(f"🔌 {db_type} Connection")

    cfg: dict[str, Any] = {}

    cfg["host"] = st.sidebar.text_input("Host", value=defaults["host"], key=f"{db_type}_host")
    cfg["port"] = st.sidebar.number_input(
        "Port", value=defaults["port"], min_value=1, max_value=65535, key=f"{db_type}_port"
    )

    if db_type in ("MySQL", "Doris", "MongoDB"):
        cfg["user"] = st.sidebar.text_input("User", value=defaults.get("user", ""), key=f"{db_type}_user")
        cfg["password"] = st.sidebar.text_input(
            "Password", value=defaults.get("password", ""), type="password", key=f"{db_type}_password"
        )
    if db_type == "Redis":
        cfg["password"] = st.sidebar.text_input(
            "Password", value=defaults.get("password", ""), type="password", key=f"{db_type}_password"
        )
        cfg["db"] = st.sidebar.number_input(
            "DB index", value=defaults["db"], min_value=0, max_value=15, key=f"{db_type}_db"
        )

    if db_type in ("MySQL", "Doris", "MongoDB"):
        cfg["database"] = st.sidebar.text_input(
            "Database", value=defaults.get("database", ""), key=f"{db_type}_database"
        )
    if db_type == "MongoDB":
        cfg["auth_source"] = st.sidebar.text_input(
            "Auth source", value=defaults.get("auth_source", "admin"), key=f"{db_type}_auth_source"
        )

    col1, col2 = st.sidebar.columns(2)
    connect_clicked = col1.button("Connect", key=f"{db_type}_connect")
    disconnect_clicked = col2.button("Disconnect", key=f"{db_type}_disconnect")

    if connect_clicked:
        connector = _build_connector(db_type, cfg)
        with st.spinner(f"Connecting to {db_type}…"):
            ok = connector.connect()
        if ok:
            _set_connector(db_type, connector)
            st.sidebar.success("Connected ✅")
        else:
            st.sidebar.error("Connection failed ❌")

    if disconnect_clicked:
        conn = _get_connector(db_type)
        if conn:
            conn.disconnect()
            _set_connector(db_type, None)
        st.sidebar.info("Disconnected.")

    status = "🟢 Connected" if _is_connected(db_type) else "🔴 Disconnected"
    st.sidebar.caption(f"Status: {status}")


# ---------------------------------------------------------------------------
# Per-database main panels
# ---------------------------------------------------------------------------


def _mysql_panel(db_type: str) -> None:
    conn = _get_connector(db_type)
    if not _is_connected(db_type):
        st.warning(f"Please connect to {db_type} first using the sidebar.")
        return

    tab_query, tab_browse, tab_describe = st.tabs(["▶ Query", "📋 Browse Tables", "🔍 Describe Table"])

    with tab_query:
        st.subheader("SQL Query")
        default_sql = "SELECT 1" if db_type == "MySQL" else "SELECT current_timestamp()"
        sql = st.text_area("SQL", value=default_sql, height=140, key=f"{db_type}_sql")
        if st.button("Run", key=f"{db_type}_run_sql"):
            try:
                result = conn.execute(sql)
                _render_result(result)
            except Exception as exc:
                st.error(str(exc))

    with tab_browse:
        st.subheader("Browse Databases / Tables")
        try:
            databases = conn.list_databases()
        except Exception as exc:
            st.error(str(exc))
            return
        selected_db = st.selectbox("Database", options=databases, key=f"{db_type}_browse_db")
        if selected_db and st.button("Show Tables", key=f"{db_type}_show_tables"):
            try:
                tables = conn.list_tables(selected_db)
                if tables:
                    st.write(tables)
                else:
                    st.info("No tables found.")
            except Exception as exc:
                st.error(str(exc))

    with tab_describe:
        st.subheader("Describe Table")
        table_name = st.text_input("Table name", key=f"{db_type}_describe_table")
        if st.button("Describe", key=f"{db_type}_do_describe"):
            if not table_name:
                st.warning("Enter a table name.")
            else:
                try:
                    result = conn.describe_table(table_name)
                    _render_result(result)
                except Exception as exc:
                    st.error(str(exc))


def _redis_panel() -> None:
    conn = _get_connector("Redis")
    if not _is_connected("Redis"):
        st.warning("Please connect to Redis first using the sidebar.")
        return

    tab_cmd, tab_keys, tab_info = st.tabs(["▶ Command", "🗝 Browse Keys", "ℹ️ Server Info"])

    with tab_cmd:
        st.subheader("Execute Redis Command")
        cmd = st.text_input("Command (e.g. SET foo bar)", value="PING", key="redis_cmd")
        if st.button("Run", key="redis_run_cmd"):
            try:
                result = conn.execute(cmd)
                st.code(str(result))
            except Exception as exc:
                st.error(str(exc))

    with tab_keys:
        st.subheader("Key Browser")
        pattern = st.text_input("Pattern", value="*", key="redis_pattern")
        if st.button("List Keys", key="redis_list_keys"):
            try:
                keys = conn.list_keys(pattern)
                if not keys:
                    st.info("No matching keys.")
                else:
                    st.write(f"Found **{len(keys)}** keys.")
                    selected_key = st.selectbox("Inspect key", options=keys, key="redis_selected_key")
                    if selected_key:
                        key_type = conn.get_key_type(selected_key)
                        value = conn.get_key_value(selected_key)
                        st.caption(f"Type: **{key_type}**")
                        if isinstance(value, dict):
                            st.json(value)
                        else:
                            st.write(value)
            except Exception as exc:
                st.error(str(exc))

    with tab_info:
        st.subheader("Redis Server Info")
        section = st.selectbox(
            "Section",
            ["all", "server", "clients", "memory", "stats", "replication", "cpu"],
            key="redis_info_section",
        )
        if st.button("Get Info", key="redis_get_info"):
            try:
                info = conn.get_info(section)
                st.json(info)
            except Exception as exc:
                st.error(str(exc))


def _mongodb_panel() -> None:
    conn = _get_connector("MongoDB")
    if not _is_connected("MongoDB"):
        st.warning("Please connect to MongoDB first using the sidebar.")
        return

    tab_find, tab_insert, tab_cmd, tab_browse = st.tabs(
        ["🔎 Find", "➕ Insert", "▶ Command", "📋 Browse"]
    )

    with tab_find:
        st.subheader("Find Documents")
        try:
            databases = conn.list_databases()
        except Exception as exc:
            st.error(str(exc))
            return
        db_name = st.selectbox("Database", options=databases, key="mongo_find_db")
        if db_name:
            try:
                collections = conn.list_collections(db_name)
            except Exception as exc:
                st.error(str(exc))
                collections = []
            col_name = st.selectbox("Collection", options=collections, key="mongo_find_col")
            query_str = st.text_area("Filter (JSON)", value="{}", height=80, key="mongo_filter")
            limit = st.number_input("Limit", value=20, min_value=1, max_value=1000, key="mongo_limit")
            if st.button("Find", key="mongo_find_btn"):
                try:
                    query = json.loads(query_str) if query_str.strip() else {}
                    docs = conn.find(col_name, query=query, database=db_name, limit=limit)
                    _render_result(docs)
                except json.JSONDecodeError:
                    st.error("Invalid JSON filter.")
                except Exception as exc:
                    st.error(str(exc))

    with tab_insert:
        st.subheader("Insert Document")
        try:
            databases = conn.list_databases()
        except Exception as exc:
            st.error(str(exc))
            return
        db_name_ins = st.selectbox("Database", options=databases, key="mongo_ins_db")
        col_name_ins = st.text_input("Collection", key="mongo_ins_col")
        doc_str = st.text_area("Document (JSON)", value='{"key": "value"}', height=100, key="mongo_ins_doc")
        if st.button("Insert", key="mongo_ins_btn"):
            try:
                doc = json.loads(doc_str)
                inserted_id = conn.insert_one(col_name_ins, doc, database=db_name_ins)
                st.success(f"Inserted document with _id: `{inserted_id}`")
            except json.JSONDecodeError:
                st.error("Invalid JSON document.")
            except Exception as exc:
                st.error(str(exc))

    with tab_cmd:
        st.subheader("Run DB Command")
        cmd_name = st.text_input("Command name (e.g. dbStats, ping)", value="ping", key="mongo_cmd")
        if st.button("Run Command", key="mongo_cmd_btn"):
            try:
                result = conn.execute(cmd_name)
                st.json(result)
            except Exception as exc:
                st.error(str(exc))

    with tab_browse:
        st.subheader("Browse Collections")
        try:
            databases = conn.list_databases()
        except Exception as exc:
            st.error(str(exc))
            return
        db_name_br = st.selectbox("Database", options=databases, key="mongo_browse_db")
        if st.button("Show Collections", key="mongo_show_cols"):
            try:
                cols = conn.list_collections(db_name_br)
                if cols:
                    for c in cols:
                        count = conn.count_documents(c, database=db_name_br)
                        st.write(f"- **{c}** ({count:,} documents)")
                else:
                    st.info("No collections found.")
            except Exception as exc:
                st.error(str(exc))


# ---------------------------------------------------------------------------
# Main layout
# ---------------------------------------------------------------------------


def main() -> None:
    st.title("🗄️ DBMS Unified Management Platform")
    st.caption("Manage MySQL · Redis · Doris · MongoDB from one interface.")

    # Sidebar: database selector
    st.sidebar.title("Database")
    db_type = st.sidebar.radio("Select database", DB_TYPES, key="selected_db")

    st.sidebar.divider()
    _connection_form(db_type)

    st.divider()

    # Main panel
    if db_type in ("MySQL", "Doris"):
        _mysql_panel(db_type)
    elif db_type == "Redis":
        _redis_panel()
    elif db_type == "MongoDB":
        _mongodb_panel()


if __name__ == "__main__":
    main()
