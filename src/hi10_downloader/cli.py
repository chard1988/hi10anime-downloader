from .retries import retry_delay
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import shutil
from urllib.parse import urlsplit

import httpx

from .parsing import parse_project, project_links, safe_name
from .network import client as safe_client, bounded_page
from .lifecycle import ServiceLocks
from . import __version__, schema

BASE = "https://hi10anime.com"
LIST_URL = BASE + "/projects/all-projects"


from .storage import save_json, load_json


def make_client(state_path: Path) -> httpx.Client:
    state = load_json(state_path, schema.session)
    cookies = httpx.Cookies()
    now = time.time()
    for cookie in state.get("cookies", []):
        # Auth cookies are only attached to the site's domains, never its mirrors.
        domain = cookie["domain"]
        if domain.lstrip(".") != "hi10anime.com":
            continue
        if cookie.get("expires", -1) not in {-1, 0} and cookie["expires"] < now:
            continue
        from http.cookiejar import Cookie
        cookies.jar.set_cookie(Cookie(0, cookie["name"], cookie["value"], None, False,
            domain, domain.startswith("."), domain.startswith("."), cookie.get("path", "/"),
            True, cookie.get("secure", True), None, True, None, None, {}))
    return safe_client(cookies=cookies, headers={"User-Agent": "Hi10Downloader/0.3.0-beta.1"})


def fetch_page(client: httpx.Client, url: str) -> str:
    return bounded_page(client, url)


def login(args) -> None:
    from playwright.sync_api import sync_playwright
    with ServiceLocks(args.state.parent, args.state.parent), sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False, chromium_sandbox=True)
        context = browser.new_context()
        page = context.new_page()
        page.goto(BASE + "/wp-login.php")
        input("Complete login in the browser, then press Enter here to verify and save the session: ")
        page.goto(LIST_URL)
        page.locator("#urlContainer").wait_for(timeout=30000)
        state = context.storage_state()
        save_json(args.state, {'cookies': [c for c in state['cookies'] if c['domain'].lstrip('.') == 'hi10anime.com'], 'origins': []})
        browser.close()
    print(f"Saved session to {args.state}. Treat this file like a password.")


def scan(args) -> None:
    with ServiceLocks(args.state.parent, args.plan.parent):
        _scan(args)


def _scan(args) -> None:
    projects, errors = [], []
    with make_client(args.state) as client:
        from .sources import load_project_list
        urls = args.project or project_links(load_project_list(client), LIST_URL)
        if args.limit:
            urls = urls[:args.limit]
        for number, url in enumerate(dict.fromkeys(urls), 1):
            if urlsplit(url).hostname != "hi10anime.com" or urlsplit(url).scheme != "https":
                raise ValueError(f"Expected an HTTPS hi10anime.com project URL: {url}")
            print(f"[{number}/{len(urls)}] {url}", flush=True)
            try:
                project = parse_project(fetch_page(client, url), url)
                projects.append(project)
                if not project["files"]:
                    errors.append({"url": url, "error": "No direct .mkv links found; host landing pages and JavaScript links need a resolver."})
            except (httpx.HTTPError, ValueError) as exc:
                errors.append({"url": url, "error": str(exc)})
            time.sleep(args.delay)
    save_json(args.plan, {"version": 1, "projects": projects, "errors": errors})
    count = sum(len(project["files"]) for project in projects)
    print(f"Saved {len(projects)} projects and {count} selected files to {args.plan}; {len(errors)} issues.")
    if errors:
        raise ValueError("Scan finished with issues; review the plan's errors before downloading.")


def digest(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def child_path(parent: Path, name: str) -> Path:
    if not name or name in {".", ".."} or safe_name(name) != name:
        raise ValueError(f"Unsafe path component in plan: {name!r}")
    path = parent / name
    if path.is_symlink() or not path.resolve().is_relative_to(parent.resolve()):
        raise ValueError(f"Path escapes download directory: {path}")
    return path


def file_folder(output: Path, project_folder: str, item: dict) -> Path:
    folder = child_path(output, project_folder)
    if item.get('subfolder'):
        folder = child_path(folder, item['subfolder'])
    return folder


def download_one(client: httpx.Client, item: dict, project_url: str, target: Path, progress=None) -> dict:
    if urlsplit(item["url"]).scheme not in {"http", "https"}:
        raise ValueError("Download URL must use HTTP or HTTPS")
    deadline = time.monotonic() + int(os.environ.get("HI10_DOWNLOAD_DEADLINE", "21600"))
    max_size = int(os.environ.get("HI10_MAX_FILE_BYTES", str(100 * 1024**3)))
    reserve = int(os.environ.get("HI10_MIN_FREE_BYTES", str(256 * 1024**2)))
    part = target.with_name(target.name + ".part")
    if part.is_symlink():
        raise ValueError(f"Refusing symlink: {part}")
    try:
        with client.stream("GET", item["url"], headers={"Referer": project_url, "Accept-Encoding": "identity"}) as response:
            response.raise_for_status()
            if response.status_code != 200:
                raise ValueError(f"Expected a complete file (HTTP 200), got {response.status_code}")
            content_type = response.headers.get("content-type", "").lower()
            if any(kind in content_type for kind in ("text/", "json", "xml")):
                raise ValueError("Download returned a document rather than a video; the mirror may require login or a resolver.")
            expected = response.headers.get("content-length")
            total = int(expected) if expected is not None else None
            if total is not None and total < 0:
                raise ValueError("Invalid negative download length.")
            if total is not None and total > max_size:
                raise ValueError("Download exceeds maximum file size.")
            if shutil.disk_usage(target.parent).free < reserve + (total or 0):
                raise ValueError("Insufficient free disk space for this download.")
            if progress:
                progress(0, total)
            size = 0
            checksum = hashlib.sha256()
            prefix = bytearray()
            with part.open("wb") as stream:
                for chunk in response.iter_bytes(1024 * 1024):
                    if len(prefix) < 4:
                        prefix.extend(chunk[:4 - len(prefix)])
                        if len(prefix) == 4 and prefix != b"\x1a\x45\xdf\xa3":
                            raise ValueError("Response is not a Matroska/EBML file.")
                    if size + len(chunk) > max_size or time.monotonic() > deadline:
                        raise ValueError("Download size or total time limit exceeded.")
                    stream.write(chunk)
                    checksum.update(chunk)
                    size += len(chunk)
                    if size % (16 * 1024**2) < len(chunk) and shutil.disk_usage(target.parent).free < reserve:
                        raise ValueError("Download stopped: free disk reserve reached.")
                    if progress:
                        progress(size, total)
                stream.flush()
                os.fsync(stream.fileno())
            expected = response.headers.get("content-length")
            if size < 4 or (expected is not None and size != int(expected)):
                raise ValueError(f"Download incomplete: received {size} bytes; expected {expected if expected is not None else 'at least 4'} bytes.")
        record = {"url": item["url"], "size": size, "sha256": checksum.hexdigest()}
        save_json(target.with_name(target.name + ".receipt.json"), record)
        part.replace(target)
        directory = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        return record
    finally:
        part.unlink(missing_ok=True)


def clear_receipt(target):
    for suffix in ('.receipt.json', '.receipt.json.bak', '.receipt.json.corrupt'):
        target.with_name(target.name + suffix).unlink(missing_ok=True)


def download(args) -> None:
    with ServiceLocks(args.state.parent, args.output):
        _download(args)


def _download(args) -> None:
    plan = json.loads(args.plan.read_text())
    if plan.get("version") != 1:
        raise ValueError("Unsupported plan version")
    args.output.mkdir(parents=True, exist_ok=True)
    manifest_path = child_path(args.output, "hi10-manifest.json")
    manifest = load_json(manifest_path) if manifest_path.exists() else {}
    failures = []
    with make_client(args.state) as client:
        for project in plan["projects"]:
            for item in project["files"]:
                folder = file_folder(args.output, project["folder"], item)
                folder.mkdir(parents=True, exist_ok=True)
                target = child_path(folder, item["filename"])
                key = str(target.relative_to(args.output))
                record = manifest.get(key)
                receipt = target.with_name(target.name + ".receipt.json")
                if not record and receipt.exists():
                    record = load_json(receipt)
                if target.exists():
                    if record and record["url"] == item["url"] and target.stat().st_size == record["size"] and digest(target) == record["sha256"]:
                        manifest[key] = record
                        save_json(manifest_path, manifest)
                        clear_receipt(target)
                        print(f"Already complete: {key}")
                        continue
                    failures.append(f"{key}: existing file is untracked or changed; move it before retrying")
                    continue
                print(f"Downloading: {key}", flush=True)
                for attempt in range(args.retries + 1):
                    try:
                        record = download_one(client, item, project["url"], target)
                        manifest[key] = record
                        save_json(manifest_path, manifest)
                        clear_receipt(target)
                        break
                    except (httpx.HTTPError, ValueError, OSError) as exc:
                        delay = retry_delay(exc, attempt)
                        if attempt == args.retries or delay is None:
                            failures.append(f"{key}: {type(exc).__name__}")
                            break
                        time.sleep(delay)
                time.sleep(args.delay)
    if failures:
        raise ValueError("Some downloads failed:\n" + "\n".join(failures))
    print("Downloads complete.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Log in, scan projects, and download the highest available MKV variants.")
    parser.add_argument('--version', action='version', version=__version__)
    parser.add_argument("--state", type=Path, default=Path(".hi10/session.json"), help="Saved browser session (sensitive)")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("login", help="Log in manually using a visible browser").set_defaults(func=login)
    scan_parser = commands.add_parser("scan", help="Create a reviewable JSON download plan")
    scan_parser.add_argument("--project", action="append", help="Scan only this project URL; repeatable")
    scan_parser.add_argument("--limit", type=int, help="Limit the number of projects scanned")
    scan_parser.add_argument("--plan", type=Path, default=Path("plan.json"))
    scan_parser.set_defaults(func=scan)
    download_parser = commands.add_parser("download", help="Download files from a reviewed plan")
    download_parser.add_argument("--plan", type=Path, default=Path("plan.json"))
    download_parser.add_argument("--output", type=Path, default=Path("downloads"))
    download_parser.add_argument("--retries", type=int, default=3)
    download_parser.set_defaults(func=download)
    for sub in (scan_parser, download_parser):
        sub.add_argument("--delay", type=float, default=1.0, help="Seconds between projects/files")
    args = parser.parse_args()
    if getattr(args, "delay", 0) < 0 or getattr(args, "retries", 0) < 0 or (getattr(args, "limit", None) is not None and args.limit < 1):
        parser.error("Delay/retries must be nonnegative and limit must be positive")
    try:
        args.func(args)
    except (OSError, ValueError, httpx.HTTPError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted. Completed files remain recorded; rerun to continue.", file=sys.stderr)
        return 130
    return 0
