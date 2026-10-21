#!/usr/bin/env python3
"""
Exchange a short-lived Instagram access token for a long-lived one (~60 days).
"""

import os
import requests

def main():
    short_token = os.environ.get("IG_ACCESS_TOKEN")
    app_secret = os.environ.get("IG_APP_SECRET")

    if not short_token or not app_secret:
        print("Error: IG_ACCESS_TOKEN and IG_APP_SECRET must be set.")
        return

    url = "https://graph.instagram.com/access_token"
    params = {
        "grant_type": "ig_exchange_token",
        "client_secret": app_secret,
        "access_token": short_token,
    }
    r = requests.get(url, params=params, timeout=15)
    if not r.ok:
        print(f"Error {r.status_code}: {r.text}")
        return
    data = r.json()

    long_token = data["access_token"]
    expires_in_days = data.get("expires_in", 0) / 86400

    print(f"\nLong-lived token generated. Expires in ~{expires_in_days:.0f} days.\n")
    print("Run this to update your environment variable:\n")
    print(f'export IG_ACCESS_TOKEN="{long_token}"')


if __name__ == "__main__":
    main()
