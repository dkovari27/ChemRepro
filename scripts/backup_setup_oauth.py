#!/usr/bin/env python3
"""
One-time OAuth2 setup for Google Drive backups.
Run this once locally:  python scripts/backup_setup_oauth.py
It opens a browser, you log in as chemrepro@gmail.com, and saves Backup/token.json.
"""
import json
import os

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
CLIENT = os.path.join(os.path.dirname(__file__), "..", "Backup", "oauth_client.json")
TOKEN  = os.path.join(os.path.dirname(__file__), "..", "Backup", "token.json")

flow = InstalledAppFlow.from_client_secrets_file(CLIENT, SCOPES)
creds = flow.run_local_server(port=0)

with open(TOKEN, "w") as f:
    f.write(creds.to_json())

print(f"Token saved to {TOKEN}")
print("\nCopy this value into Railway as GDRIVE_TOKEN_JSON:")
print(creds.to_json())
