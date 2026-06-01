from database import SessionLocal
import crud


def get_career_opportunities(user_email: str):
    db = SessionLocal()
    try:
        opportunities = crud.get_career_emails(db, user_email)
    finally:
        db.close()
    
    # Sort By Priority
    opportunities = sorted(
        opportunities,
        key=lambda x: x.priority,
        reverse=True
    )
    
    return opportunities

def print_career_dashboard(opportunities):
    jobs = sum(1 for item in opportunities if item.category == "Job")
    internships = sum(1 for item in opportunities if item.category == "Internship")
    interviews = sum(1 for item in opportunities if item.category == "Interview")

    print("\n")
    print("=" * 70)
    print("           INBOXPILOT CAREER TRACKER")
    print("=" * 70)

    print(f"Jobs        : {jobs}")
    print(f"Internships : {internships}")
    print(f"Interviews  : {interviews}")

def print_top_opportunities(opportunities):
    print("\n")
    print("=" * 70)
    print("              TOP OPPORTUNITIES")
    print("=" * 70)

    if not opportunities:
        print("No career opportunities found.")
    else:
        for i, item in enumerate(opportunities, start=1):
            print("\n" + "-" * 70)
            print(f"Rank      : {i}")
            print(f"Category  : {item.category}")
            print(f"Priority  : {item.priority}")
            print(f"Subject   : {item.subject}")

            if item.deadline:
                print(f"Deadline  : {item.deadline}")

            if item.summary:
                print(f"Summary   : {item.summary}")

if __name__ == "__main__":
    import os
    import sys

    user_email = (os.getenv("INBOX_USER_EMAIL") or (sys.argv[1] if len(sys.argv) > 1 else "")).strip()
    if not user_email:
        raise SystemExit("Usage: INBOX_USER_EMAIL=you@gmail.com python career_tracker.py")
    opportunities = get_career_opportunities(user_email)
    print_career_dashboard(opportunities)
    print_top_opportunities(opportunities)