# Cloudflare Tunnel + Access — step by step (assume you've never done this)

Goal: reach the dashboard at a real address like `https://studio.example.com` that ONLY YOU can
open, with no port exposed on the server. We use a **named Cloudflare Tunnel** (a persistent
outbound connection from the VPS to Cloudflare — nothing inbound to open) and **Cloudflare Access**
(a login wall in front, emailed one-time PIN). A second path `/term/` reaches the web terminal (ttyd).

You need: a domain on Cloudflare (free plan is fine). If you don't have one, register/move one to
Cloudflare first (Dashboard → add a site → follow the nameserver steps).

---

## A. Install cloudflared on the VPS
```
curl -fsSL https://pkg.cloudflare.com/cloudflared/install.sh | sudo bash   # or: sudo apt install cloudflared
cloudflared --version
```

## B. Log cloudflared into your Cloudflare account
```
cloudflared tunnel login
```
This prints a URL — open it in your browser, pick your domain, click Authorize. It saves a
certificate to `~/.cloudflared/`.

## C. Create the named tunnel
```
cloudflared tunnel create web-studio
```
Note the **Tunnel ID** it prints and the credentials file path (`~/.cloudflared/<ID>.json`).

## D. Tell the tunnel what to route — `~/.cloudflared/config.yml`
Create that file (replace the ID, the hostname, and the credentials path):
```yaml
tunnel: <TUNNEL-ID>
credentials-file: /home/studio/.cloudflared/<TUNNEL-ID>.json

ingress:
  # The web terminal (ttyd) — must come BEFORE the catch-all
  - hostname: studio.example.com
    path: ^/term/?.*
    service: http://127.0.0.1:7681
  # The dashboard
  - hostname: studio.example.com
    service: http://127.0.0.1:8788
  # Required final catch-all
  - service: http_status:404
```
(8788 = studio.py; 7681 = ttyd default port. Set `STUDIO_TTYD_URL=https://studio.example.com/term/`
in `/etc/web-studio/studio.env` so the dashboard's "Open session" button links there.)

## E. Give the hostname a DNS record (one command)
```
cloudflared tunnel route dns web-studio studio.example.com
```

## F. Run the tunnel as a service (starts on boot)
```
sudo cloudflared service install
sudo systemctl enable --now cloudflared
```

## G. Run ttyd (also as a service) — bound to localhost, behind the tunnel
Create `/etc/systemd/system/ttyd.service`:
```ini
[Unit]
Description=ttyd web terminal
After=network-online.target
[Service]
User=studio
# -i 127.0.0.1 keeps it local; the tunnel + Access are the only way in.
# Drop -W if you want a read-only terminal.
ExecStart=/usr/bin/ttyd -i 127.0.0.1 -p 7681 -W -b /term bash
Restart=on-failure
[Install]
WantedBy=multi-user.target
```
```
sudo systemctl enable --now ttyd
```

---

## H. Put Cloudflare Access (the login wall) in front
Without this, anyone who learns the hostname can reach it. Access fixes that.

1. In the Cloudflare dashboard go to **Zero Trust** (one-time: pick the free plan, it asks for a
   team name like `your-name`).
2. **Access → Applications → Add an application → Self-hosted.**
3. Application name: `Web Studio`. **Application domain:** `studio.example.com` (leave path blank so
   it covers the dashboard AND `/term/`).
4. **Add a policy:**
   - Policy name: `me-only`
   - Action: **Allow**
   - Include → **Emails** → add your email address (allowlist).
5. **Authentication / login methods:** enable **One-time PIN** (this is the emailed-code login —
   no extra identity provider needed).
6. Save. Session duration: 24h is reasonable.

Now visiting `https://studio.example.com` shows a Cloudflare login → you enter your email → you get
a 6-digit PIN by email → you're in. Anyone else is blocked.

> Note: studio.py still has its own `STUDIO_TOKEN`. With Access in front you may open it once as
> `https://studio.example.com/?key=<token>` (cookie remembers it). Access is the real gate; the
> token is defense-in-depth.

---

## Verify
- `https://studio.example.com` → Cloudflare PIN login → dashboard loads.
- `https://studio.example.com/term/` → (after PIN) a terminal in the browser.
- From a different browser/incognito with a non-allowlisted email → blocked at Access.
- On the VPS, `sudo ufw status` shows only OpenSSH — no 8788/7681 exposed.
