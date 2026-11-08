"""Artifact downloads: a short-lived signed link (MinIO) or a stream after the owner check.

On the server the files are in MinIO. The browser gets a presigned link made for the
public MinIO address (``S3_PUBLIC_ENDPOINT_URL``, valid 5 minutes). Without a public
address (dev, tests, or MinIO kept private) Django streams the file itself; both happen
only after the owner check in the view.
"""

from __future__ import annotations

from django.conf import settings
from django.http import FileResponse, HttpResponse, HttpResponseRedirect

from jobs.models import Artifact

CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".zip": "application/zip",
    ".json": "application/json",
    ".html": "text/html; charset=utf-8",
}


def presigned_url(artifact: Artifact, expires_s: int = 300) -> str | None:
    endpoint = str(getattr(settings, "S3_PUBLIC_ENDPOINT_URL", "") or "")
    storage = artifact.file.storage
    if not endpoint or not hasattr(storage, "bucket_name"):
        return None
    import boto3  # type: ignore[import-untyped, unused-ignore]
    from botocore.config import Config  # type: ignore[import-untyped, unused-ignore]

    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=storage.access_key,
        aws_secret_access_key=storage.secret_key,
        region_name=getattr(storage, "region_name", None) or "us-east-1",
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )
    url: str = client.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": storage.bucket_name,
            "Key": artifact.file.name,
            "ResponseContentDisposition": f'attachment; filename="{artifact.name}"',
        },
        ExpiresIn=expires_s,
    )
    return url


def download(artifact: Artifact) -> HttpResponse | FileResponse:
    url = presigned_url(artifact)
    if url is not None:
        return HttpResponseRedirect(url)
    suffix = "." + artifact.name.rsplit(".", 1)[-1].lower() if "." in artifact.name else ""
    response = FileResponse(
        artifact.file.open("rb"),
        as_attachment=True,
        filename=artifact.name,
        content_type=CONTENT_TYPES.get(suffix, "application/octet-stream"),
    )
    response["X-Content-Type-Options"] = "nosniff"
    return response
