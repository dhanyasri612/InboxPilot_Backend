import json

import gmail_client

FETCH_OPTIONS = [
    ("1", "today"),
    ("2", "7d"),
    ("3", "30d"),
    ("4", "all"),
]


def prompt_fetch_range():
    print("\nInboxPilot Email Fetch Options\n")

    for choice, range_key in FETCH_OPTIONS:
        option = gmail_client.get_range_config(range_key)
        print(f"{choice}. {option['label']}")

    choice = input("\nChoose option: ").strip()

    for option_choice, range_key in FETCH_OPTIONS:
        if choice == option_choice:
            return range_key

    return "all"


def prompt_saved_account_action(profile):
    print(f"\nSaved Gmail account detected: {profile['emailAddress']}")
    choice = input("Reuse this account? (y/N): ").strip().lower()

    if choice == "y":
        return True

    gmail_client.clear_credentials()
    print("Saved token removed. Starting a new Gmail authorization.")
    return False


def main():
    creds = gmail_client.load_credentials()

    if creds:
        profile = gmail_client.get_gmail_profile()
        if profile and not prompt_saved_account_action(profile):
            creds = None

    if not creds:
        print("\nGmail authorization required.")
        gmail_client.run_cli_oauth()

    profile = gmail_client.get_gmail_profile()
    if profile:
        print(f"\nLogged in as: {profile['emailAddress']}")

    range_key = prompt_fetch_range()
    range_config = gmail_client.get_range_config(range_key)

    print(f"\nFetching: {range_config['label']}...")
    result = gmail_client.fetch_and_save_emails(range_key)

    print("\n" + "=" * 60)
    print(f"Saved {result['count']} emails to emails.json")
    print("=" * 60)


if __name__ == "__main__":
    main()
