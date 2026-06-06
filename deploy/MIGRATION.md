# Web Studio — Cloud Migration Runbook

Move the studio from your Mac to an always-on Linux VPS. After this, your Mac is just a browser:
you open the dashboard over the internet, click into a session, and drive Claude Code on the box.

Estimated time: ~45–60 min, most of it waiting on `setup.sh` and DNS.

---

## 0. What you're renting — recommendation & cost
This workload = Node/Astro builds + Claude Code + scraping (wget mirrors get large) + a tiny web
dashboard. It wants **~4 GB RAM, 2 vCPU, and 80 GB disk** (mirrors are hundreds of MB each).

- **Recommended: Hetzner Cloud CPX21** — 3 vCPU / 4 GB / 80 GB NVMe — **≈ $8–9/month.** Best value;
  Ubuntu 24.04 image; add their backups for ~20% if you want belt-and-suspenders.
  (CX22, 2 vCPU / 4 GB / 40 GB, ≈ $5/mo, also works if you keep few clients.)
- Alternatives: DigitalOcean / Linode "4 GB / 2 vCPU" droplet ≈ **$24/month** (pricier, very polished).
- Plus object storage for backups: **Backblaze B2** ≈ $6/TB/month — your data is GBs, so effectively
  a dollar or two. **All-in: ~$10/month.**

Pick Ubuntu 24.04 LTS. Add your SSH public key during creation. Note the server's IP.

---

## 1. First SSH in + create the box's identity
```
ssh root@<SERVER_IP>
```
(If you didn't add an SSH key at creation, do so now — password SSH gets disabled in step 2.)

## 2. Run the bootstrap (installs everything, creates the `studio` user, hardens)
Copy your public key into the command so the `studio` user can log in:
```
sudo REPO_URL=<your-repo-url> \
     ADMIN_SSH_KEY="$(cat ~/.ssh/id_ed25519.pub)" \
     bash setup.sh
```
(Get `setup.sh` onto the box first: `scp deploy/setup.sh root@<IP>:` or clone the repo and run
`deploy/setup.sh`.) It is idempotent — re-run any time. When done it has: Python+Node+git, wrangler,
Claude Code CLI, ttyd, the repo at `/home/studio/web-studio`, ufw (SSH only), SSH-keys-only, and the
`studio` systemd service installed-but-not-started.

## 3. The two one-time interactive logins (as the `studio` user)
```
ssh studio@<SERVER_IP>
claude            # sign in to Claude Code (follow the prompt / paste the auth)
wrangler login    # opens a URL — paste it into your browser, authorize Cloudflare
```
These can't be scripted (they're interactive auth) — this is the one hands-on part.

## 4. Put it on the internet safely — tunnel + Access
Follow **deploy/tunnel-setup.md** end to end: named Cloudflare Tunnel maps
`https://studio.<yourdomain>` → the dashboard and `…/term/` → ttyd, with **Cloudflare Access**
(email allowlist + one-time PIN) as the login wall. No server port is ever exposed.
Then set `STUDIO_TTYD_URL` in `/etc/web-studio/studio.env` to `https://studio.<yourdomain>/term/`.

## 5. Start the dashboard
```
sudo systemctl start studio
sudo systemctl status studio     # should be active (running)
```

## 6. Backups
Install restic, create `/etc/web-studio/backup.env` (see the header of **deploy/backup.sh** for the
exact variables — repo, password file, B2/S3 keys), then add the cron line from that file via
`sudo crontab -u studio -e`. Run it once by hand to confirm: `bash deploy/backup.sh`.

---

## Verify checklist (don't call it done until all pass)
- [ ] `https://studio.<yourdomain>` prompts Cloudflare Access → emailed PIN → dashboard loads.
- [ ] The dashboard is reachable **only** via Access (incognito + a non-allowlisted email = blocked;
      `sudo ufw status` shows only OpenSSH; nothing answers on `<IP>:8788`).
- [ ] "Open session" on a client row opens the **ttyd** web terminal (not a Mac Terminal).
- [ ] Start a client / Advance / paste owner answers / Archive all work from the dashboard.
- [ ] In a session: `claude` runs; "Assemble prototype", an edit, and **publish-always** all work —
      a change ends live at its `*.pages.dev` preview URL (publish-always rule).
- [ ] `wrangler pages deploy` succeeds from the box (it did during a publish above).
- [ ] `bash deploy/backup.sh` completed and `restic snapshots` lists a snapshot.

## Mac-decommission note
Once the checklist passes, **the Mac is just a browser.** Nothing studio-specific needs to run on it.
Your local `~/web-studio` becomes an ordinary clone like any other dev checkout — keep it if you like
to hack locally (`git pull` to sync), or delete it; the server is now the source of truth and the
always-on home of the dashboard, the client work, and the backups. Don't run the dashboard in both
places against the same clients — the server is canonical now.
