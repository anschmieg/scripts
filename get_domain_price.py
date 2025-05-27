import argparse
import json
import os

import requests
from dotenv import load_dotenv

load_dotenv()

# Config
DOMAINR_HOST = "domainr.p.rapidapi.com"
DOMAINR_BASE_URL = f"https://{DOMAINR_HOST}/v2/status"
DOMAINR_API_KEY = os.getenv("DOMAINR_RAPIDAPI_KEY")

DNSIMPLE_API_BASE = os.getenv("DNSIMPLE_API_BASE", "https://api.dnsimple.com/v2")
DNSIMPLE_ACCOUNT_ID = os.getenv("DNSIMPLE_ACCOUNT_ID")
DNSIMPLE_API_TOKEN = os.getenv("DNSIMPLE_API_TOKEN")


def get_domainr_status(domain):
    """Check availability and premium flag via Domainr (RapidAPI)."""
    headers = {"x-rapidapi-host": DOMAINR_HOST, "x-rapidapi-key": DOMAINR_API_KEY}
    params = {"domain": domain}
    resp = requests.get(DOMAINR_BASE_URL, headers=headers, params=params)
    resp.raise_for_status()
    status = resp.json()["status"][0]["status"].split()
    return {
        "available": "undelegated" in status or "inactive" in status,
        "premium": "premium" in status,
    }


def get_tld_fees(tld):
    """Fetch standard registry fees for a TLD from DNSimple."""
    url = f"{DNSIMPLE_API_BASE}/{DNSIMPLE_ACCOUNT_ID}/tlds/{tld}"
    headers = {
        "Authorization": f"Bearer {DNSIMPLE_API_TOKEN}",
        "Accept": "application/json",
    }
    r = requests.get(url, headers=headers)
    r.raise_for_status()
    data = r.json()["data"]
    return {
        "registration": float(data["registration_fee"]),
        "transfer": float(data["transfer_fee"]),
    }


def check_domains(domains):
    results = {}
    for name in domains:
        if "." not in name:
            raise ValueError(f"Invalid domain: {name}")
        tld = name.rsplit(".", 1)[1]

        st = get_domainr_status(name)
        fees = get_tld_fees(tld)
        price = fees["registration"] if st["available"] else fees["transfer"]

        results[name] = {
            "available": st["available"],
            "premium": st["premium"],
            "price": price,
        }
    return results


if __name__ == "__main__":
    for var in ("DOMAINR_RAPIDAPI_KEY", "DNSIMPLE_ACCOUNT_ID", "DNSIMPLE_API_TOKEN"):
        if not os.getenv(var):
            raise SystemExit(f"Please set {var}")

    parser = argparse.ArgumentParser(
        description="Lookup domain availability, premium flag and price"
    )
    parser.add_argument(
        "domains", nargs="+", help="Domains to check, e.g. example.com foo.bet"
    )
    args = parser.parse_args()

    output = check_domains(args.domains)
    print(json.dumps(output, indent=2))
