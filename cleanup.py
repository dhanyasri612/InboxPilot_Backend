import requests

API_BASE_URL = "http://localhost:8000"

PROMOTION_CATEGORIES = {
    "Promotion",
    "Newsletter",
    "Spam",
}

def get_cleanup_candidates():
    cleanup_candidates = []
    for category in PROMOTION_CATEGORIES:
        response = requests.get(f"{API_BASE_URL}/emails/category/{category}")
        if response.status_code == 200:
            cleanup_candidates.extend(response.json())
    return cleanup_candidates

def print_cleanup_candidates(cleanup_candidates):
    print("\n")
    print("=" * 60)
    print("EMAILS THAT CAN BE CLEANED")
    print("=" * 60)

    for i, email in enumerate(cleanup_candidates, start=1):
        print(f"{i}. {email['subject']}")

    print(f"\nFound {len(cleanup_candidates)} emails.")

def run_cleanup(cleanup_candidates):
    choice = input("\nMove these emails to Trash? (y/n): ")

    if choice.lower() != "y":
        print("Cleanup cancelled.")
        return

    deleted_count = 0
    for email in cleanup_candidates:
        try:
            response = requests.delete(f"{API_BASE_URL}/email/{email['gmail_id']}")
            if response.status_code == 200:
                deleted_count += 1
                print(f"Moved to Trash: {email['subject']}")
            else:
                print(f"Failed to delete: {email['subject']}")
        except Exception as e:
            print(f"An error occurred while deleting {email['subject']}: {e}")

    print("\n")
    print("=" * 60)
    print(f"Moved {deleted_count} emails to Trash")
    print("=" * 60)

if __name__ == "__main__":
    candidates = get_cleanup_candidates()
    if candidates:
        print_cleanup_candidates(candidates)
        run_cleanup(candidates)
    else:
        print("No emails to clean up.")