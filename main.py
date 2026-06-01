from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from . import crud, models
from .database import SessionLocal, engine, get_db
from .gmail_client import fetch_and_save_emails

models.Base.metadata.create_all(bind=engine)

app = FastAPI()


ALLOWED_CATEGORIES = [
    "Security",
    "Account",
    "Spam",
    "Promotion",
    "Newsletter",
    "Job",
    "Internship",
    "Interview",
    "Networking",
    "Learning",
    "College",
    "AI Tools",
    "Social",
    "Finance",
    "Shopping",
    "Travel",
    "Events",
    "Support",
    "Product Updates",
    "Notifications",
    "Health",
    "Entertainment",
    "Other",
]

PRIORITY_ORDER = [
    "Security",
    "Account",
    "Interview",
    "Internship",
    "Job",
    "Finance",
    "College",
    "Networking",
    "Learning",
    "AI Tools",
    "Support",
    "Product Updates",
    "Events",
    "Notifications",
    "Travel",
    "Shopping",
    "Promotion",
    "Newsletter",
    "Social",
    "Health",
    "Entertainment",
    "Spam",
    "Other",
]

PRIORITY_BY_CATEGORY = {
    category: max(5, 100 - (index * 4))
    for index, category in enumerate(PRIORITY_ORDER)
}

CATEGORY_RULES = {
    "Security": [
        r"\blogin\b",
        r"\bsign in\b",
        r"\bverification\b",
        r"\bsecurity alert\b",
        r"\bsuspicious activity\b",
        r"\bpassword\b",
        r"\bsecure your account\b",
        r"\bcheck activity\b",
        r"\ballowed access\b",
    ],
    "Account": [
        r"\bstorage warning\b",
        r"\bsubscription\b",
        r"\bbilling\b",
        r"\bpayment\b",
        r"\baccount update\b",
        r"\baccount notice\b",
        r"\bicloud storage\b",
    ],
    "Promotion": [
        r"\boffer\b",
        r"\bsale\b",
        r"\bdiscount\b",
        r"\bcoupon\b",
        r"\blimited time\b",
        r"\bdeal\b",
        r"\bspecial offer\b",
    ],
    "Newsletter": [
        r"\bnewsletter\b",
        r"\bdigest\b",
        r"\bweekly update\b",
        r"\bmonthly update\b",
        r"\bcommunity update\b",
    ],
    "Interview": [
        r"\binterview\b",
        r"\bassessment\b",
        r"\bcoding test\b",
        r"\baptitude test\b",
    ],
    "Internship": [r"\binternship\b", r"\bintern\b", r"\btrainee\b"],
    "Job": [
        r"\bhiring\b",
        r"\bcareer opportunity\b",
        r"\brecruitment\b",
        r"\bvacancy\b",
        r"\bopening\b",
        r"\bposition\b",
        r"\bassociate\b",
        r"\bjob alert\b",
    ],
    "Networking": [
        r"\bconnect\b",
        r"\binvitation\b",
        r"\bprofile views\b",
        r"\bconnection request\b",
        r"\blinkedin invitation\b",
    ],
    "Learning": [
        r"\bcourse\b",
        r"\bwebinar\b",
        r"\bcertification\b",
        r"\btutorial\b",
        r"\bbootcamp\b",
        r"\bworkshop\b",
    ],
    "College": [
        r"\buniversity\b",
        r"\bcollege\b",
        r"\bexam\b",
        r"\bassignment\b",
        r"\bplacement\b",
        r"\bacademic\b",
    ],
    "AI Tools": [
        r"\bchatgpt\b",
        r"\bopenai\b",
        r"\bclaude\b",
        r"\bgemini\b",
        r"\bcopilot\b",
        r"\bgamma\b",
        r"\bai platform\b",
    ],
    "Social": [
        r"\bpinterest\b",
        r"\binstagram\b",
        r"\bfacebook\b",
        r"\bx\b",
        r"\btwitter\b",
        r"\blinkedin social notifications\b",
    ],
    "Finance": [
        r"\bbank\b",
        r"\btransaction\b",
        r"\bstatement\b",
        r"\bcredit card\b",
        r"\binvestment\b",
    ],
    "Shopping": [
        r"\bamazon\b",
        r"\bflipkart\b",
        r"\bmyntra\b",
        r"\border shipped\b",
        r"\border delivered\b",
    ],
    "Travel": [
        r"\bflight\b",
        r"\bhotel\b",
        r"\bbooking\b",
        r"\breservation\b",
    ],
    "Events": [
        r"\bconference\b",
        r"\bmeetup\b",
        r"\bhackathon\b",
        r"\bevent invitation\b",
    ],
    "Support": [
        r"\bsupport ticket\b",
        r"\bcustomer support\b",
        r"\bhelpdesk\b",
    ],
    "Product Updates": [
        r"\bnew feature\b",
        r"\brelease notes\b",
        r"\bupdate available\b",
        r"\bproduct announcement\b",
    ],
    "Notifications": [
        r"\breminders\b",
        r"\balerts\b",
        r"\bstatus updates\b",
        r"\bautomated notifications\b",
    ],
    "Health": [
        r"\bmedical\b",
        r"\bhospital\b",
        r"\bappointment\b",
        r"\bhealthcare\b",
    ],
    "Entertainment": [
        r"\bmovie\b",
        r"\bmusic\b",
        r"\bstreaming\b",
        r"\byoutube updates\b",
    ],
}

SPAM_PATTERNS = [
    r"\bcongratulations you won\b",
    r"\bfree money\b",
    r"\bcrypto giveaway\b",
    r"\blottery\b",
    r"\burgent action required\b",
    r"\bsuspicious marketing\b",
    r"\bclick here now\b",
]

PROMO_WORDS = [
    r"\boffer\b",
    r"\bdiscount\b",
    r"\bsale\b",
    r"\bcoupon\b",
    r"\bdeal\b",
    r"\bbuy now\b",
]

DOMAIN_COMPANY_MAP = {
    "linkedin.com": "LinkedIn",
    "apple.com": "Apple",
    "email.apple.com": "Apple",
    "google.com": "Google",
    "dev.to": "DEV Community",
    "cursor.com": "Cursor",
    "mail.cursor.com": "Cursor",
    "openai.com": "OpenAI",
    "pinterest.com": "Pinterest",
    "instagram.com": "Instagram",
    "facebook.com": "Facebook",
    "twitter.com": "Twitter",
    "x.com": "X",
    "gamma.app": "Gamma",
    "udemy.com": "Udemy",
    "coursera.org": "Coursera",
    "amazon.in": "Amazon",
    "amazon.com": "Amazon",
    "flipkart.com": "Flipkart",
    "myntra.com": "Myntra",
    "youtube.com": "YouTube",
}

GENERIC_SENDER_TOKENS = {
    "team",
    "support",
    "noreply",
    "no-reply",
    "notification",
    "notifications",
    "update",
    "updates",
    "alerts",
    "alert",
    "mailer",
}


def normalize_text(value):
    return re.sub(r"\s+", " ", (value or "").lower()).strip()


def normalize_category(value):
    if not value:
        return "Other"

    normalized = normalize_text(value)
    aliases = {
        "ai": "AI Tools",
        "ai tool": "AI Tools",
        "product update": "Product Updates",
        "notification": "Notifications",
    }

    if normalized in aliases:
        return aliases[normalized]

    for category in ALLOWED_CATEGORIES:
        if normalize_text(category) == normalized:
            return category

    return "Other"


def build_email_text(email):
    return normalize_text(
        f"{email.get('subject', '')} {email.get('body', '')} {email.get('sender', '')}"
    )


def extract_domain(address):
    if "@" not in address:
        return ""
    return address.split("@", 1)[1].lower().strip()


def extract_company(email):
    sender = email.get("sender", "")
    subject = email.get("subject", "")
    display_name, address = parseaddr(sender)
    domain = extract_domain(address)

    for known_domain, company in DOMAIN_COMPANY_MAP.items():
        if domain == known_domain or domain.endswith(f".{known_domain}"):
            return company

    cleaned_display = clean_company_name(display_name)
    if cleaned_display:
        return cleaned_display

    root_from_domain = root_domain_name(domain)
    if root_from_domain:
        return root_from_domain

    if subject:
        candidate = clean_company_name(subject)
        if candidate:
            return candidate

    return "Unknown"


def root_domain_name(domain):
    if not domain:
        return ""

    pieces = [piece for piece in domain.split(".") if piece]
    if len(pieces) < 2:
        return clean_company_name(domain)

    if pieces[-2] in {"co", "com", "org", "net"} and len(pieces) >= 3:
        base = pieces[-3]
    else:
        base = pieces[-2]

    return clean_company_name(base)


def clean_company_name(value):
    if not value:
        return ""

    cleaned = re.sub(r"[<>\[\]{}()|\\/]+", " ", value)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,-_")
    if not cleaned:
        return ""

    words = []
    for word in cleaned.split():
        lower = word.lower()
        if lower in GENERIC_SENDER_TOKENS:
            continue
        if lower.startswith("http"):
            continue
        words.append(word)

    if not words:
        return ""

    final_name = " ".join(words).strip()
    if len(final_name) > 60:
        final_name = final_name[:60].strip()
    return final_name


def spam_signal_score(email):
    text = build_email_text(email)
    sender = email.get("sender", "")
    _display_name, address = parseaddr(sender)

    score = 0

    for pattern in SPAM_PATTERNS:
        if re.search(pattern, text):
            score += 25

    promo_hits = sum(1 for pattern in PROMO_WORDS if re.search(pattern, text))
    if promo_hits >= 2:
        score += 20

    emoji_count = len(re.findall(r"[\U0001F300-\U0001FAFF]", sender + " " + email.get("subject", "")))
    if emoji_count >= 3:
        score += 20

    if not address and promo_hits > 0:
        score += 25

    if address and re.search(r"\d{5,}", address):
        score += 15

    return min(score, 100)


def detect_rule_category(email):
    text = build_email_text(email)

    spam_score = spam_signal_score(email)
    if spam_score >= 45:
        return "Spam", spam_score, ["spam_signals"]

    matches = []
    for category, patterns in CATEGORY_RULES.items():
        category_hits = [pattern for pattern in patterns if re.search(pattern, text)]
        if category_hits:
            matches.append((category, category_hits))

    if not matches:
        return None, 0, []

    order_index = {category: index for index, category in enumerate(PRIORITY_ORDER)}
    matches.sort(key=lambda item: order_index.get(item[0], 999))

    selected_category, selected_hits = matches[0]
    confidence = min(99, 80 + (len(selected_hits) * 6))
    return selected_category, confidence, selected_hits


def extract_deadline(email):
    text = normalize_text(f"{email.get('subject', '')} {email.get('body', '')}")
    patterns = [
        r"\b(?:deadline|due by|apply by|apply before)\s+([^.!,\n]{3,60})",
        r"\b(?:before|by)\s+((?:today|tomorrow|tonight|this week|next week|monday|tuesday|wednesday|thursday|friday|saturday|sunday|\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2}(?:,\s*\d{4})?))\b",
        r"\b(?:today|tomorrow|tonight|this week|next week|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
        r"\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b",
        r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2}(?:,\s*\d{4})?\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip() if match.groups() else match.group(0).strip()

    return None


def generate_ai_summary(email, company_hint=None):
    subject = email.get("subject", "")
    sender = email.get("sender", "")
    body = email.get("body", "")[:900]

    if not client:
        return {
            "company": company_hint or "Unknown",
            "category": "Notifications",
            "confidence": 55,
            "priority": PRIORITY_BY_CATEGORY.get("Notifications", 40),
            "deadline": extract_deadline(email),
            "summary": (subject or body[:150] or "No summary available")[:220],
            "failed": True,
        }

    prompt = f"""
You are classifying a production inbox email.

Subject:
{subject}

Sender:
{sender}

Body:
{body}

Return only valid JSON with keys:
company, category, confidence, priority, deadline, summary

Allowed categories:
{', '.join(ALLOWED_CATEGORIES)}

Rules:
- Choose exactly one allowed category.
- confidence must be integer 0-100.
- Use null for deadline when absent.
"""

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": "Return only JSON. No markdown, no prose.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0,
        )

        content = (response.choices[0].message.content or "").strip()
        content = content.replace("```json", "").replace("```", "").strip()
        data = json.loads(content)
    except Exception:
        return {
            "company": company_hint or "Unknown",
            "category": "Notifications",
            "confidence": 55,
            "priority": PRIORITY_BY_CATEGORY.get("Notifications", 40),
            "deadline": extract_deadline(email),
            "summary": (subject or body[:150] or "No summary available")[:220],
            "failed": True,
        }

    category = normalize_category(data.get("category"))
    confidence = data.get("confidence") if isinstance(data.get("confidence"), int) else 72
    priority = data.get("priority") if isinstance(data.get("priority"), int) else PRIORITY_BY_CATEGORY.get(category, 30)

    return {
        "company": data.get("company") or company_hint or "Unknown",
        "category": category,
        "confidence": max(0, min(100, confidence)),
        "priority": max(1, min(100, priority)),
        "deadline": data.get("deadline") or extract_deadline(email),
        "summary": (data.get("summary") or subject or body[:150] or "No summary available")[:220],
        "failed": False,
    }


def fallback_category_without_ai(email):
    text = build_email_text(email)
    sender = normalize_text(email.get("sender", ""))

    if re.search(r"\b(notification|notifier|noreply|no-reply|alert)\b", sender):
        return "Notifications"

    if re.search(r"\bhelp|support|ticket\b", text):
        return "Support"

    if re.search(r"\bupdate|release|feature\b", text):
        return "Product Updates"

    if re.search(r"\border|delivery|shipped\b", text):
        return "Shopping"

    return "Notifications"


def generate_summary(email, company, category):
    subject = (email.get("subject") or "No Subject").strip()
    body = re.sub(r"\s+", " ", email.get("body", "")).strip()

    summary = subject if subject else body[:160]
    if not summary:
        summary = "No summary available"

    if company and company != "Unknown" and company.lower() not in summary.lower():
        summary = f"{company} {category.lower()} - {summary}"

    return summary[:220]


def generate_subcategory(email, category):
    subject = (email.get("subject") or "").strip()
    if subject:
        return subject[:80]

    company = extract_company(email)
    return f"{company} {category}".strip()[:80]


def derive_priority(category, email, deadline=None):
    priority = PRIORITY_BY_CATEGORY.get(category, 20)
    text = build_email_text(email)

    if deadline:
        priority += 6

    if re.search(r"\burgent\b|\basap\b|\bimmediately\b|\bfinal reminder\b|\blast chance\b", text):
        priority += 8

    return max(1, min(100, priority))


def categorize_email(email):
    company = extract_company(email)
    rule_category, rule_confidence, _rule_hits = detect_rule_category(email)

    ai_category = "Skipped"

    if rule_category:
        final_category = rule_category
        confidence = rule_confidence
        deadline = extract_deadline(email)
        priority = derive_priority(final_category, email, deadline)
        summary = generate_summary(email, company, final_category)
    else:
        ai_result = generate_ai_summary(email, company_hint=company)
        ai_category = ai_result.get("category", "Notifications")

        if ai_result.get("failed"):
            final_category = fallback_category_without_ai(email)
            confidence = 55
            priority = derive_priority(final_category, email)
            deadline = extract_deadline(email)
            summary = generate_summary(email, company, final_category)
        else:
            final_category = normalize_category(ai_result.get("category"))
            confidence = ai_result.get("confidence", 72)
            priority = ai_result.get("priority", derive_priority(final_category, email))
            deadline = ai_result.get("deadline")
            summary = ai_result.get("summary") or generate_summary(email, company, final_category)
            company = ai_result.get("company") or company

    if final_category not in ALLOWED_CATEGORIES:
        final_category = "Other"

    confidence = max(0, min(100, int(confidence)))
    priority = max(1, min(100, int(priority)))
    subcategory = generate_subcategory(email, final_category)

    return {
        "company": company or "Unknown",
        "rule_category": rule_category or "None",
        "ai_category": ai_category,
        "category": final_category,
        "subcategory": subcategory,
        "confidence": confidence,
        "priority": priority,
        "deadline": deadline,
        "deadlineDetected": bool(deadline),
        "summary": summary,
    }


@app.post("/sync")
def sync_emails(db: Session = Depends(get_db)):
    fetch_and_save_emails(db)
    return {"message": "Email synchronization completed successfully."}

@app.get("/emails", response_model=list[models.Email])
def read_emails(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    emails = crud.get_emails(db, skip=skip, limit=limit)
    return emails

@app.get("/emails/category/{category}", response_model=list[models.Email])
def read_category_emails(category: str, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    emails = crud.get_category_emails(db, category=category, skip=skip, limit=limit)
    return emails

@app.get("/career", response_model=list[models.Email])
def read_career_emails(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    emails = crud.get_career_emails(db, skip=skip, limit=limit)
    return emails

@app.get("/dashboard")
def get_dashboard_stats(db: Session = Depends(get_db)):
    total_emails = db.query(models.Email).count()
    jobs = db.query(models.Email).filter(models.Email.category == "Job").count()
    internships = db.query(models.Email).filter(models.Email.category == "Internship").count()
    interviews = db.query(models.Email).filter(models.Email.category == "Interview").count()
    security_alerts = db.query(models.Email).filter(models.Email.category == "Security").count()
    deadlines = db.query(models.Email).filter(models.Email.deadline != None).count()
    
    return {
        "total_emails": total_emails,
        "jobs": jobs,
        "internships": internships,
        "interviews": interviews,
        "security_alerts": security_alerts,
        "deadlines": deadlines,
    }

@app.delete("/email/{gmail_id}")
def delete_email_endpoint(gmail_id: str, db: Session = Depends(get_db)):
    db_email = crud.delete_email(db, gmail_id=gmail_id)
    if db_email is None:
        raise HTTPException(status_code=404, detail="Email not found")
    # Here you would also add the logic to delete the email from Gmail
    return {"message": "Email marked as deleted."}



def print_debug(email, classification):
    print("---")
    print(f"## Subject: {email.get('subject', '')}")
    print(f"Sender: {email.get('sender', '')}")
    print(f"Detected Company: {classification['company']}")
    print(f"Rule Category: {classification['rule_category']}")
    print(f"AI Category: {classification['ai_category']}")
    print(f"Final Category: {classification['category']}")
    print(f"Subcategory: {classification.get('subcategory', '')}")
    print(f"Confidence: {classification['confidence']}")
    print(f"Priority: {classification['priority']}")


def print_analytics(results):
    category_counter = Counter(item.get("category", "Other") for item in results)
    company_counter = Counter(
        item.get("company", "Unknown")
        for item in results
        if item.get("company") and item.get("company") != "Unknown"
    )

    print("\n" + "=" * 70)
    print("CATEGORY DISTRIBUTION")
    print("=" * 70)
    for category, count in category_counter.most_common():
        print(f"{category:<20} : {count}")

    print("\n" + "=" * 70)
    print("TOP COMPANIES")
    print("=" * 70)
    for company, count in company_counter.most_common(10):
        print(f"{company:<25} : {count}")

    print("\n" + "=" * 70)
    print("CATEGORY METRICS")
    print("=" * 70)
    print(f"Spam Count             : {category_counter.get('Spam', 0)}")
    print(f"Jobs Count             : {category_counter.get('Job', 0)}")
    print(f"Internship Count       : {category_counter.get('Internship', 0)}")
    print(f"Interviews Count       : {category_counter.get('Interview', 0)}")
    print(f"Learning Emails Count  : {category_counter.get('Learning', 0)}")
    print(f"Security Alerts Count  : {category_counter.get('Security', 0)}")
    print(f"Promotions Count       : {category_counter.get('Promotion', 0)}")
    print(f"Newsletters Count      : {category_counter.get('Newsletter', 0)}")


def print_deadlines(results):
    print("\n" + "=" * 70)
    print("UPCOMING DEADLINES")
    print("=" * 70)

    found = False
    for item in results:
        if item.get("deadline"):
            found = True
            print(f"Deadline : {item['deadline']}")
            print(f"Category : {item['category']}")
            print(f"Subject  : {item['subject']}")
            print("-" * 40)

    if not found:
        print("No deadlines detected.")


def print_top_priority(results):
    sorted_items = sorted(results, key=lambda item: item.get("priority", 0), reverse=True)

    print("\n" + "=" * 70)
    print("TOP PRIORITY EMAILS")
    print("=" * 70)

    for item in sorted_items[:10]:
        print(
            f"{item['priority']:>3} | "
            f"{item['confidence']:>3}% | "
            f"{item['category']:<18} | "
            f"{item['subject']}"
        )


def generate_daily_brief(results):
    print("\n" + "=" * 70)
    print("AI DAILY BRIEF")
    print("=" * 70)

    if not client:
        print("GROQ_API_KEY1 is not set, so the daily brief was skipped.")
        return

    prompt = f"""
Analyze these inbox results and produce concise bullet points:
- Most important emails
- Deadlines
- Career opportunities
- Promotions
- Security/account alerts

Results:
{json.dumps(results, indent=2)}
"""

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        print(response.choices[0].message.content)
    except Exception as error:
        print("Could not generate summary.")
        print(error)


def analyze_emails(emails, debug=False):
    results = []

    if debug:
        print("\nAnalyzing emails...\n")

    for email in emails:
        try:
            classification = categorize_email(email)
            if debug:
                print_debug(email, classification)

            results.append(
                {
                    "id": email.get("id"),
                    "subject": email.get("subject", ""),
                    "sender": email.get("sender", ""),
                    "company": classification["company"],
                    "category": classification["category"],
                    "subcategory": classification.get("subcategory", ""),
                    "confidence": classification["confidence"],
                    "priority": classification["priority"],
                    "deadline": classification["deadline"],
                    "deadlineDetected": classification.get("deadlineDetected", False),
                    "summary": classification["summary"],
                    "body": email.get("body", ""),
                    "internalDate": email.get("internalDate"),
                }
            )
        except Exception as error:
            if debug:
                print(f"Error processing: {email.get('subject', '')}")
                print(error)

    return results


def main():
    from backend.categorization import main as run_pipeline

    run_pipeline()


from backend.categorization import (  # noqa: E402
    analyze_emails,
    categorize_email,
    print_analytics,
    print_deadlines,
    print_debug,
    print_top_priority,
    save_results,
)


if __name__ == "__main__":
    main()