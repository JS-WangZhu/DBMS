import json
import requests
from typing import List, Optional
from app.models.db_asset import DatabaseInstance
from app.utils.crypto import decrypt_secret

def get_mysql_metadata(instance: DatabaseInstance, database: str):
    import pymysql
    password = decrypt_secret(instance.password_encrypted) if instance.password_encrypted else None
    cluster = instance.cluster
    ha_domain = (cluster.ha_domain or "").strip() if cluster else ""
    host = ha_domain or instance.resolved_ip or instance.host_input
    
    connection = pymysql.connect(
        host=host,
        port=instance.port,
        user=instance.username,
        password=password,
        database=database,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=5
    )
    
    metadata = {"tables": [], "database": database}
    try:
        with connection.cursor() as cursor:
            # Get tables
            cursor.execute("SHOW TABLES")
            tables = [list(row.values())[0] for row in cursor.fetchall()]
            
            for table in tables:
                # Get table stats (rows, size)
                cursor.execute(f"""
                    SELECT TABLE_ROWS, DATA_LENGTH, INDEX_LENGTH 
                    FROM information_schema.TABLES 
                    WHERE TABLE_SCHEMA = '{database}' AND TABLE_NAME = '{table}'
                """)
                stats = cursor.fetchone()
                
                # Get create table
                cursor.execute(f"SHOW CREATE TABLE `{table}`")
                create_sql = cursor.fetchone()["Create Table"]
                
                # Get indexes
                cursor.execute(f"SHOW INDEX FROM `{table}`")
                indexes = cursor.fetchall()
                
                metadata["tables"].append({
                    "table_name": table,
                    "rows": stats.get("TABLE_ROWS") if stats else 0,
                    "data_size_mb": round(stats.get("DATA_LENGTH", 0) / 1024 / 1024, 2) if stats else 0,
                    "index_size_mb": round(stats.get("INDEX_LENGTH", 0) / 1024 / 1024, 2) if stats else 0,
                    "create_sql": create_sql,
                    "indexes": indexes
                })
    finally:
        connection.close()
    return metadata

def get_mongodb_metadata(instance: DatabaseInstance, database: str):
    from pymongo import MongoClient
    password = decrypt_secret(instance.password_encrypted) if instance.password_encrypted else None
    host = instance.resolved_ip or instance.host_input
    
    # Use single node for metadata fetching
    uri = f"mongodb://{instance.username}:{password}@{host}:{instance.port}/{database}?authSource=admin"
    if not instance.username:
        uri = f"mongodb://{host}:{instance.port}/{database}"
        
    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    metadata = {"collections": [], "database": database}
    try:
        db = client[database]
        collections = db.list_collection_names()
        for col_name in collections:
            col = db[col_name]
            # Get statistics
            try:
                stats = db.command("collstats", col_name)
            except:
                stats = {}
            
            # Get one document as sample for schema
            sample = col.find_one()
            # Get indexes
            indexes = list(col.list_indexes())
            
            metadata["collections"].append({
                "collection_name": col_name,
                "count": stats.get("count", 0),
                "size_mb": round(stats.get("size", 0) / 1024 / 1024, 2),
                "storage_size_mb": round(stats.get("storageSize", 0) / 1024 / 1024, 2),
                "sample_document": str(sample) if sample else "Empty collection",
                "indexes": indexes
            })
    finally:
        client.close()
    return metadata

def analyze_sql_with_ai(config, db_type: str, metadata: dict, sql_list: List[str]):
    api_url = (config.api_url or "").strip()
    api_key = config.api_key
    model_name = config.model_name
    
    # 自动补齐 OpenAI 兼容路径
    if api_url.endswith("/v1") or api_url.endswith("/v1/"):
        api_url = api_url.rstrip("/") + "/chat/completions"
    
    # 安全性检查：如果记录的是 https 但被意外变成了 http，这里可以做个记录或尝试修正
    # 但由于 requests 会跟随重定向，如果服务器强制跳转到 http，显示的就是 http
    
    metadata_str = json.dumps(metadata, indent=2, ensure_ascii=False)
    sqls_str = "\n".join(sql_list)
    
    prompt = f"""
你是一位资深的数据库专家。请分析以下 {db_type} 数据库的元数据和待执行的 SQL/命令。
分析其风险、可行性，并给出优化建议。请务必参考提供的表数据量（行数和大小）来评估查询风险（例如大表全表扫描）。

数据库元数据（表结构/索引/数据量/大小）:
{metadata_str}

待分析的 SQL/命令:
{sqls_str}

请按以下要求进行分析并回复：
1. **逐行评估**：请针对每一行（或每一条）SQL/命令，给出明确的执行结论（如：[可执行]、[有风险]、[语法错误]、[禁止执行]），并简述理由。
2. **风险分析**：是否存在全表扫描、锁表风险、性能问题等。
3. **优化建议**：针对 SQL 或索引的优化建议。
4. **最终结论**：请明确给出该变更单是否可以“放行”（[建议放行] 或 [不建议放行]），并总结核心原因。

请简要回复。
"""

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": "你是一个专业的数据库 DBA，精通 SQL 审计和风险评估。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7
    }
    
    try:
        # 显式打印请求信息以便调试
        print(f"[AI Request] URL: {api_url}")
        print(f"[AI Request] Payload: {json.dumps(payload, ensure_ascii=False)}")
        
        response = requests.post(api_url, headers=headers, json=payload, timeout=60)
        
        if response.status_code != 200:
            print(f"[AI Response Error] Status: {response.status_code}")
            print(f"[AI Response Content] {response.text}")
            # 尝试解析错误详情
            try:
                err_data = response.json()
                return f"AI 分析请求失败 (URL: {api_url}): {response.status_code} - {json.dumps(err_data, ensure_ascii=False)}"
            except:
                return f"AI 分析请求失败 (URL: {api_url}): {response.status_code} - {response.text}"
        
        result = response.json()
        print(f"[AI Response Success] {json.dumps(result, ensure_ascii=False)[:500]}...")
        
        choice = result.get("choices", [{}])[0]
        message = choice.get("message", {})
        return message.get("content", "")
    except Exception as e:
        # 返回更详细的错误信息，包含实际请求的 URL
        return f"AI 分析请求失败 (URL: {api_url}): {str(e)}"

def analyze_sql_with_ai_stream(config, db_type: str, metadata: dict, sql_list: List[str]):
    api_url = (config.api_url or "").strip()
    api_key = config.api_key
    model_name = config.model_name
    
    if api_url.endswith("/v1") or api_url.endswith("/v1/"):
        api_url = api_url.rstrip("/") + "/chat/completions"
    
    metadata_str = json.dumps(metadata, indent=2, ensure_ascii=False)
    sqls_str = "\n".join(sql_list)
    
    prompt = f"""
你是一位资深的数据库专家。请分析以下 {db_type} 数据库的元数据和待执行的 SQL/命令。
分析其风险、可行性，并给出优化建议。请务必参考提供的表数据量（行数和大小）来评估查询风险（例如大表全表扫描）。

数据库元数据（表结构/索引/数据量/大小）:
{metadata_str}

待分析的 SQL/命令:
{sqls_str}

请按以下要求进行分析并回复：
1. **逐行评估**：请针对每一行（或每一条）SQL/命令，给出明确的执行结论（如：[可执行]、[有风险]、[语法错误]、[禁止执行]），并简述理由。
2. **风险分析**：是否存在全表扫描、锁表风险、性能问题等。
3. **优化建议**：针对 SQL 或索引的优化建议。
4. **最终结论**：请明确给出该变更单是否可以“放行”（[建议放行] 或 [不建议放行]），并总结核心原因。

请简要回复。
"""

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": "你是一个专业的数据库 DBA，精通 SQL 审计和风险评估。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
        "stream": True
    }
    
    try:
        response = requests.post(api_url, headers=headers, json=payload, timeout=120, stream=True)
        if response.status_code != 200:
            yield json.dumps({"error": f"{response.status_code} - {response.text}"}, ensure_ascii=False)
            return

        content_buffer = ""

        for line in response.iter_lines():
            if line:
                decoded_line = line.decode('utf-8')
                if decoded_line.startswith('data: '):
                    data_str = decoded_line[6:]
                    if data_str == '[DONE]':
                        break
                    try:
                        data = json.loads(data_str)
                        choice = data.get("choices", [{}])[0]
                        delta = choice.get("delta", {})
                        
                        # Handle content only, ignore reasoning_details
                        if "content" in delta and delta["content"]:
                            text = delta["content"]
                            # 兼容性处理：MiniMax 的 content 有时可能是全量累积
                            if text.startswith(content_buffer):
                                new_content = text[len(content_buffer):]
                            else:
                                new_content = text
                                
                            if new_content:
                                yield json.dumps({"content": new_content}, ensure_ascii=False)
                                content_buffer = text if text.startswith(content_buffer) else (content_buffer + text)
                    except Exception:
                        continue
    except Exception as e:
        yield json.dumps({"error": str(e)}, ensure_ascii=False)
