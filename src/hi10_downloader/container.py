"""One batch per container start, configured through unRAID environment fields."""
import argparse
import os
from pathlib import Path
import sys

import httpx

from .cli import BASE, LIST_URL, fetch_page, make_client, save_json, _scan as scan, _download as download
from .lifecycle import ServiceLocks


def login_from_environment(state: Path) -> None:
    username = os.environ.get("HI10_USERNAME", "")
    password = os.environ.get("HI10_PASSWORD", "")
    if not username or not password:
        raise ValueError("Set HI10_USERNAME and HI10_PASSWORD, or import a valid session.json into /config.")
    raise ValueError('Automatic batch login is disabled. Import a desktop session.json or use the interactive web login.')


def ensure_session(state: Path) -> None:
    if state.exists():
        try:
            with make_client(state) as client:
                from .parsing import project_links
                project_links(fetch_page(client, LIST_URL), LIST_URL)
            return
        except (ValueError, OSError):
            pass
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in {401, 403}:
                raise
    login_from_environment(state)


def main() -> int:
    try:
        config = Path(os.environ.get("HI10_CONFIG_DIR", "/config"))
        output = Path(os.environ.get("HI10_DOWNLOAD_DIR", "/downloads"))
        config.mkdir(parents=True, exist_ok=True)
        state = config / "session.json"
        limit_text = os.environ.get("HI10_PROJECT_LIMIT", "").strip()
        limit = int(limit_text) if limit_text else None
        if limit is not None and limit < 1:
            raise ValueError("HI10_PROJECT_LIMIT must be positive or empty for all projects")
        args = argparse.Namespace(state=state, plan=config / "plan.json", project=None,
                                  limit=limit, delay=1.0, output=output, retries=3)
        with ServiceLocks(config, output):
            ensure_session(state)
            scan(args)
            download(args)
        return 0
    except KeyboardInterrupt:
        return 130
    except Exception:
        # Do not print exception details: requests can include signed private URLs.
        print("Batch stopped. Check access/credentials, writable /config and /downloads mappings, and /config/plan.json if present. For a login challenge, import a desktop session.json and restart. No further files will be downloaded in this run.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
