#!/usr/bin/env python3
"""
Newsletter sender — runs after daily review push at 09:50
Checks RSS feed for new reviews, formats an email, and sends via Migadu SMTP
"""

import smtplib, json, os, re, html
from email.mime.text import MIMEText
from datetime import datetime
from xml.etree import ElementTree
from urllib.request import urlopen

WORKSPACE = os.path.expanduser("~/.openclaw/workspace")
SITE_URL = "https://theshoppersverdict.com"
RSS_URL = f"{SITE_URL}/index.xml"
SUBS_FILE = os.path.join(WORKSPACE, "theshoppersverdict/data/subscribers.json")

SMTP_HOST = "smtp.migadu.com"
SMTP_PORT = 587
SMTP_USER = "gemma@glycdigital.com"
SMTP_PASS = "qeHD2sbVQR8a"

def get_today_reviews():
    """Fetch RSS and extract today's reviews"""
    resp = urlopen(RSS_URL, timeout=15)
    tree = ElementTree.parse(resp)
    root = tree.getroot()
    
    today = datetime.now().strftime("%Y-%m-%d")
    reviews = []
    
    for item in root.findall(".//item"):
        pubdate = item.findtext("pubDate", "")
        # Parse date — RSS uses format like "Tue, 12 May 2026 00:00:00 +0000"
        match = re.search(r'\d{2} \w{3} \d{4}', pubdate)
        if match:
            from datetime import datetime as dt
            date_str = match.group()
            pub_date = dt.strptime(date_str, "%d %b %Y").strftime("%Y-%m-%d")
            if pub_date == today:
                title = item.findtext("title", "Untitled")
                link = item.findtext("link", "#")
                desc = item.findtext("description", "")
                desc = re.sub(r'<[^>]+>', '', desc)[:200]
                reviews.append({"title": title, "link": link, "desc": desc})
    
    return reviews

def load_subscribers():
    """Load subscriber emails"""
    if not os.path.exists(SUBS_FILE):
        return []
    with open(SUBS_FILE) as f:
        data = json.load(f)
    return data.get("subscribers", [])

def build_email(reviews):
    """Build HTML email"""
    site_name = "The Shopper's Verdict"
    date_str = datetime.now().strftime("%B %d, %Y")
    
    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,sans-serif;background:#f5f5f5;padding:24px;margin:0;">
<div style="max-width:600px;margin:0 auto;background:white;border-radius:8px;overflow:hidden;">
<div style="background:#1B1B2F;padding:24px;text-align:center;">
<h1 style="color:#C9A84C;margin:0;font-size:20px;">{site_name}</h1>
<p style="color:#aaa;margin:8px 0 0;font-size:13px;">New Reviews — {date_str}</p>
</div>
<div style="padding:24px;">
<p style="color:#333;font-size:15px;line-height:1.5;">Here are today's new reviews from The Shopper's Verdict. We analyze thousands of Amazon customer reviews so you can buy with confidence.</p>
<hr style="border:none;border-top:1px solid #eee;margin:20px 0;">
"""
    for review in reviews:
        html += f"""
<div style="margin-bottom:20px;padding:16px;background:#FAFAFA;border-radius:6px;border-left:3px solid #C9A84C;">
<h3 style="margin:0 0 6px;font-size:16px;"><a href="{review['link']}" style="color:#1B1B2F;text-decoration:none;">{html.escape(review['title'])}</a></h3>
<p style="margin:0;color:#666;font-size:13px;line-height:1.4;">{html.escape(review['desc'])}</p>
</div>"""

    html += f"""
<hr style="border:none;border-top:1px solid #eee;margin:20px 0;">
<div style="text-align:center;padding:16px;">
<a href="{SITE_URL}" style="display:inline-block;background:#C9A84C;color:#1B1B2F;padding:10px 24px;border-radius:4px;text-decoration:none;font-weight:600;font-size:14px;">Browse All Reviews →</a>
</div>
<p style="font-size:11px;color:#999;text-align:center;margin-top:20px;">
You're receiving this because you subscribed to {site_name}.<br>
<a href="{SITE_URL}/unsubscribe" style="color:#999;">Unsubscribe</a>
</p>
</div></div></body></html>"""
    return html

def send_newsletter(html_body, subscribers):
    """Send via Migadu SMTP"""
    if not subscribers:
        print("No subscribers to send to")
        return
    
    msg = MIMEText(html_body, "html")
    msg["Subject"] = f"New Reviews Today — The Shopper's Verdict"
    msg["From"] = "newsletter@theshoppersverdict.com"
    msg["To"] = subscribers[0]  # BCC all others
    
    try:
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(msg["From"], subscribers, msg.as_string())
        server.quit()
        print(f"✅ Newsletter sent to {len(subscribers)} subscribers")
    except Exception as e:
        print(f"❌ Failed: {e}")

def main():
    print(f"[NEWSLETTER] {datetime.now().strftime('%H:%M')} — checking for new reviews")
    
    reviews = get_today_reviews()
    if not reviews:
        print("No new reviews today — skipping newsletter")
        return
    
    print(f"Found {len(reviews)} new reviews")
    subscribers = load_subscribers()
    print(f"Loaded {len(subscribers)} subscribers")
    
    html = build_email(reviews)
    send_newsletter(html, subscribers)

if __name__ == "__main__":
    main()
