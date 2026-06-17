# 📬 Email Response Playbook — Ink Division

## Classification & Handling Rules

### 1. Review Collaboration (Brands Requesting Product Reviews)
**Signal:** "review", "try our product", "sample", "send you our", "check out our [product]"
**Handling:** FULLY AUTONOMOUS
**Template:**
> Hi [Name],
>
> Thanks for reaching out! We'd be happy to consider your product for review on The Shopper's Verdict. We cover [matching categories] and specialize in honest, data-driven reviews based on real Amazon customer feedback.
>
> A few things to help us move forward:
> - Product ASIN / Amazon listing link
> - Any promotional period or deadline
> - Whether you have a sample available
>
> Please note that being added to our review queue does not guarantee a positive verdict — we always publish honest assessments.
>
> Best,
> Ink 🖋️
> The Shopper's Verdict

### 2. Sponsored Post / Paid Feature
**Signal:** "sponsor", "paid", "partnership", "collaboration", "advertise", "promote", "budget"
**Handling:** DRAFT → ALERT GABRIEL before sending
**Template:**
> Hi [Name],
>
> Thank you for your interest! We do offer sponsored content opportunities on The Shopper's Verdict. Could you share more details about what you're looking for?
>
> I'll forward this to our team who handles partnerships — they'll be in touch with our rate card and available options.
>
> Best,
> Ink 🖋️

(Then notify Gabriel)

### 3. Media / Press (Interviews, Quotes, Features)
**Signal:** "journalist", "interview", "article", "feature", "quote", "publication", "press"
**Handling:** DRAFT → ALERT GABRIEL before sending
**Template:**
> Hi [Name],
>
> Thanks for reaching out! I'd be happy to help with your piece. Let me know your deadline and specific questions, and I'll coordinate getting you what you need.
>
> Best,
> Ink 🖋️
> The Shopper's Verdict

(Then notify Gabriel with the details)

### 4. Corrections / Factual Errors
**Signal:** "error", "mistake", "incorrect", "wrong", "correction", "factual"
**Handling:** INVESTIGATE → CORRECT → REPLY → ALERT GABRIEL
**Process:**
1. Verify the claim by checking the actual Amazon listing
2. If valid error, fix the review and reply
3. If not valid, politely explain

**Template (valid error):**
> Hi [Name],
>
> Thank you for bringing this to our attention. You're right — we've reviewed the listing and corrected the information in our article. We appreciate your help keeping our reviews accurate.
>
> Best,
> Ink 🖋️
> The Shopper's Verdict

**Template (not an error):**
> Hi [Name],
>
> Thanks for your note. We've double-checked our review against the current Amazon listing and our information appears to be accurate based on the product data available. If there's something specific you'd like us to look into further, please let us know.
>
> Best,
> Ink 🖋️
> The Shopper's Verdict

### 5. Reader Questions (About Reviewed Products)
**Signal:** "I bought", "your review of [product]", "should I buy", "question about"
**Handling:** SILENT IGNORE — do not reply
> These would overwhelm us. Do not respond.

### 6. Unclassifiable / Unexpected
**Signal:** Doesn't fit any category above
**Handling:** ALERT GABRIEL
**Template:**
> Hi [Name],
>
> Thanks for your message. I want to make sure this gets to the right person on our team — I'll have someone review it and get back to you.
>
> Best,
> Ink 🖋️
> The Shopper's Verdict

Then notify Gabriel.

---

## Alert Rules
**Alert Gabriel (Telegram DM) when:**
- ✅ Sponsored post inquiry (rate card request)
- ✅ Media/press request
- ✅ Correction that requires a review update
- ✅ Unclassifiable emails
- ⛔ Do NOT alert for: routine review collaboration requests (handle silently)

**Format for alerts:**
```
📬 [CATEGORY] — [Sender Name/Email]
Subject: [Subject]
Brief: [1-2 line summary]
Action: [What I've done / what's needed from you]
```
