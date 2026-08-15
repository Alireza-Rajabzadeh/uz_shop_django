import json
import os
from pathlib import Path

import requests
from django.core.management.base import BaseCommand

CONTRACTS_PATH = Path(__file__).resolve().parent.parent.parent.parent / "domains" / "content" / "data" / "content_contracts.json"


class Command(BaseCommand):
    help = "Fetch the client panel content component contracts and save them as a JSON file"

    def add_arguments(self, parser):
        parser.add_argument(
            "--url",
            type=str,
            default=os.getenv("CLIENT_PANEL_BASE_URL", "http://localhost:3000/api/content/components"),
            help="Client panel contracts endpoint URL",
        )

    def handle(self, *args, **options):
        url = options["url"]
        try:
            response = requests.get(url, timeout=15)
            response.raise_for_status()
        except requests.RequestException as exc:
            self.stderr.write(self.style.ERROR(f"Failed to fetch contracts from {url}: {exc}"))
            raise SystemExit(1)

        payload = response.json()
        CONTRACTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONTRACTS_PATH.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        self.stdout.write(self.style.SUCCESS(f"Saved {len(payload.get('components', []))} contracts to {CONTRACTS_PATH}"))
