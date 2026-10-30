"""Cliente R2 con boto3 (S3 API directa — PLAN.md §4.2).

Elección v0.1: notas write-once por PUT completo, listas e inmersiones triviales
de la S3 API. `CloudBucketMount` queda reservado para el embedder (v1).
"""

from __future__ import annotations

import logging
from functools import lru_cache

import boto3
from botocore.client import Config

from . import config

logger = logging.getLogger(__name__)

R2_SIGNATURE = Config(
    signature_version="s3v4",
    retries={"max_attempts": 3, "mode": "standard"},
    request_checksum_calculation="when_required",
    response_checksum_validation="when_required",
)


@lru_cache(maxsize=1)
def client():
    """Cliente S3 apuntando al endpoint de R2 (crea conexiones bajo demanda)."""
    if not (config.R2_ENDPOINT and config.R2_ACCESS_KEY and config.R2_SECRET_KEY):
        raise RuntimeError(
            "R2 no configurado: faltan R2_ENDPOINT / R2_ACCESS_KEY / R2_SECRET_KEY"
        )
    return boto3.client(
        "s3",
        endpoint_url=config.R2_ENDPOINT,
        aws_access_key_id=config.R2_ACCESS_KEY,
        aws_secret_access_key=config.R2_SECRET_KEY,
        config=R2_SIGNATURE,
    )


def put_bytes(key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    client().put_object(Bucket=config.R2_BUCKET, Key=key, Body=data, ContentType=content_type)
    logger.info("R2 put %s (%d bytes, %s)", key, len(data), content_type)
    return key


def get_bytes(key: str) -> bytes:
    response = client().get_object(Bucket=config.R2_BUCKET, Key=key)
    return response["Body"].read()


def delete(key: str) -> None:
    client().delete_object(Bucket=config.R2_BUCKET, Key=key)
    logger.info("R2 delete %s", key)


def exists(key: str) -> bool:
    try:
        client().head_object(Bucket=config.R2_BUCKET, Key=key)
        return True
    except client().exceptions.ClientError:
        return False


def list_prefix(prefix: str, limit: int = 100) -> list[str]:
    """Claves bajo un prefijo, ordenadas por nombre (los timestamps ISO ordenan crono)."""
    keys: list[str] = []
    paginator = client().get_paginator("list_objects_v2")
    for page in paginator.paginate(
            Bucket=config.R2_BUCKET, Prefix=prefix, PaginationConfig={"PageSize": limit}):
        for item in page.get("Contents", []):
            keys.append(item["Key"])
            if len(keys) >= limit:
                return keys
    return keys


def count_prefix(prefix: str) -> int:
    total = 0
    paginator = client().get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=config.R2_BUCKET, Prefix=prefix):
        total += page.get("KeyCount", 0)
    # contamos la propia "carpeta" si existe como objeto vacío
    return total
