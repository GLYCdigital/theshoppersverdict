#!/usr/bin/env python3
"""
imap_email_monitor.py — Polls contact@theshoppersverdict.com via IMAP.

Checks for unread emails every 30 min (via cron).
When new email found: logs it, notifies Ink via Telegram, stores for processing.

Usage (cron every 30 min):
  python3 scripts/imap_email_monitor.py

Reply to an email:
  python3 scripts/imap_email_monitor.py --reply <msg_id> "Your reply text"
"""

import sys, os, json, configparser, email, email.utils
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CREDENTIALS = os.path.join(WORKSPACE, ".email_credentials.cfg")
INBOX_TRACK = os.path.join(WORKSPACE, "data", "email_inbox.json")
REPLY_DIR = os.path.join(WORKSPACE, "data", "email_replies")

def load_config():
    cfg = configparser.ConfigParser()
    cfg.read(CREDENTIALS)
    return cfg

def check_inbox():
    """Connect to IMAP, find unseen messages, return list of email dicts."""
    import imaplib
    
    cfg = load_config()
    imap_cfg = cfg['imap']
    
    try:
        if imap_cfg.getboolean('use_ssl'):
            conn = imaplib.IMAP4_SSL(imap_cfg['host'], imap_cfg.getint('port'))
        else:
            conn = imaplib.IMAP4(imap_cfg['host'], imap_cfg.getint('port'))
        
        conn.login(imap_cfg['username'], imap_cfg['password'])
        conn.select('INBOX')
        
        status, messages = conn.search(None, 'UNSEEN')
        if status != 'OK':
            conn.logout()
            return []
        
        msg_ids = messages[0].split() if messages[0] else []
        emails = []
        
        for mid in msg_ids[-5:]:  # max 5 per check to avoid flooding
            status, data = conn.fetch(mid, '(RFC822)')
            if status != 'OK':
                continue
            
            raw = email.message_from_bytes(data[0][1])
            
            # Parse email
            msg = {
                'msg_id': str(mid, 'utf-8') if isinstance(mid, bytes) else str(mid),
                'from': raw.get('From', ''),
                'subject': raw.get('Subject', '(No subject)'),
                'date': raw.get('Date', ''),
                'body': '',
                'has_attachments': False,
            }
            
            # Extract body
            if raw.is_multipart():
                for part in raw.walk():
                    ctype = part.get_content_type()
                    if ctype == 'text/plain':
                        try:
                            payload = part.get_payload(decode=True)
                            if payload:
                                msg['body'] = payload.decode('utf-8', errors='replace')[:2000]
                        except:
                            pass
                        break
                    elif ctype == 'text/html' and not msg['body']:
                        msg['body'] = '(HTML content — check inbox)'
            else:
                try:
                    payload = raw.get_payload(decode=True)
                    if payload:
                        msg['body'] = payload.decode('utf-8', errors='replace')[:2000]
                except:
                    pass
            
            # Track attachments
            if raw.is_multipart():
                for part in raw.walk():
                    if part.get_content_maintype() == 'multipart':
                        continue
                    if part.get('Content-Disposition') and 'attachment' in part.get('Content-Disposition'):
                        msg['has_attachments'] = True
                        break
            
            emails.append(msg)
        
        conn.logout()
        return emails
    
    except Exception as e:
        print(f"❌ IMAP error: {e}", flush=True)
        return []

def load_tracked():
    if os.path.exists(INBOX_TRACK):
        with open(INBOX_TRACK) as f:
            return json.load(f)
    return {'seen_ids': [], 'pending': []}

def save_tracked(data):
    os.makedirs(os.path.dirname(INBOX_TRACK), exist_ok=True)
    with open(INBOX_TRACK, 'w') as f:
        json.dump(data, f, indent=2)

def send_email(to, subject, body, reply_to_msg_id=None):
    """Send an email via SMTP."""
    import smtplib
    from email.mime.text import MIMEText
    
    cfg = load_config()
    smtp_cfg = cfg['smtp']
    
    msg = MIMEText(body, 'plain', 'utf-8')
    msg['From'] = smtp_cfg['username']
    msg['To'] = to
    msg['Subject'] = subject
    
    try:
        if smtp_cfg.getboolean('use_ssl'):
            conn = smtplib.SMTP_SSL(smtp_cfg['host'], smtp_cfg.getint('port'))
        else:
            conn = smtplib.SMTP(smtp_cfg['host'], smtp_cfg.getint('port'))
            conn.starttls()
        
        conn.login(smtp_cfg['username'], smtp_cfg['password'])
        conn.send_message(msg)
        conn.quit()
        return True
    except Exception as e:
        print(f"❌ SMTP error: {e}", flush=True)
        return False


def main():
    print(f"[{datetime.now().strftime('%H:%M SGT')}] Checking inbox...", flush=True)
    
    # ── Reply mode ──
    if len(sys.argv) > 2 and sys.argv[1] == '--reply':
        msg_id = sys.argv[2]
        reply_text = sys.argv[3] if len(sys.argv) > 3 else ''
        if not reply_text:
            # Read from stdin
            reply_text = sys.stdin.read().strip()
        
        # Load original email to get the reply-to address
        tracked = load_tracked()
        pending = [p for p in tracked.get('pending', []) if p['msg_id'] == msg_id]
        
        if pending:
            original = pending[0]
            to_addr = email.utils.parseaddr(original['from'])[1]
            subject = f"Re: {original['subject']}"
            
            if send_email(to_addr, subject, reply_text):
                print(f"✅ Reply sent to {to_addr} re: {original['subject'][:50]}", flush=True)
                # Move from pending to seen
                tracked['seen_ids'].append(msg_id)
                tracked['pending'] = [p for p in tracked['pending'] if p['msg_id'] != msg_id]
                save_tracked(tracked)
                return True
            else:
                print(f"❌ Failed to send reply", flush=True)
                return False
        else:
            print(f"❌ Email {msg_id} not found in pending", flush=True)
            return False
    
    # ── Check mode ──
    emails = check_inbox()
    tracked = load_tracked()
    new_emails = [e for e in emails if e['msg_id'] not in tracked.get('seen_ids', [])]
    
    if not new_emails:
        print(f"  No new emails.", flush=True)
        return
    
    print(f"  📬 {len(new_emails)} new email(s):", flush=True)
    for msg in new_emails:
        print(f"  ── {msg['subject'][:80]}", flush=True)
        print(f"      From: {msg['from'][:60]}", flush=True)
        print(f"      Body: {msg['body'][:100]}", flush=True)
        tracked['pending'].append({
            'msg_id': msg['msg_id'],
            'from': msg['from'],
            'subject': msg['subject'],
            'date': msg['date'],
            'body': msg['body'][:2000],
        })
    
    # Mark as seen so we don't reprocess
    for msg in new_emails:
        tracked['seen_ids'].append(msg['msg_id'])
    
    save_tracked(tracked)
    print(f"  Stored {len(new_emails)} emails for processing.", flush=True)
    
    # Write pending emails to a summary file for the agent to see
    pending_summary = os.path.join(WORKSPACE, "data", "pending_emails.md")
    with open(pending_summary, 'w') as f:
        f.write("# 📬 Pending Emails\n\n")
        for p in tracked['pending']:
            f.write(f"## From: {p['from']}\n")
            f.write(f"**Subject:** {p['subject']}\n")
            f.write(f"**Date:** {p['date']}\n")
            f.write(f"**Msg ID:** {p['msg_id']}\n\n")
            f.write(f"**Body:**\n{p['body']}\n\n---\n\n")


if __name__ == "__main__":
    main()
