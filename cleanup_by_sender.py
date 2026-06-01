import json
import os

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

creds = Credentials.from_authorized_user_file(
    "token.json",
    SCOPES
)

service = build(
    "gmail",
    "v1",
    credentials=creds
)

with open("results.json", "r") as f:
    results = json.load(f)

promotion_senders = set()

for email in results:

    if email["category"] in [
        "Promotion",
        "Newsletter"
    ]:

        sender = email["sender"]

        # Extract actual email address
        if "<" in sender and ">" in sender:
            sender = sender.split("<")[1].split(">")[0]

        promotion_senders.add(sender)

print("\nPromotion Senders Found:\n")

for sender in promotion_senders:
    print(sender)

choice = input(
    "\nDelete emails from these senders? (y/n): "
)

if choice.lower() != "y":
    exit()

deleted = 0

for sender in promotion_senders:

    query = f"from:{sender}"

    response = service.users().messages().list(
        userId="me",
        q=query,
        maxResults=100
    ).execute()

    messages = response.get(
        "messages",
        []
    )

    print(
        f"\n{sender}: {len(messages)} emails"
    )

    for msg in messages:

        service.users().messages().trash(
            userId="me",
            id=msg["id"]
        ).execute()

        deleted += 1

print(
    f"\nDeleted {deleted} emails."
)