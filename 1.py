import argparse
import json
import re
from html import unescape
from typing import Any

import requests

URL = "https://energy.volyn.ua/spozhyvacham/perervy-u-elektropostachanni/cherga/#move"


# Optional cookies from the original script. They can be left empty.
DEFAULT_COOKIES = {
    "cf_clearance": "",
    "PHPSESSID": "",
    "__cf_bm": "",
}

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:148.0) Gecko/20100101 Firefox/148.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Content-Type": "application/x-www-form-urlencoded",
    "Origin": "https://energy.volyn.ua",
    "Referer": "https://energy.volyn.ua/spozhyvacham/perervy-u-elektropostachanni/cherga/",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
    "DNT": "1",
    "Priority": "u=0, i",
}


def clean_text(value: str) -> str:
    text = unescape(value)
    text = re.sub(r"<[^>]*>", "", text)
    text = text.replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def extract_results_table(html: str) -> list[dict[str, str]]:
    """Extract the table with columns:
    District, Locality, Street, House, GPV queue, GAV queue.
    """
    table_match = re.search(
        r"<table[^>]*>\s*<tr[^>]*>\s*<td>Район</td>.*?</table>",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not table_match:
        return []

    table_html = table_match.group(0)
    row_blocks = re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, flags=re.IGNORECASE | re.DOTALL)
    if len(row_blocks) <= 1:
        return []

    results: list[dict[str, str]] = []
    for row_html in row_blocks[1:]:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row_html, flags=re.IGNORECASE | re.DOTALL)
        if len(cells) < 6:
            continue

        district, locality, street, house, gpv_queue, gav_queue = (clean_text(c) for c in cells[:6])
        if house == "<>":
            house = ""

        results.append(
            {
                "district": district,
                "locality": locality,
                "street": street,
                "house": house,
                "gpv_queue": gpv_queue,
                "gav_queue": gav_queue,
            }
        )

    return results


def group_by_gpv_queue(rows: list[dict[str, str]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        queue = row["gpv_queue"] or "unknown"
        if queue not in grouped:
            grouped[queue] = {
                "queue": queue,
                "addresses_count": 0,
                "addresses": [],
            }

        grouped[queue]["addresses"].append(
            {
                "district": row["district"],
                "locality": row["locality"],
                "street": row["street"],
                "house": row["house"],
                "gav_queue": row["gav_queue"],
            }
        )
        grouped[queue]["addresses_count"] += 1

    return dict(sorted(grouped.items(), key=lambda item: item[0]))


def fetch_html(city: str, street: str, timeout: int = 30) -> str:
    data = {
        "formCity": city,
        "formStreet": street,
    }

    cookies = {k: v for k, v in DEFAULT_COOKIES.items() if v}

    response = requests.post(
        URL,
        headers=DEFAULT_HEADERS,
        cookies=cookies,
        data=data,
        timeout=timeout,
    )
    response.raise_for_status()
    return response.text


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse Volynoblenergo queue search page into JSON")
    parser.add_argument("city_arg", nargs="?", default="", help="City/locality for request (positional)")
    parser.add_argument("street_arg", nargs="?", default="", help="Street for request (positional)")
    parser.add_argument("--city", default="", help="City/locality for request (named)")
    parser.add_argument("--street", default="", help="Street for request (named)")
    parser.add_argument("--output", default="queues_result.json", help="Output JSON path")
    parser.add_argument("--save-html", default="1.html", help="Where to save fetched HTML")
    parser.add_argument(
        "--input-html",
        default="",
        help="Use existing HTML file instead of sending request",
    )
    args = parser.parse_args()
    city = args.city or args.city_arg or ""
    street = args.street or args.street_arg or ""

    if args.input_html:
        with open(args.input_html, "r", encoding="utf-8") as f:
            html = f.read()
    else:
        html = fetch_html(city, street)
        with open(args.save_html, "w", encoding="utf-8") as f:
            f.write(html)

    rows = extract_results_table(html)
    grouped = group_by_gpv_queue(rows)

    payload = {
        "query": {
            "city": city,
            "street": street,
        },
        "total_rows": len(rows),
        "rows": rows,
        "queues_gpv": grouped,
    }

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"Saved {len(rows)} rows to {args.output}")


if __name__ == "__main__":
    main()
