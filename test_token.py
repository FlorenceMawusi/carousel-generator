#!/usr/bin/env python3
"""Quick sanity check: is the current IG_ACCESS_TOKEN valid and usable?"""

import os
import requests

def main():
    token = os.environ.get("IG_ACCESS_TOKEN")
    user_id = os.environ.get("IG_USER_ID")
    if not token or not user_id:
        print("Error: IG_ACCESS_TOKEN and IG_USER_ID must be set.")
        return

    url = f"https://graph.instagram.com/v21.0/{user_id}"
    params = {"fields": "id,username,account_type", "access_token": token}
    r = requests.get(url, params=params, timeout=15)
    print(f"Status: {r.status_code}")
    print(r.text)


if __name__ == "__main__":
    main()
