"""
Garcia Folklorico Studio -- GBP Account & Location Fetcher
One-time setup utility to discover GBP account and location IDs.

Usage:
    python -m gbp.account_fetcher --list
"""

import argparse
from pathlib import Path

from google.auth.transport.requests import AuthorizedSession

from .auth_setup import get_credentials

ACCOUNT_MGMT_URL = "https://mybusinessaccountmanagement.googleapis.com/v1"
BUSI_INFO_URL = "https://mybusinessbusinessinformation.googleapis.com/v1"


def _authed_session() -> AuthorizedSession:
    return AuthorizedSession(get_credentials())


def list_accounts(session: AuthorizedSession) -> list:
    resp = session.get(f"{ACCOUNT_MGMT_URL}/accounts")
    resp.raise_for_status()
    return resp.json().get("accounts", [])


def list_locations(session: AuthorizedSession, account_name: str) -> list:
    resp = session.get(
        f"{BUSI_INFO_URL}/{account_name}/locations",
        params={"readMask": "name,title,storefrontAddress,phoneNumbers"},
    )
    resp.raise_for_status()
    return resp.json().get("locations", [])


def validate_location(session: AuthorizedSession, location_name: str) -> bool:
    try:
        resp = session.get(
            f"{BUSI_INFO_URL}/{location_name}",
            params={"readMask": "name,title"},
        )
        return resp.status_code == 200
    except Exception:
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="List GBP accounts and locations")
    parser.add_argument("--list", action="store_true", help="List all accounts and locations")
    args = parser.parse_args()

    if args.list:
        session = _authed_session()
        accounts = list_accounts(session)

        if not accounts:
            print("No accounts found. Make sure you signed in to the correct Google account.")
        else:
            for acct in accounts:
                acct_name = acct.get("name", "")
                print(f"\nAccount: {acct.get('accountName', '')}  ({acct_name})")
                locations = list_locations(session, acct_name)
                for loc in locations:
                    addr = loc.get("storefrontAddress", {})
                    phones = loc.get("phoneNumbers", {})
                    phone = phones.get("primaryPhone", "N/A")
                    city = addr.get("locality", "")
                    state = addr.get("administrativeArea", "")
                    print(f"  Location : {loc.get('title', '')}  ({loc.get('name', '')})")
                    print(f"  Address  : {city}, {state}")
                    print(f"  Phone    : {phone}")
                    print()

            print("-" * 60)
            print("Copy these values into gbp_config.json:")
            print('  "account_id"  : the accounts/XXXXXXX string above')
            print('  "location_id" : the locations/XXXXXXX string above')
    else:
        parser.print_help()
