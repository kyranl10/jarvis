# Jarvis

Kyran's personal assistant. Every few minutes it gathers the day's calendar (UNC, work, Canvas, Marching
Tar Heels), weather, flagged email, PMA announcements, scores and internship leads, then refreshes the
HUD and the spoken morning briefing.

**Cost: $0.** Weather (Open-Meteo), notifications (ntfy), the refresh loop (GitHub Actions) and the
HUD (GitHub Pages) are all free.

```
calendars (ICS links) ──┐
Open-Meteo weather ─────┤
Gmail "Jarvis" label ───┼─> jarvis.briefing ─> private ntfy topics ─> HUD (kyranl10/jarvis-hud) + iPhone alarm
Discord, ESPN, Meta ────┤
data/mail.enc ──────────┘   (mail triage, written by a scheduled Claude task)
```

## This repo is public

Anyone can read this repo and its history, so nothing private goes in it:
- Links, tokens and passwords live only in GitHub Actions secrets (and your local `.env`).
- The mail triage's results are encrypted in `data/mail.enc`. The key is the `MAIL_KEY` secret;
  `python -m jarvis.mailstore show` prints the contents if you have it.
- The run log prints status lines only, never the briefing or feed URLs.
- Everything the HUD shows travels through ntfy topics named after `NTFY_TOPIC`, so that name is
  the one thing protecting your data. Treat it like a password.

## Setup (about 15 minutes, Windows)

### 1. Get the code running locally
In the Anaconda Prompt (or PowerShell with Python 3.12+):

```powershell
cd C:\Users\klak\Projects\jarvis
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Open `.env` in any editor. You'll fill it in over the next steps.

### 2. Notifications on your iPhone
1. Install **ntfy** from the App Store (free).
2. Make up a long topic name nobody could guess, like `jarvis-q7m2x9vk4p`.
   Anyone who knows it can read your briefings, so treat it like a password.
3. In the app, tap **+** and subscribe to that topic. Put the same name in `NTFY_TOPIC`.

### 3. Outlook calendar link
A school Microsoft 365 account usually blocks outside apps from signing in to your calendar, so
Jarvis reads a published, read-only link instead.

1. Go to https://outlook.office.com > Settings (gear) > Calendar > Shared calendars.
2. Under "Publish a calendar", pick your calendar and "Can view all details", then Publish.
3. Copy the **ICS** link (not HTML) into `OUTLOOK_ICS_URL`.

Anyone with this link can see your calendar, so keep it private.
If the "Publish a calendar" section is missing, your school has turned it off. Tell Claude and
we'll switch to a workaround.

Try it without sending anything, then for real:
```powershell
python -m jarvis.briefing --dry-run
python -m jarvis.briefing
```

### Work calendar and messages (VenueHorn)
1. In Outlook on the web, signed in to your work account: Settings > Calendar > Shared calendars >
   Publish a calendar > "Can view all details" > Publish. Save the **ICS** link as the GitHub secret
   `WORK_ICS_URL`. Work events show up labelled "VenueHorn:". Keep the link private.
2. Still in work Outlook: Settings > Mail > Rules > Add new rule. Condition: **Apply to all messages**.
   Action: **Redirect to** your Gmail address. Redirect keeps the original sender, so Teams
   notifications read as "LevinW on VenueHorn Teams wrote: ...". If you get an "external forwarding
   is blocked" bounce, VenueHorn's admin has turned it off; the calendar still works.
3. In Gmail, create a filter for `to:(@venuehorn.com)`: Skip the Inbox, Apply the label: Jarvis.

### 4. Make it run every morning
1. Move the schedule file into place (from the jarvis folder):
   `mkdir .github\workflows; move morning.yml .github\workflows\`
2. Push this folder to GitHub (`.env` is ignored, so your secrets stay local). The repo is public
   so Actions minutes are free; see "This repo is public" above.
3. Repo > Settings > Secrets and variables > Actions > New repository secret.
   Add `NTFY_TOPIC`, `OUTLOOK_ICS_URL`, `MAIL_KEY` and the others named in `.github/workflows/morning.yml`.
4. Actions tab > Jarvis refresh > Run workflow, to test it (manual runs send a notification).

Scheduled runs start `jarvis.loop`, which refreshes every 15 minutes (and right away when the HUD's
Sync button is tapped) for about 5.6 hours, then starts its successor. No push notification is sent;
the iPhone alarm reads the briefing whenever you wake up.

## Development
```powershell
pip install pytest
python -m pytest
```
