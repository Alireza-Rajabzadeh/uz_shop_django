from pathlib import Path
import re
import shutil
import time
from urllib.parse import urljoin

from .contracts import ApprovedCategory
from .filesystem import read_json, write_json_atomic
from .listing import page_url


BASE_URL = "https://www.digikala.com"
CATEGORY_API = re.compile(
    r"^https://api\.digikala\.com/discovery/api/v2/categories/(\d+)/products(?:\?.*)?$"
)


def canonical_categories(path):
    manifest = read_json(path)
    result = {}

    def visit(items):
        for item in items:
            result[int(item["id"])] = item
            visit(item.get("children", []))

    visit(manifest.get("categories", []))
    return result


def system_chromium(explicit=None):
    if explicit:
        path = Path(explicit).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"Chromium executable not found: {path}")
        return str(path)
    for name in ("chromium", "chromium-browser", "google-chrome"):
        executable = shutil.which(name)
        if executable:
            return executable
    snap = Path("/snap/bin/chromium")
    return str(snap) if snap.exists() else None


def discover_categories(
    category_manifest,
    category_ids,
    output_path,
    *,
    chromium_path=None,
    headful=False,
    timeout=30,
    retries=3,
    delay=1.0,
    progress=None,
):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright is required for discovery; install scripts/requirements-digikala-discovery.txt."
        ) from exc

    records = canonical_categories(category_manifest)
    selected = []
    for category_id in dict.fromkeys(int(value) for value in category_ids):
        record = records.get(category_id)
        if record is None:
            raise ValueError(f"Category {category_id} is not in the canonical manifest.")
        if record.get("children"):
            raise ValueError(f"Category {category_id} is not a leaf category.")
        selected.append(record)
    if not selected:
        raise ValueError("Discovery requires at least one leaf category.")

    discovered = []
    with sync_playwright() as playwright:
        options = {"headless": not headful}
        executable = system_chromium(chromium_path)
        if executable:
            options["executable_path"] = executable
        browser = playwright.chromium.launch(**options)
        context = browser.new_context(locale="fa-IR")
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        context.route(
            "**/*",
            lambda route: route.abort()
            if route.request.resource_type in {"image", "media", "font"}
            else route.continue_(),
        )
        try:
            for index, record in enumerate(selected, start=1):
                last_error = None
                for attempt in range(1, retries + 1):
                    page = context.new_page()
                    captured = []

                    def capture(response):
                        match = CATEGORY_API.match(response.url)
                        if match and 200 <= response.status < 300:
                            captured.append((int(match.group(1)), response.url))

                    page.on("response", capture)
                    try:
                        try:
                            page.goto(
                                urljoin(BASE_URL, record["source_url"]),
                                wait_until="domcontentloaded",
                                timeout=timeout * 1000,
                            )
                        except Exception:
                            pass
                        deadline = time.monotonic() + timeout
                        while not captured and time.monotonic() < deadline:
                            page.wait_for_timeout(250)
                        if not captured:
                            raise RuntimeError("No category product API response was captured.")
                        digikala_id, api_url = captured[0]
                        approved = ApprovedCategory.from_dict(
                            {
                                "category_id": int(record["id"]),
                                "name": record["name"],
                                "digikala_category_id": digikala_id,
                                "api_url": page_url(api_url, 1),
                            }
                        )
                        discovered.append(approved)
                        if progress:
                            progress(
                                {
                                    "index": index,
                                    "count": len(selected),
                                    **approved.as_dict(),
                                }
                            )
                        break
                    except Exception as exc:
                        last_error = exc
                        if attempt < retries:
                            time.sleep(delay * attempt)
                    finally:
                        page.close()
                else:
                    raise RuntimeError(
                        f"Category {record['id']} discovery failed: {last_error}"
                    )
                if index < len(selected):
                    time.sleep(delay)
        finally:
            context.close()
            browser.close()

    write_json_atomic(
        output_path,
        {
            "schema": "uzshop.digikala.category-mappings/v1",
            "categories": [category.as_dict() for category in discovered],
        },
        overwrite=True,
    )
    return discovered
