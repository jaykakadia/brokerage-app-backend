"""
Copies uploaded media from one storage backend to another, for switching where photos live
(e.g. Render + R2 -> VPS local disk, or local -> R2). The database stores only storage keys,
so no data change is needed — after copying, point STORAGE_BACKEND / MEDIA_BASE_URL at the
new backend and redeploy.

Both backends are configured from the usual settings (.env / environment): "local" uses
UPLOAD_DIR, "s3" uses the S3_* settings.

    python -m scripts.copy_media --from s3 --to local
    python -m scripts.copy_media --from local --to s3 --dry-run
"""
import argparse
import mimetypes
import sys

from app.services.storage_service import create_backend


def main() -> int:
    parser = argparse.ArgumentParser(description="Copy uploaded media between storage backends.")
    parser.add_argument("--from", dest="source", required=True, choices=["local", "s3"])
    parser.add_argument("--to", dest="target", required=True, choices=["local", "s3"])
    parser.add_argument("--prefix", default="listings/", help="Only copy keys under this prefix.")
    parser.add_argument("--dry-run", action="store_true", help="List what would be copied.")
    args = parser.parse_args()

    if args.source == args.target:
        parser.error("--from and --to must differ")

    source = create_backend(args.source)
    target = create_backend(args.target)
    existing = set(target.list_keys(args.prefix))

    copied = skipped = failed = 0
    for key in source.list_keys(args.prefix):
        if key in existing:
            skipped += 1
            continue
        if args.dry_run:
            print(f"would copy {key}")
            copied += 1
            continue
        try:
            content_type = mimetypes.guess_type(key)[0] or "application/octet-stream"
            target.save(key, source.read(key), content_type)
            print(f"copied {key}")
            copied += 1
        except Exception as exc:
            print(f"FAILED {key}: {exc}", file=sys.stderr)
            failed += 1

    print(f"\n{'Would copy' if args.dry_run else 'Copied'} {copied}, already there {skipped}, failed {failed}.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
