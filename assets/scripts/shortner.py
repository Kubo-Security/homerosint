#!/usr/bin/env python3

import argparse
import asyncio
import aiohttp
import csv

from urllib.parse import urlparse
from rich.console import Console
from rich.table import Table
from rich.text import Text

CSV_URL = (
    "https://raw.githubusercontent.com/"
    "sambokai/ShortURL-Services-List/master/"
    "shorturl-services-list.csv"
)

PATTERNS = [
    "/{}",
    "/go/{}",
    "/s/{}",
    "/r/{}",
    "/u/{}",
    "/link/{}",
    "/short/{}",
    "/redirect/{}",
    "/index.php/{}",
    "/?{}",
    "/?id={}",
    "/?url={}",
    "/?code={}",
]

TIMEOUT = aiohttp.ClientTimeout(total=10)

console = Console()


# -------------------------
# NORMALISATION DOMAINE
# -------------------------
def normalize_host(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()

        if ":" in host:
            host = host.split(":")[0]

        if host.startswith("www."):
            host = host[4:]

        return host

    except Exception:
        return ""


# -------------------------
# FILTRE CONTENU PAGE
# -------------------------
def is_not_found_page(text: str) -> bool:
    if not text:
        return False

    t = text.lower()

    return (
        "not found" in t or
        "404" in t and "page not found" in t or
        "error 404" in t
    )


def is_homepage(final_url: str) -> bool:
    try:
        path = urlparse(final_url).path.strip("/").lower()

        if path == "":
            return True

        return path in {
            "index.php",
            "index.html",
            "404",
            "error",
            "notfound",
        }

    except Exception:
        return False


# -------------------------
# COULEURS HTTP
# -------------------------
def color_http(status: int) -> Text:

    if status == 200:
        return Text(str(status), style="green")

    if status == 403:
        return Text(str(status), style="orange3")

    if status == 404:
        return Text(str(status), style="red")

    return Text(str(status), style="red")


# -------------------------
# LOAD DOMAINS
# -------------------------
async def load_domains(session):
    async with session.get(CSV_URL) as resp:
        text = await resp.text()

    domains = set()

    for row in csv.reader(text.splitlines()):
        if not row:
            continue

        d = row[0].strip().lower()

        if d and not d.startswith("#"):
            domains.add(d)

    return sorted(domains)


# -------------------------
# RESOLVE URL
# -------------------------
async def resolve(session, short_url):

    try:
        async with session.get(
            short_url,
            allow_redirects=True,
            ssl=False
        ) as resp:

            final_url = str(resp.url)

            text = await resp.text(errors="ignore")

            src = normalize_host(short_url)
            dst = normalize_host(final_url)

            # même domaine => ignore
            if src == dst:
                return None

            # homepage ou erreur classique
            if is_homepage(final_url):
                return None

            # contenu "not found"
            if is_not_found_page(text):
                return None

            return {
                "short_url": short_url,
                "final_url": final_url,
                "status": resp.status,
            }

    except Exception:
        return None


# -------------------------
# TEST DOMAIN
# -------------------------
async def test_domain(session, domain, token):

    urls = []

    for pattern in PATTERNS:

        path = pattern.format(token)

        urls.extend([
            f"https://{domain}{path}",
            f"https://www.{domain}{path}",
            f"http://{domain}{path}",
        ])

    tasks = [resolve(session, u) for u in urls]

    results = await asyncio.gather(*tasks)

    return [r for r in results if r]


# -------------------------
# MAIN RUN
# -------------------------
async def run(token):

    connector = aiohttp.TCPConnector(
        limit=300,
        limit_per_host=10,
        ssl=False
    )

    async with aiohttp.ClientSession(
        connector=connector,
        timeout=TIMEOUT,
    ) as session:

        console.print("[cyan][*][/cyan] Chargement des domaines...")

        domains = await load_domains(session)

        console.print(f"[green][+][/green] {len(domains)} domaines chargés")

        table = Table(show_lines=True)

        table.add_column("URL courte", overflow="fold")
        table.add_column("HTTP", justify="center")
        table.add_column("URL finale", overflow="fold")

        seen = set()
        total = 0

        jobs = [test_domain(session, d, token) for d in domains]

        for future in asyncio.as_completed(jobs):

            results = await future

            for r in results:

                key = (r["short_url"], r["final_url"])

                if key in seen:
                    continue

                seen.add(key)
                total += 1

                table.add_row(
                    r["short_url"],
                    color_http(r["status"]),
                    r["final_url"]
                )

        console.print()
        console.print(table)
        console.print()

        console.print(f"[bold green]Résultats : {total}[/bold green]")


# -------------------------
# CLI
# -------------------------
def main():

    parser = argparse.ArgumentParser()

    parser.add_argument("token", help="Token à tester")

    args = parser.parse_args()

    asyncio.run(run(args.token))


if __name__ == "__main__":
    main()