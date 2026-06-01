import json

with open("results.json", "r") as f:
    results = json.load(f)

print("\nSMART ACTIONS\n")

for email in results:

    action = email.get("action", "Keep")

    print(
        f"[{action}] "
        f"{email['subject']}"
    )