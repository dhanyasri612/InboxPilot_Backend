import sys
from pathlib import Path
import requests

ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import gmail_client

API_BASE_URL = "http://localhost:8000"

PROMOTION_CATEGORIES = {
    "Promotion",
    "Newsletter",
    "Spam",
}

def get_user_email():
    try:
        profile = gmail_client.get_gmail_profile()
        if profile and profile.get("emailAddress"):
            return profile["emailAddress"]
    except Exception:
        pass
    
    email = input("Enter your Gmail address: ").strip()
    return email

def get_cleanup_candidates(user_email):
    cleanup_candidates = []
    response = requests.get(f"{API_BASE_URL}/emails?email={user_email}&range=all")
    if response.status_code == 200:
        all_emails = response.json()
        for email in all_emails:
            if email.get("category") in PROMOTION_CATEGORIES:
                cleanup_candidates.append(email)
    return cleanup_candidates

def print_cleanup_candidates(cleanup_candidates):
    print("\n")
    print("=" * 60)
    print("EMAILS THAT CAN BE CLEANED")
    print("=" * 60)

    for i, email in enumerate(cleanup_candidates, start=1):
        print(f"{i}. [{email.get('category', 'Other')}] {email.get('subject', 'No Subject')}")

    print(f"\nFound {len(cleanup_candidates)} emails.")

def run_cleanup(cleanup_candidates, user_email):
    choice = input("\nMove these emails to Trash? (y/n): ")

    if choice.lower() != "y":
        print("Cleanup cancelled.")
        return

    deleted_count = 0
    for email in cleanup_candidates:
        try:
            response = requests.post(
                f"{API_BASE_URL}/emails/delete",
                json={"messageId": email["id"], "email": user_email}
            )
            if response.status_code == 200:
                deleted_count += 1
                print(f"Moved to Trash: {email['subject']}")
            else:
                print(f"Failed to delete: {email['subject']} (Status: {response.status_code})")
        except Exception as e:
            print(f"An error occurred while deleting {email['subject']}: {e}")

    print("\n")
    print("=" * 60)
    print(f"Moved {deleted_count} emails to Trash")
    print("=" * 60)

if __name__ == "__main__":
    email = get_user_email()
    if not email:
        print("Gmail address is required.")
        sys.exit(1)
        
    candidates = get_cleanup_candidates(email)
    if candidates:
        print_cleanup_candidates(candidates)
        run_cleanup(candidates, email)
    else:
        print("No emails to clean up.")