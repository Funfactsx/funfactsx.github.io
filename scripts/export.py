#!/usr/bin/env python3
"""Export only the publicly rendered Fun Facts website to GitHub Pages.
Does not use the private ASP.NET app, SQL Server, CMS, or AI pipeline.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urljoin
from xml.etree import ElementTree as ET
import argparse
import json
import re
import shutil
import threading
import time

from bs4 import BeautifulSoup
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

TOPICS = ["science-nature", "space", "places", "people-history", "culture-life", "animals"]
LISTS = TOPICS + ["fun-facts-for-kids"]
PAGES = ["random-fun-facts", "about", "history", "contact", "privacy", "terms", "search"]
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*-xfunfacts-[a-z0-9]+$", re.I)
ASSET_ROOTS = ("/css/", "/js/", "/fonts/", "/images/", "/img/", "/icons/")
ORIGIN = "https://uwarboretum.org"
TARGET = "https://funfactsx.github.io"
LOCAL = threading.local()
ROOT = Path(__file__).resolve().parent.parent
TARGET_DIR = ROOT / "site"


def http():
    if not hasattr(LOCAL, "session"):
        s = requests.Session()
        retry = Retry(total=5, status=5, connect=5, read=4,
                      backoff_factor=1.5, status_forcelist=[429, 500, 502, 503, 504])
        s.mount("https://", HTTPAdapter(max_retries=retry))
        s.headers.update({"User-Agent": "Mozilla/5.0 (compatible; FunFactsOwnerStaticMigration/1.0)"})
        LOCAL.session = s
    return LOCAL.session


def fetch(path):
    response = http().get(ORIGIN + path, timeout=(15, 60))
    response.raise_for_status()
    if "text/html" not in response.headers.get("Content-Type", "").lower():
        raise RuntimeError("Expected HTML at " + path)
    if "<html" not in response.text.lower():
        raise RuntimeError("Malformed HTML at " + path)
    return response.text


def count_pages(html):
    soup = BeautifulSoup(html, "lxml")
    nums = [1]
    for a in soup.select(".ff-pager a[href]"):
        v = parse_qs(urlparse(a["href"]).query).get("page", [""])[0]
        if v.isdigit():
            nums.append(int(v))
    for block in soup.select(".ff-section__meta"):
        m = re.search(r"Page\s+\d+\s+of\s+([\d,]+)", block.get_text(" ", strip=True), re.I)
        if m:
            nums.append(int(m.group(1).replace(",", "")))
    return max(nums)


def cards(html, category):
    soup = BeautifulSoup(html, "lxml")
    out = {}
    for card in soup.select("a.ff-card[href]"):
        slug = urlparse(card["href"]).path.strip("/")
        if not SLUG.fullmatch(slug):
            continue
        img = card.find("img")
        title = card.select_one(".ff-card__title")
        cls = next((c[4:] for c in card.get("class", []) if c.startswith("cat-")), category)
        if cls not in TOPICS:
            cls = category if category in TOPICS else ""
        out[slug] = {
            "slug": slug,
            "title": title.get_text(" ", strip=True) if title else slug.replace("-", " "),
            "category": cls,
            "image": (img.get("data-src") or img.get("src") or "") if img else ""
        }
    return out


def save(path, data):
    file = TARGET_DIR / path
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(data, encoding="utf-8")


def rewrite(html, route, preview, category=None, page=None):
    soup = BeautifulSoup(html, "lxml")
    if not soup.html or not soup.head or not soup.body:
        raise ValueError("Incomplete document " + route)

    for el in soup.find_all(True):
        for key in ("href", "src", "content", "data-src", "poster", "action"):
            value = el.get(key)
            if isinstance(value, str) and value.startswith(ORIGIN):
                el[key] = TARGET + value[len(ORIGIN):]

    for el in soup.select('script[type="application/ld+json"]'):
        if el.string:
            el.string.replace_with(el.string.replace(ORIGIN, TARGET))

    for token in soup.select('meta[name="csrf-token"]'):
        token.decompose()

    for script in soup.find_all("script"):
        path = urlparse(script.get("src", "")).path
        if path == "/js/script.js":
            script["src"] = "/js/static.js"
        elif not script.get("src") and "serviceWorker.register" in (script.string or script.get_text()):
            script.decompose()

    for anchor in soup.select("a[href]"):
        u = urlparse(anchor["href"])
        n = parse_qs(u.query).get("page", [""])[0]
        if u.path.strip("/") in LISTS and n.isdigit():
            anchor["href"] = u.path.rstrip("/") if int(n) == 1 else u.path.rstrip("/") + "/page/" + n + "/"

    # GitHub Pages cannot serve different HTML at ?page=2, use real static URLs.
    if category and page and page > 1:
        canonical = TARGET + "/" + category + "/page/" + str(page) + "/"
        for tag in soup.select('link[rel="canonical"]'):
            tag["href"] = canonical
        for tag in soup.select('meta[property="og:url"]'):
            tag["content"] = canonical
        for script in soup.select('script[type="application/ld+json"]'):
            if script.string:
                script.string.replace_with(script.string.replace(
                    TARGET + "/" + category + "?page=" + str(page), canonical))

    if route == "/search":
        main = soup.select_one("main .ff-container") or soup.select_one("main")
        if main is not None:
            section = soup.new_tag("section", id="ff-static-search-results")
            section["class"] = "ff-section"
            main.append(section)

    if preview:
        for tag in soup.select('meta[name="robots"]'):
            tag.decompose()
        meta = soup.new_tag("meta", attrs={"name": "robots", "content": "noindex,nofollow"})
        soup.head.append(meta)

    if not soup.select_one('script[src*="static.js"]'):
        script = soup.new_tag("script", src="/js/static.js")
        script["defer"] = ""
        soup.body.append(script)

    return "<!doctype html>\n" + re.sub(
        r"(?is)^\s*<!doctype[^>]*>\s*", "", str(soup))


def local_path(route, page=1):
    slug = route.strip("/")
    if not slug:
        return "index.html"
    if page > 1:
        return slug + "/page/" + str(page) + "/index.html"
    return slug + ".html"


def download_asset(path):
    u = urlparse(path)
    clean = u.path
    if not (clean.startswith(ASSET_ROOTS) or clean in ["/favicon.ico", "/manifest.json"]):
        return None
    if clean == "/js/script.js" or clean == "/js/static.js":
        return None
    resp = http().get(ORIGIN + clean, timeout=(12, 40))
    if resp.status_code != 200:
        return (clean, False, [])
    data = resp.content
    if len(data) > 15_000_000:
        raise ValueError("Unusually large asset: " + clean)
    dest = TARGET_DIR / clean.lstrip("/")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    extra = []
    if clean.endswith(".css"):
        css = resp.text
        for match in re.findall(r"url\(\s*['\"]?([^)'\"\s]+)", css):
            x = urljoin(ORIGIN + clean, match)
            p = urlparse(x)
            if p.netloc == urlparse(ORIGIN).netloc and p.path.startswith(ASSET_ROOTS):
                extra.append(p.path)
    return (clean, True, extra)


def assets_from_html(html):
    soup = BeautifulSoup(html, "lxml")
    assets = set()
    for tag in soup.find_all(True):
        for prop in ("href", "src", "poster", "data-src"):
            value = tag.get(prop)
            if isinstance(value, str):
                p = urlparse(value)
                if (not p.netloc or p.netloc == urlparse(ORIGIN).netloc) and (
                    p.path.startswith(ASSET_ROOTS) or p.path in ["/favicon.ico", "/manifest.json"]
                ):
                    assets.add(p.path)
    return assets


def make_sitemap(records, page_counts):
    ns = "http://www.sitemaps.org/schemas/sitemap/0.9"
    ET.register_namespace("", ns)
    root = ET.Element("{" + ns + "}urlset")
    routes = [""] + LISTS + [p for p in PAGES if p != "search"]
    routes += [c + "/page/" + str(n) + "/" for c, pages in page_counts.items() for n in range(2, pages + 1)]
    routes += sorted(records)
    for route in dict.fromkeys(routes):
        url = ET.SubElement(root, "{" + ns + "}url")
        ET.SubElement(url, "{" + ns + "}loc").text = TARGET + "/" + route
    ET.ElementTree(root).write(TARGET_DIR / "sitemap.xml", encoding="utf-8", xml_declaration=True)


def export(preview=True, workers=4):
    if TARGET_DIR.exists():
        shutil.rmtree(TARGET_DIR)
    TARGET_DIR.mkdir(parents=True)
    all_assets = set(["/css/style.css", "/favicon.ico", "/manifest.json",
                      "/images/og-share.png", "/images/favicon-32.png"])
    records = {}
    page_counts = {}
    jobs = []
    for route in [""] + PAGES:
        path = "/" + route
        html = fetch(path)
        all_assets.update(assets_from_html(html))
        save(local_path(path), rewrite(html, path, preview))
        print("Static page:", path, flush=True)

    for category in LISTS:
        html = fetch("/" + category)
        n = count_pages(html)
        if not 1 <= n <= 300:
            raise RuntimeError("Bad page count " + category + " " + str(n))
        page_counts[category] = n
        records.update(cards(html, category))
        all_assets.update(assets_from_html(html))
        save(local_path(category), rewrite(html, "/" + category, preview))
        jobs.extend((category, i) for i in range(2, n + 1))
        print(category, n, "pages", flush=True)

    def pull_list(job):
        c, p = job
        route = "/" + c + "?page=" + str(p)
        html = fetch(route)
        got = cards(html, c)
        if not got:
            raise RuntimeError("Missing cards on " + route)
        save(local_path(c, p), rewrite(html, route, preview, c, p))
        return got, assets_from_html(html)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for f in as_completed([pool.submit(pull_list, x) for x in jobs]):
            rec, assets = f.result()
            records.update(rec)
            all_assets.update(assets)

    if len(records) < 3000:
        raise RuntimeError("INCOMPLETE: only " + str(len(records)) + " distinct articles")

    def pull_fact(slug):
        html = fetch("/" + slug)
        soup = BeautifulSoup(html, "lxml")
        if not soup.find("h1") or not soup.select_one('link[rel="canonical"]'):
            raise RuntimeError("Invalid fact " + slug)
        save(local_path(slug), rewrite(html, "/" + slug, preview))
        return assets_from_html(html)

    missing = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(pull_fact, s): s for s in sorted(records)}
        for index, future in enumerate(as_completed(futures), 1):
            try:
                all_assets.update(future.result())
            except Exception as error:
                missing.append([futures[future], str(error)])
            if index % 250 == 0:
                print("Articles processed", index, "/", len(records), flush=True)
    if missing:
        save("failures.json", json.dumps(missing, indent=2))
        raise RuntimeError("INCOMPLETE: " + str(len(missing)) + " article requests failed")

    assets = set(all_assets)
    checked = set()
    failures = []
    while assets:
        todo = sorted(assets - checked)
        if not todo:
            break
        checked.update(todo)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for f in as_completed([pool.submit(download_asset, x) for x in todo]):
                result = f.result()
                if result:
                    path, ok, extra = result
                    if not ok:
                        failures.append(path)
                    assets.update(extra)
        if len(checked) > 1500:
            raise RuntimeError("Suspiciously many assets")
    if not (TARGET_DIR / "css/style.css").exists():
        raise RuntimeError("Missing essential CSS: /css/style.css")
    print("Assets copied", len(checked), "; missing optional", failures[:25], flush=True)

    (TARGET_DIR / "js").mkdir(exist_ok=True)
    shutil.copy2(ROOT / "scripts/static.js", TARGET_DIR / "js/static.js")
    (TARGET_DIR / ".nojekyll").write_text("", encoding="utf-8")
    (TARGET_DIR / "facts.json").write_text(
        json.dumps(sorted(records.values(), key=lambda x: x["slug"]), ensure_ascii=False), encoding="utf-8")
    make_sitemap(records, page_counts)
    (TARGET_DIR / "robots.txt").write_text(
        "User-agent: *\nDisallow: /\n" if preview else
        "User-agent: *\nAllow: /\nSitemap: " + TARGET + "/sitemap.xml\n", encoding="utf-8")
    save("404.html", "<!doctype html><html lang='en'><head><meta name='robots' content='noindex'><title>404 | Fun Facts</title><link rel='stylesheet' href='/css/style.css'></head><body><main style='padding:6rem 1rem;text-align:center'><h1>Page not found</h1><p><a href='/'>Go home</a></p></main></body></html>")
    report = {"origin": ORIGIN, "host": TARGET, "preview": preview, "articles": len(records),
              "pages": page_counts, "assets": len(checked), "missing_optional_assets": failures,
              "created_utc": datetime.now(timezone.utc).isoformat()}
    save("build-report.json", json.dumps(report, ensure_ascii=False, indent=2))
    print("Export finished", json.dumps(report), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--production", action="store_true", help="Make the mirrored site indexable; default safe noindex preview")
    p.add_argument("--workers", type=int, default=4)
    args = p.parse_args()
    if not 1 <= args.workers <= 8:
        p.error("workers must be 1..8")
    export(preview=not args.production, workers=args.workers)
