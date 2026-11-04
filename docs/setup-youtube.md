# Setting up YouTube

*Bahasa Indonesia: [setup-youtube.id.md](setup-youtube.id.md)*

StreamBridge posts your TikTok viewers' messages into your YouTube live chat.
Unlike Twitch, YouTube needs a **one-time setup in Google Cloud**. It is free
and takes about 15 minutes. You create your own small "project", so the daily
YouTube limit belongs to you and is not shared with other people.

> The in-app setup wizard for these steps is not built yet. Until it is, use
> this guide as the reference for what the wizard will ask. Google renames
> console pages from time to time (the consent screen now lives under
> **Google Auth Platform**: Branding, Audience, Data Access, Clients), so
> button names may differ slightly. These steps have not been tested end to
> end yet.

## 0. Enable live streaming on your channel first

The first time you enable live streaming, YouTube can take **up to 24 hours**
to switch it on. Your channel must also be verified and must not have a live
streaming restriction from the last 90 days. Do this before anything else:
<https://www.youtube.com/features>

## 1. Create a Google Cloud project

1. Open <https://console.cloud.google.com/> and sign in with the Google
   account that owns your YouTube channel.
2. Click the project picker at the top, then **New project**. Name it
   `StreamBridge` and click **Create**.

## 2. Turn on the YouTube Data API

1. Open **APIs & Services > Library**.
2. Search for **YouTube Data API v3**, open it, and click **Enable**.

## 3. Set up the consent screen

1. Open **Google Auth Platform** (<https://console.cloud.google.com/auth/overview>)
   and start the setup. The older name is **APIs & Services > OAuth consent
   screen**.
2. Choose the user type **External**.
3. Fill in the app name (`StreamBridge`), your email as support email and as
   developer contact. Leave the rest empty. Save.
4. On the **Scopes** step, add `.../auth/youtube.force-ssl`.
5. On the **Test users** step, add your own Google account.
6. **Important:** back on the consent screen page, click **Publish app**.
   While the app is in "Testing", Google logs you out every **7 days** and you
   would have to log in again each week. After publishing it stays logged in.

When you log in, Google may say **"Google hasn't verified this app"**. That is
expected: you built the app yourself and you are its only user. Click
**Advanced**, then **Go to StreamBridge (unsafe)**. Google may keep showing
this warning because the app is not verified; that is fine for personal use
(an unverified app is limited to 100 users).

## 4. Create the login file

1. Open **Google Auth Platform > Clients** (older name: **APIs & Services >
   Credentials**).
2. Click **Create client**.
3. Application type: **Desktop app**. Name: `StreamBridge`. Click **Create**.
4. Download the JSON right away; the secret is shown only once. The file is called `client_secret_....json`.
5. Give this file to StreamBridge when it asks. StreamBridge copies it into
   its own folder. **Never share this file and never upload it anywhere.**

## 5. Log in

Choose **Log in with Google** in StreamBridge. Your browser opens, you approve
the access, and StreamBridge keeps the login in the Windows Credential Manager.

## The daily limit (quota)

YouTube gives each project **10,000 units per day**. Sending one message costs
**20 units**, so at most **500 messages a day**. The count resets at midnight
Pacific Time (about 15:00 in Jakarta, or 14:00 during US summer time).

To stay inside this, StreamBridge:

- joins several chat messages into **one** message (compact mode) and sends
  only the newest chat that fits in 200 characters;
- by default sends chat and gifts to YouTube, but not follows, likes or shares;
- (planned) shows "YouTube quota: used / 10,000" and, above 90%, sends only
  gifts.

With 500 messages a day, a 2 to 3 hour LIVE only fits if chat is batched into
longer windows; StreamBridge is being tuned for this. The chat that does not
fit is counted as "dropped".

## Using a separate bot account (advanced)

Messages normally come from your own channel. To use another account, log in
with that account instead and paste the **link of your live** (for example
`https://www.youtube.com/watch?v=...`) in Settings, because a second account
cannot look up your broadcast by itself.

## Troubleshooting

| Message | What to do |
|---|---|
| "YouTube live chat not found yet" | Your live has not started, or live streaming is not enabled yet (see step 0). StreamBridge keeps checking every minute. |
| "YouTube login expired" | Log in again. This happens weekly if the app was left in "Testing" (step 3.6). |
| "Daily quota is used up" | Wait for the midnight Pacific reset. |
| "This is not a Desktop app client file" | Create the OAuth client with the type **Desktop app** (step 4). |
