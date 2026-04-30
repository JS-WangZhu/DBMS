import os
import subprocess
from urllib.parse import urlsplit

MULTIPART_CHUNK_SIZE = 8 * 1024 * 1024


def _normalize_endpoint_url(endpoint_url: str):
    value = (endpoint_url or "").strip()
    if not value:
        return None
    if value.startswith("//"):
        return f"https:{value}"
    parsed = urlsplit(value)
    if parsed.scheme:
        return value
    return f"https://{value}"


def _build_transfer_config():
    from boto3.s3.transfer import TransferConfig

    return TransferConfig(
        multipart_threshold=MULTIPART_CHUNK_SIZE,
        multipart_chunksize=MULTIPART_CHUNK_SIZE,
    )


def upload_file_to_s3(local_path: str, s3_config: dict):
    if not s3_config.get("enabled"):
        return {"ok": False, "message": "s3 upload disabled"}

    try:
        import boto3
    except Exception:
        return {"ok": False, "message": "boto3 is not installed"}

    bucket = s3_config.get("bucket")
    if not bucket:
        return {"ok": False, "message": "missing s3 bucket"}

    prefix = (s3_config.get("prefix") or "").strip("/")
    key_name = os.path.basename(local_path)
    object_key = f"{prefix}/{key_name}" if prefix else key_name

    client = boto3.client(
        "s3",
        region_name=s3_config.get("region") or None,
        endpoint_url=_normalize_endpoint_url(s3_config.get("endpoint_url")),
        aws_access_key_id=s3_config.get("access_key") or None,
        aws_secret_access_key=s3_config.get("secret_key") or None,
    )

    client.upload_file(local_path, bucket, object_key, Config=_build_transfer_config())
    return {"ok": True, "bucket": bucket, "key": object_key}


def upload_file_to_us3(local_path: str, s3_config: dict):
    if not s3_config.get("enabled"):
        return {"ok": False, "message": "s3 upload disabled"}
    bucket = s3_config.get("bucket")
    if not bucket:
        return {"ok": False, "message": "missing s3 bucket"}
    prefix = (s3_config.get("prefix") or "").strip("/")
    cli_path = (s3_config.get("us3_cli_path") or "").strip() or "/data/us3cli-linux64"
    if not os.path.exists(cli_path):
        return {"ok": False, "message": f"us3 cli not found: {cli_path}"}
    dest = f"us3://{bucket}/{prefix}" if prefix else f"us3://{bucket}/"
    if not dest.endswith("/"):
        dest = dest + "/"
    try:
        result = subprocess.run([cli_path, "cp", local_path, dest], capture_output=True, text=True, check=True)
        key_name = os.path.basename(local_path)
        object_key = f"{prefix}/{key_name}" if prefix else key_name
        return {"ok": True, "bucket": bucket, "key": object_key, "stdout": result.stdout.strip()}
    except subprocess.CalledProcessError as exc:
        return {"ok": False, "message": exc.stderr or str(exc), "exit_code": exc.returncode}


def generate_presigned_download_url(bucket: str, key: str, s3_config: dict, expires_in: int = 900):
    if not s3_config.get("enabled"):
        return None

    try:
        import boto3
    except Exception:
        return None

    client = boto3.client(
        "s3",
        region_name=s3_config.get("region") or None,
        endpoint_url=_normalize_endpoint_url(s3_config.get("endpoint_url")),
        aws_access_key_id=s3_config.get("access_key") or None,
        aws_secret_access_key=s3_config.get("secret_key") or None,
    )

    try:
        return client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expires_in,
        )
    except Exception:
        return None
