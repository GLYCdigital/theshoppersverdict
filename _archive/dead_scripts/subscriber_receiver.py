#!/usr/bin/env python3
"""
Subscriber receiver — lightweight HTTP endpoint for newsletter signups.
Receives POST from Cloudflare Pages Function (subscribe.js),
appends email to subscribers.json.

Launched via launchd alongside gateway. Listens on 127.0.0.1:9877
"""

import http.server
import json
import os
import re
import sys

WORKSPACE = os.path.expanduser("~/.openclaw/workspace")
SUBS_FILE = os.path.join(WORKSPACE, "theshoppersverdict/data/subscribers.json")
PORT = 9877

def save_subscriber(email):
    """Append email to subscribers.json if not already present."""
    os.makedirs(os.path.dirname(SUBS_FILE), exist_ok=True)
    
    subscribers = []
    if os.path.exists(SUBS_FILE):
        try:
            with open(SUBS_FILE) as f:
                data = json.load(f)
                if isinstance(data, dict) and "subscribers" in data:
                    subscribers = data["subscribers"]
                elif isinstance(data, list):
                    subscribers = data
        except (json.JSONDecodeError, Exception):
            subscribers = []
    
    if email not in subscribers:
        subscribers.append(email)
    
    with open(SUBS_FILE, "w") as f:
        json.dump({"subscribers": subscribers}, f, indent=2)
    
    return len(subscribers)

class SubscriberHandler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8")
        
        # Parse form data or JSON
        email = None
        if self.headers.get("Content-Type", "").startswith("application/json"):
            try:
                data = json.loads(body)
                email = data.get("email", "").strip().lower()
            except json.JSONDecodeError:
                pass
        else:
            # Form-encoded
            import urllib.parse
            params = urllib.parse.parse_qs(body)
            email = params.get("email", [""])[0].strip().lower()
        
        if not email or not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Invalid email"}).encode())
            return
        
        total = save_subscriber(email)
        
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({
            "status": "ok",
            "email": email,
            "total_subscribers": total
        }).encode())
    
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(f"Newsletter subscriber receiver running. POST emails to subscribe.\n".encode())
    
    def log_message(self, format, *args):
        """Squelch default HTTP server logging."""
        pass

def main():
    server = http.server.HTTPServer(("127.0.0.1", PORT), SubscriberHandler)
    print(f"📬 Subscriber receiver listening on http://127.0.0.1:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()

if __name__ == "__main__":
    main()
