import hashlib
import re
import unicodedata
from urllib.parse import parse_qs, unquote, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup

RESOLUTION = re.compile(r"(?<!\d)(\d{3,4})\s*p(?![a-z0-9])", re.I)
SEASON = re.compile(r"(?<![a-z0-9])(?:season[\s_.-]*|s)(\d{1,3})(?=$|[^a-z0-9]|e\d)", re.I)
DIMENSIONS = re.compile(r"(?<!\d)\d{3,4}\s*[x×]\s*(\d{3,4})(?!\d)", re.I)


def safe_name(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    value = re.sub(r'[\x00-\x1f<>:"/\\|?*]', "_", value).strip(" .")[:160]
    if not value:
        return "untitled"
    if value.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
        value = "_" + value
    return value


def canonical(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))


def project_links(html: str, base: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    container = soup.select_one("#urlContainer")
    if container is None:
        raise ValueError("Project list has no #urlContainer. Log in again or check the page markup.")
    return list(dict.fromkeys(canonical(urljoin(base, a["href"])) for a in container.select("a[href]") if urlsplit(urljoin(base, a["href"])).scheme in {"http", "https"}))


def resolution(text: str) -> int:
    match = RESOLUTION.search(text) or DIMENSIONS.search(text)
    return int(match.group(1)) if match else 0


def file_key(filename: str) -> str:
    # Preserve episode, season, codec, release group and edition; ignore quality and CRC.
    value = RESOLUTION.sub("", filename.lower())
    value = DIMENSIONS.sub("", value)
    # CRC32 values identify a particular encode, not a different episode/edition.
    value = re.sub(r"[\[(][0-9a-f]{8}[\])]", "", value, flags=re.I)
    return re.sub(r"[\W_]+", "", value)


def download_target(url: str) -> str:
    """Read an explicit file destination from the site's known outbound-link wrapper."""
    parts = urlsplit(url)
    if parts.hostname in {"ouo.io", "ouo.press"} and parts.path.startswith("/s/"):
        values = parse_qs(parts.query).get("s", [])
        if len(values) == 1:
            target = urlsplit(values[0])
            if target.scheme in {"http", "https"} and target.hostname and target.path.lower().endswith(".mkv"):
                return canonical(values[0])
    return url


def section_name(anchor, root) -> tuple[str, str]:
    """Use an owning download-table caption, or a meaningful preceding heading."""
    table = anchor.find_parent('table')
    caption = table.find('caption') if table else None
    table_title = caption or (table.select_one('thead th[colspan]') if table else None)
    if table_title:
        text = table_title.get_text(' ', strip=True)
        name = re.sub(r'^(?:links|downloads|episodes)\s+for\s*:\s*', '', text, flags=re.I)
        name = re.sub(r'\s*\[[^\]]*\]\s*$', '', name).strip()
        generic = re.sub(r'\b(?:BD|DVD|Blu-ray|quality|downloads?|links?|episodes?|HEVC|x264|x265)\b', '', RESOLUTION.sub('', name), flags=re.I)
        if re.search(r'[^\W_]', generic):
            return name, text
    for heading in anchor.find_all_previous(['h2', 'h3', 'h4', 'h5', 'h6']):
        if root is not heading and root not in heading.parents:
            continue
        text = heading.get_text(' ', strip=True)
        remainder = RESOLUTION.sub('', DIMENSIONS.sub('', text))
        remainder = re.sub(r'\b(?:BD|DVD|Blu-ray|quality|downloads?|links?|episodes?|HEVC|x264|x265)\b', '', remainder, flags=re.I)
        if re.search(r'[^\W_]', remainder):
            return re.sub(r'\s*\[[^\]]*\]\s*$', '', text).strip(), text
    return '', ''


def parse_project(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    root = soup.select_one(".entry-content") or soup.select_one("article") or soup
    heading = soup.select_one("h1.entry-title") or soup.select_one("h1") or soup.title
    title = heading.get_text(" ", strip=True) if heading else urlsplit(url).path.strip("/")
    folder = safe_name(title)[:140] + "--" + hashlib.sha256(url.encode()).hexdigest()[:8]
    files, section_labels = [], {}
    section_seasons, section_bases = {}, {}
    seen = set()
    for anchor in root.select("a[href]"):
        target = download_target(canonical(urljoin(url, anchor["href"])))
        parts = urlsplit(target)
        filename = unquote(parts.path.rsplit("/", 1)[-1])
        if parts.scheme not in {"http", "https"} or not filename.lower().endswith(".mkv"):
            continue
        label, section_text = section_name(anchor, root)
        season_match = SEASON.search(filename) or SEASON.search(label) or SEASON.search(section_text)
        season = int(season_match.group(1)) if season_match else None
        base_label = re.sub(r'\s+', ' ', SEASON.sub('', label)).strip(' -_—:|')
        if season is not None:
            label = (base_label + ' — ' if base_label else '') + f'Season {season:02d}'
        section_key = re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', label).casefold()).strip()
        if (section_key, target) in seen:
            continue
        seen.add((section_key, target))
        section_labels.setdefault(section_key, label or 'Project files')
        section_seasons[section_key] = season
        section_bases[section_key] = base_label
        quality = resolution(filename) or resolution(anchor.get_text(" ", strip=True))
        if not quality:
            block = anchor.find_parent(["tr", "li", "p"])
            if block:
                qualities = set(RESOLUTION.findall(block.get_text(" ", strip=True)))
                if len(qualities) == 1:
                    quality = int(qualities.pop())
        if not quality:
            quality = resolution(section_text)
        if not quality:
            previous = anchor.find_previous(["h2", "h3", "h4", "h5", "h6"])
            quality = resolution(previous.get_text(" ", strip=True)) if previous else 0
        files.append({"url": target, "filename": safe_name(filename[:-4])[:150] + ".mkv",
                      "resolution": quality, "key": file_key(filename), '_section': section_key})
    sections = []
    if len(section_labels) > 1 or any(value is not None for value in section_seasons.values()):
        for key, label in section_labels.items():
            section_id = hashlib.sha256(key.encode()).hexdigest()[:12]
            season = section_seasons[key]
            subfolder = f'Season {season:02d}' if season is not None and len(set(section_bases.values())) == 1 else safe_name(label)[:140] + '--' + section_id[:8]
            sections.append({'id': section_id, 'title': label, 'folder': subfolder, 'season': season})
            for item in files:
                if item['_section'] == key:
                    item.update(section_id=section_id, section_title=label, subfolder=subfolder)
                    item['key'] = section_id + ':' + item['key']
    for item in files:
        item.pop('_section')
    selected = select_files(files)
    return {"url": url, "title": title, "folder": folder, "files": selected,
            "variants": files, "candidate_count": len(files), 'sections': sections}


def select_files(candidates: list[dict], preferred: int = 0, choices: dict | None = None,
                 section_qualities: dict | None = None) -> list[dict]:
    """Choose one variant per identity within each collection section."""
    groups = {}
    for item in candidates:
        groups.setdefault(item["key"], []).append(item)
    selected = []
    for key, variants in groups.items():
        section_quality = int((section_qualities or {}).get(variants[0].get('section_id'), 0)) or preferred
        quality = int((choices or {}).get(key, 0)) or section_quality
        matching = [item for item in variants if item["resolution"] == quality] if quality else []
        selected.append(dict(max(matching or variants, key=lambda item: item["resolution"])))
    names = set()
    for item in selected:
        name = item["filename"]
        folder_key = item.get('subfolder', '').casefold()
        if (folder_key, name.casefold()) in names:
            item["filename"] = name[:-4] + "--" + hashlib.sha256(item["url"].encode()).hexdigest()[:8] + ".mkv"
        names.add((folder_key, item['filename'].casefold()))
    return selected
