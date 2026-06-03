import json
import os
import re
import sys
from collections import Counter
from email.utils import parseaddr
from pathlib import Path

from dotenv import load_dotenv

from backend.groq_client import chat_completions_create, has_groq_keys, is_rate_limit_error

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

load_dotenv()

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

CAREER_CATEGORIES = {
    "Job",
    "Internship",
    "Interview",
    "Networking",
    "Learning",
    "College",
}

PRIORITY_BY_CATEGORY = {
    "Security": 95,
    "Interview": 90,
    "Account": 85,
    "Job": 80,
    "Internship": 75,
    "College": 70,
    "Learning": 60,
    "Networking": 55,
    "AI Tools": 50,
    "Finance": 65,
    "Travel": 65,
    "Support": 75,
    "Events": 50,
    "Health": 60,
    "Shopping": 40,
    "Social": 45,
    "Promotion": 35,
    "Product Updates": 30,
    "Notifications": 30,
    "Newsletter": 25,
    "Entertainment": 35,
    "Spam": 10,
    "Other": 20,
}

DOMAIN_COMPANY_MAP = {
    "linkedin.com": "LinkedIn",
    "google.com": "Google",
    "accounts.google.com": "Google",
    "apple.com": "Apple",
    "icloud.com": "Apple",
    "spotify.com": "Spotify",
    "udemy.com": "Udemy",
    "coursera.org": "Coursera",
    "openai.com": "OpenAI",
    "gamma.app": "Gamma",
    "razorpay.com": "Razorpay",
    "leetcode.com": "LeetCode",
    "wisecut.video": "Wisecut",
    "letsupgrade.in": "LetsUpgrade",
    "letsupgrade.com": "LetsUpgrade",
    "amazon.com": "Amazon",
    "amazon.in": "Amazon",
    "meta.com": "Meta",
    "facebook.com": "Meta",
    "microsoft.com": "Microsoft",
}

SPAM_PATTERNS = [
    r"\bfree money\b",
    r"\blottery\b",
    r"\bcrypto giveaway\b",
    r"\burgent action required\b",
    r"\bclick here now\b",
    r"\bclick link below\b",
    r"\bclaim now\b",
    r"\bverify your wallet\b",
    r"\bcongratulations you won\b",
]

SPAM_PROMO_PATTERNS = [
    r"\boffer\b",
    r"\bdiscount\b",
    r"\bsale\b",
    r"\bpremium\b",
    r"\bdeal\b",
]

VALIDATION_RULES = [
    (
        "Account",
        [
            r"\bpan\b",
            r"\bverify your identity\b",
            r"\baccount access\b",
            r"\bbilling\b",
            r"\bpayment\b",
            r"\baccount update\b",
        ],
    ),
    (
        "Security",
        [
            r"accounts\.google\.com",
            r"\blogin\b",
            r"\bsign in\b",
            r"\bsecurity alert\b",
            r"\bsuspicious activity\b",
            r"\bpassword\b",
            r"\bverification\b",
        ],
    ),
    (
        "Networking",
        [r"linkedin\.com", r"\bmessaged you\b", r"\bprofile views\b", r"\bconnection request\b"],
    ),
    ("Internship", [r"\binternship\b", r"\bsummer internship\b", r"\btraining program\b"]),
    (
        "Interview",
        [
            r"\binterview (invitation|invite|schedule|round|call|process|loop|date|with|panel)\b",
            r"\btechnical interview\b",
            r"\bconfirm your interview\b",
            r"\bscheduled an interview\b",
            r"\bhr interview\b",
            r"\bassessment\b",
            r"\bcoding round\b",
            r"\baptitude test\b",
        ],
    ),
    ("Learning", [r"udemy\.com", r"coursera\.org", r"\bcourse\b", r"\bworkshop\b", r"\bbootcamp\b"]),
    ("AI Tools", [r"\bai agents?\b", r"openai\.com", r"\bchatgpt\b", r"\bgamma\b", r"\bcopilot\b"]),
    ("Promotion", [r"spotify\.com", r"\boffer\b", r"\bpremium\b", r"\bdiscount\b", r"\bsale\b"]),
    ("Product Updates", [r"\bproduct update\b", r"\brelease notes\b", r"\bnew feature\b", r"\bupdate\b"]),
    ("Newsletter", [r"\bnewsletter\b", r"\bdigest\b", r"\bweekly update\b", r"\broundup\b"]),
]

DEADLINE_PATTERNS = [
    r"\bdeadline\b",
    r"\bapply before\b",
    r"\blast date\b",
    r"\bdue date\b",
    r"\bexam date\b",
    r"\binterview date\b",
    r"\btoday\b",
    r"\btomorrow\b",
    r"\bnext week\b",
    r"\bthis week\b",
    r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2}(?:,\s*\d{4})?\b",
    r"\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b",
]


def normalize_text(value):
    return re.sub(r"\s+", " ", (value or "").lower()).strip()


def normalize_category(value):
    if not value:
        return "Other"

    normalized = normalize_text(value)
    for category in ALLOWED_CATEGORIES:
        if normalize_text(category) == normalized:
            return category

    aliases = {
        "ai": "AI Tools",
        "ai tool": "AI Tools",
        "product update": "Product Updates",
        "notification": "Notifications",
        "intern": "Internship",
        "interviews": "Interview",
        "job opportunity": "Job",
    }

    return aliases.get(normalized, "Other")


def build_email_text(email):
    return normalize_text(
        f"{email.get('subject', '')} {email.get('body', '')} {email.get('sender', '')}"
    )


def extract_domain(address):
    if "@" not in address:
        return ""
    return address.split("@", 1)[1].lower().strip()


def clean_company_name(value):
    if not value:
        return ""

    cleaned = re.sub(r"[<>{}\[\]()|\\/]+", " ", value)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,-_")
    return cleaned[:60].strip()


def extract_company(email):
    sender = email.get("sender", "")
    display_name, address = parseaddr(sender)
    domain = extract_domain(address)

    if not domain:
        raw_sender = normalize_text(sender)
        if raw_sender and " " not in raw_sender and "." in raw_sender and "@" not in raw_sender:
            domain = raw_sender

    if domain in DOMAIN_COMPANY_MAP:
        return DOMAIN_COMPANY_MAP[domain]

    for known_domain, company in DOMAIN_COMPANY_MAP.items():
        if domain.endswith(f".{known_domain}"):
            return company

    cleaned_display = clean_company_name(display_name)
    if cleaned_display:
        return cleaned_display

    if domain:
        return clean_company_name(domain.split(".")[0]) or clean_company_name(domain)

    return "Unknown"


def spam_signal_score(email):
    text = build_email_text(email)
    sender = email.get("sender", "")
    _display_name, address = parseaddr(sender)

    score = 0

    for pattern in SPAM_PATTERNS:
        if re.search(pattern, text):
            score += 25

    promo_hits = sum(1 for pattern in SPAM_PROMO_PATTERNS if re.search(pattern, text))
    if promo_hits >= 2:
        score += 20

    if not address and promo_hits > 0:
        score += 20

    if address and re.search(r"\d{5,}", address):
        score += 10

    return min(score, 100)


def detect_deadline(email):
    text = normalize_text(f"{email.get('subject', '')} {email.get('body', '')}")
    for pattern in DEADLINE_PATTERNS:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return {"deadline": match.group(0).strip(), "deadlineDetected": True}
    return {"deadline": "", "deadlineDetected": False}


def _safe_json_load(content):
    cleaned = (content or "").strip()
    cleaned = cleaned.replace("```json", "").replace("```", "").strip()
    return json.loads(cleaned)


def clean_email_body(body: str, max_chars: int = 1000) -> str:
    if not body:
        return ""
    # Strip HTML tags
    clean = re.sub(r"<[^>]*>", " ", body)
    # Strip URLs to avoid distracting the model and bloating tokens
    clean = re.sub(r"https?://\S+", "", clean)
    # Normalize excessive spaces and newlines
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean[:max_chars]


def parse_confidence(val) -> int:
    if isinstance(val, (int, float)):
        if 0 <= val <= 1:
            return int(val * 100)
        return int(val)
    if isinstance(val, str):
        try:
            val = val.replace("%", "").strip()
            num = float(val)
            if 0 <= num <= 1:
                return int(num * 100)
            return int(num)
        except ValueError:
            pass
    return 70  # default fallback


def classify_with_groq(email, company):
    subject = email.get("subject", "")
    sender = email.get("sender", "")
    body = email.get("body", "")

    fallback = {
        "company": company or "Unknown",
        "category": "Other",
        "subcategory": "",
        "reason": "Groq unavailable",
        "confidence": 0,
        "failed": True,
    }

    if not has_groq_keys():
        fallback["reason"] = "No Groq API keys configured (GROQ_API_KEY / GROQ_API_KEY1)"
        return fallback

    # Clean and truncate body to conserve tokens and prevent rate limits
    cleaned_body = clean_email_body(body, max_chars=1000)

    prompt = f"""
You are an email classification engine.

Choose EXACTLY ONE category from:

Security
Account
Spam
Promotion
Newsletter
Job
Internship
Interview
Networking
Learning
College
AI Tools
Social
Finance
Shopping
Travel
Events
Support
Product Updates
Notifications
Health
Entertainment
Other

Return JSON only.

{{
  "category": "",
  "subcategory": "",
  "reason": "",
  "confidence": 0
}}

Company hint:
{company}

Subject:
{subject}

Sender:
{sender}

Body:
{cleaned_body}
"""

    try:
        response = chat_completions_create(
            model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
            messages=[
                {"role": "system", "content": "Return only JSON. No markdown, no prose."},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
        )
        data = _safe_json_load(response.choices[0].message.content or "")
    except Exception as error:
        fallback["reason"] = str(error)
        if is_rate_limit_error(error):
            fallback["reason"] = (
                "All Groq API keys hit rate limits. "
                "Add another key or wait for quota reset. "
                f"Last error: {error}"
            )
        return fallback

    confidence = parse_confidence(data.get("confidence"))
    category = normalize_category(data.get("category"))

    return {
        "company": data.get("company") or company or "Unknown",
        "category": category if category in ALLOWED_CATEGORIES else "Other",
        "subcategory": (data.get("subcategory") or "").strip(),
        "reason": (data.get("reason") or "").strip(),
        "confidence": max(0, min(100, confidence)),
        "failed": False,
    }


def validate_classification(email, ai_result):
    sender = email.get("sender", "")
    subject = normalize_text(email.get("subject", ""))
    body = normalize_text(email.get("body", ""))
    sender_text = normalize_text(sender)
    confidence = ai_result.get("confidence", 0)
    text = f"{subject} {body} {sender_text}"

    # Always override to Spam if the spam heuristic score is high, regardless of AI confidence
    if spam_signal_score(email) >= 45:
        return {"applied": True, "category": "Spam", "reason": "Spam heuristic override"}

    if ai_result.get("failed") or confidence < 60:
        for category, patterns in VALIDATION_RULES:
            for pattern in patterns:
                if re.search(pattern, text, flags=re.IGNORECASE):
                    return {"applied": True, "category": category, "reason": f"Validation matched {pattern}"}

    return {"applied": False, "category": ai_result.get("category", "Other"), "reason": "Kept AI result"}


def derive_priority(category, email=None, ai_confidence=70):
    base = PRIORITY_BY_CATEGORY.get(category, PRIORITY_BY_CATEGORY["Other"])
    if not email:
        return base

    subject = normalize_text(email.get("subject", ""))
    body = normalize_text(email.get("body", ""))
    text = f"{subject} {body}"
    
    boost = 0
    
    # 1. Boost for upcoming deadlines (Urgent)
    deadline_info = detect_deadline(email)
    if deadline_info.get("deadlineDetected"):
        boost += 15
        
    # 2. Boost/Deboost for critical career keywords
    if category in {"Job", "Internship", "Interview"}:
        text_lower = text.lower()
        if any(w in text_lower for w in ["offer", "selected", "shortlisted", "hired", "congratulations"]):
            boost += 15
        elif any(w in text_lower for w in ["next steps", "schedule", "call", "urgent", "action required"]):
            boost += 10
        elif any(w in text_lower for w in ["reject", "regret", "not moving forward", "unsuccessful"]):
            boost -= 15

    # 3. Boost based on AI confidence
    if ai_confidence >= 90:
        boost += 5
    elif ai_confidence < 70:
        boost -= 5

    return max(1, min(99, base + boost))


def build_subcategory(email, classification):
    if classification.get("subcategory"):
        return classification["subcategory"][:80]

    subject = (email.get("subject") or "").strip()
    if subject:
        return subject[:80]

    company = classification.get("company") or extract_company(email)
    return f"{company} {classification.get('category', 'Other')}".strip()[:80]


def classify_with_heuristics(email, company):
    """
    Check if we can classify the email with high confidence using rule-based heuristics,
    completely bypassing the Groq AI model call.
    """
    subject = normalize_text(email.get("subject", ""))
    body = normalize_text(email.get("body", ""))
    sender = normalize_text(email.get("sender", ""))
    text = f"{subject} {body} {sender}"
    
    # 1. Spam High Confidence Heuristic
    if spam_signal_score(email) >= 45:
        return {
            "company": company or "Unknown",
            "category": "Spam",
            "subcategory": "Spam Alert",
            "reason": "Spam heuristic high confidence match",
            "confidence": 95,
            "failed": False,
            "heuristic": True
        }
        
    # 2. Security Alerts (very common)
    security_patterns = [
        r"accounts\.google\.com",
        r"\bsecurity alert\b",
        r"\bpassword reset\b",
        r"\bverification code\b",
        r"\bsign-in alert\b",
        r"\bnew login\b",
        r"\bsuspicious activity\b",
        r"\bconfirm your account\b",
        r"\bverify your email\b"
    ]
    if any(re.search(pat, text) for pat in security_patterns):
        return {
            "company": company or "Unknown",
            "category": "Security",
            "subcategory": "Security Alert",
            "reason": "Security heuristic match",
            "confidence": 95,
            "failed": False,
            "heuristic": True
        }

    # 3. Social & Networking
    social_patterns = [
        r"linkedin\.com",
        r"facebookmail\.com",
        r"twitter\.com",
        r"instagram\.com",
        r"\bconnection request\b",
        r"\bmessaged you\b",
        r"\bnew follower\b"
    ]
    if any(re.search(pat, text) for pat in social_patterns):
        category = "Networking" if "linkedin.com" in text or "connection" in text else "Social"
        return {
            "company": company or "Unknown",
            "category": category,
            "subcategory": "Social Notification",
            "reason": "Social heuristic match",
            "confidence": 90,
            "failed": False,
            "heuristic": True
        }

    # 4. Newsletters (Unsubscribe link present + informational keywords)
    if "unsubscribe" in body and any(k in subject for k in ["newsletter", "digest", "weekly", "daily", "roundup", "update"]):
        return {
            "company": company or "Unknown",
            "category": "Newsletter",
            "subcategory": "Weekly Digest",
            "reason": "Newsletter heuristic match",
            "confidence": 90,
            "failed": False,
            "heuristic": True
        }

    return None


def categorize_email(email):
    company = extract_company(email)
    
    # Try Heuristics First
    heuristic_result = classify_with_heuristics(email, company)
    if heuristic_result:
        ai_result = heuristic_result
    else:
        ai_result = classify_with_groq(email, company)
        
    validation = validate_classification(email, ai_result)
    final_category = ai_result.get("category", "Other")

    # Apply validation if the validation category is Spam (always overrides) 
    # or if AI failed or has low confidence
    if validation.get("applied") and (
        validation.get("category") == "Spam"
        or ai_result.get("failed")
        or ai_result.get("confidence", 0) < 60
    ):
        final_category = validation["category"]

    if final_category not in ALLOWED_CATEGORIES:
        final_category = "Other"

    deadline_info = detect_deadline(email)
    
    # Filter/clean deadline based on final category to prevent false-positives
    # (e.g. login dates in Security/Account/Social emails being marked as deadlines)
    if final_category in {"Security", "Account", "Social", "Networking", "Support", "Product Updates", "Notifications", "Other", "Spam"}:
        strong_deadline_keywords = [r"\bdeadline\b", r"\bdue\b", r"\bexpire\b", r"\bapply\b", r"\bcutoff\b"]
        text_to_check = normalize_text(f"{email.get('subject', '')} {email.get('body', '')}")
        if not any(re.search(kw, text_to_check) for kw in strong_deadline_keywords):
            deadline_info = {"deadline": "", "deadlineDetected": False}

    career_related = final_category in CAREER_CATEGORIES
    confidence = ai_result.get("confidence", 0)
    if validation.get("applied") and validation.get("category") != ai_result.get("category"):
        confidence = max(0, confidence - 5)

    return {
        "company": ai_result.get("company") or company or "Unknown",
        "ai_category": ai_result.get("category", "Other"),
        "ai_confidence": ai_result.get("confidence", 0),
        "ai_reason": ai_result.get("reason", ""),
        "validation_result": validation,
        "category": final_category,
        "subcategory": build_subcategory(
            email,
            {"company": company, "category": final_category, "subcategory": ai_result.get("subcategory", "")},
        ),
        "confidence": max(0, min(100, confidence)),
        "priority": derive_priority(final_category, email, confidence),
        "deadline": deadline_info["deadline"],
        "deadlineDetected": deadline_info["deadlineDetected"],
        "career_related": career_related,
        "summary": (email.get("subject") or email.get("body") or "No summary available")[:220],
    }


def print_debug(email, classification):
    print("---")
    print(f"## Subject: {email.get('subject', '')}")
    print(f"Sender: {email.get('sender', '')}")
    print(f"Company: {classification.get('company', 'Unknown')}")
    print(f"AI Category: {classification.get('ai_category', '')}")
    print(f"AI Confidence: {classification.get('ai_confidence', 0)}")
    print(f"Validation Result: {classification.get('validation_result', {})}")
    print(f"Final Category: {classification.get('category', '')}")
    print(f"Priority: {classification.get('priority', 0)}")
    print(f"Career Related: {classification.get('career_related', False)}")


def save_results(items, path="results.json"):
    normalized = []

    for item in items:
        normalized.append(
            {
                "id": item.get("id"),
                "subject": item.get("subject", ""),
                "sender": item.get("sender", ""),
                "company": item.get("company") or "Unknown",
                "category": normalize_category(item.get("category")),
                "subcategory": item.get("subcategory") or "",
                "confidence": max(0, min(100, int(item.get("confidence", 0) or 0))),
                "priority": max(1, min(100, int(item.get("priority", 20) or 20))),
                "deadline": item.get("deadline") or None,
                "deadlineDetected": bool(item.get("deadline") or item.get("deadlineDetected")),
                "career_related": bool(item.get("career_related")),
                "ai_category": normalize_category(item.get("ai_category")),
                "ai_confidence": max(0, min(100, int(item.get("ai_confidence", 0) or 0))),
                "ai_reason": item.get("ai_reason") or "",
                "validation_result": item.get("validation_result") or {},
                "summary": item.get("summary") or "",
                "body": item.get("body") or "",
                "internalDate": item.get("internalDate"),
            }
        )

    with open(path, "w", encoding="utf-8") as results_file:
        json.dump(normalized, results_file, indent=4)

    return normalized


def build_analytics(results):
    category_counter = Counter(item.get("category", "Other") for item in results)
    company_counter = Counter(
        item.get("company", "Unknown") for item in results if item.get("company") and item.get("company") != "Unknown"
    )
    ai_counter = Counter(item.get("ai_category", "Other") for item in results)
    validation_corrections = [
        item
        for item in results
        if item.get("validation_result", {}).get("applied")
        and item.get("validation_result", {}).get("category") != item.get("ai_category")
    ]
    career_emails = [item for item in results if item.get("career_related")]
    spam_emails = [item for item in results if item.get("category") == "Spam"]
    deadlines = [item for item in results if item.get("deadlineDetected")]

    return {
        "categoryDistribution": dict(category_counter),
        "topCompanies": company_counter.most_common(10),
        "careerEmails": career_emails,
        "spamEmails": spam_emails,
        "deadlinesFound": deadlines,
        "aiClassifications": dict(ai_counter),
        "validationCorrections": validation_corrections,
    }


def print_analytics(results):
    analytics = build_analytics(results)

    print("\n" + "=" * 70)
    print("CATEGORY DISTRIBUTION")
    print("=" * 70)
    for category, count in Counter(analytics["categoryDistribution"]).most_common():
        print(f"{category:<20} : {count}")

    print("\n" + "=" * 70)
    print("TOP COMPANIES")
    print("=" * 70)
    for company, count in analytics["topCompanies"]:
        print(f"{company:<25} : {count}")

    print("\n" + "=" * 70)
    print("CAREER EMAILS")
    print("=" * 70)
    print(f"Count: {len(analytics['careerEmails'])}")

    print("\n" + "=" * 70)
    print("SPAM EMAILS")
    print("=" * 70)
    print(f"Count: {len(analytics['spamEmails'])}")

    print("\n" + "=" * 70)
    print("DEADLINES FOUND")
    print("=" * 70)
    print(f"Count: {len(analytics['deadlinesFound'])}")

    print("\n" + "=" * 70)
    print("AI CLASSIFICATIONS")
    print("=" * 70)
    for category, count in Counter(analytics["aiClassifications"]).most_common():
        print(f"{category:<20} : {count}")

    print("\n" + "=" * 70)
    print("VALIDATION CORRECTIONS")
    print("=" * 70)
    print(f"Count: {len(analytics['validationCorrections'])}")


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


def analyze_emails(emails, debug=False):
    results = []

    if debug:
        print("\nAnalyzing emails in parallel...\n")

    from concurrent.futures import ThreadPoolExecutor

    def process_email(email):
        try:
            classification = categorize_email(email)
            if debug:
                print_debug(email, classification)

            return {
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
                "career_related": classification.get("career_related", False),
                "ai_category": classification.get("ai_category", "Other"),
                "ai_confidence": classification.get("ai_confidence", 0),
                "ai_reason": classification.get("ai_reason", ""),
                "validation_result": classification.get("validation_result", {}),
                "summary": classification["summary"],
                "body": email.get("body", ""),
                "internalDate": email.get("internalDate"),
            }
        except Exception as error:
            if debug:
                print(f"Error processing: {email.get('subject', '')}")
                print(error)
            return None

    # Run AI classifications with 5 parallel workers
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(process_email, email) for email in emails]
        for fut in futures:
            res = fut.result()
            if res:
                results.append(res)

    return results


def main():
    with open("emails.json", "r", encoding="utf-8") as emails_file:
        emails = json.load(emails_file)

    results = analyze_emails(emails, debug=True)
    normalized_results = save_results(results)

    print_analytics(normalized_results)
    print_top_priority(normalized_results)
    print_deadlines(normalized_results)

    print("\n" + "=" * 70)
    print("Results saved to results.json")
    print("=" * 70)


if __name__ == "__main__":
    main()
