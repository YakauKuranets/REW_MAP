# Cloudflare Access: protect /admin/* (Map v12)

Goal: keep the public map/CC available (if needed) but restrict admin panel.

## Recommended
- Protect:
  - `/admin/*`
  - `/api/*` (optional, if you want to harden all admin APIs)
  - `/uploads/*` (optional)

- Allow:
  - only your emails/users
  - optionally IP allow-list

## Steps (Cloudflare Dashboard)
1) Zero Trust -> **Access** -> **Applications** -> **Add an application** -> **Self-hosted**.
2) Application domain:
   - Domain: `madcommandcentre.org`
   - Path: `/admin*`
3) Policy:
   - Action: **Allow**
   - Include:
     - Emails: (your admin emails)
     - OR Emails ending in: (your domain)
   - (Optional) Require OTP / WebAuthn / device posture.
4) Add **Deny** policy for everyone else (default).
5) Save.

## Notes
- Admin login cookie will remain, but the request must pass Access first.
- If you protect `/api/*`, ensure Android + Telegram bot are either:
  - routed via a different hostname, or
  - you add a service token, or
  - you only protect `/api/admin/*`.

