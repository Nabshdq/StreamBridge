# Setting up Twitch

*Bahasa Indonesia: [setup-twitch.id.md](setup-twitch.id.md)*

StreamBridge posts your TikTok viewers' messages into your Twitch chat.
You only need your Twitch account. You never type your Twitch password into
StreamBridge: you approve StreamBridge on Twitch's own website instead.

## 1. Log in with your Twitch account (recommended)

By default, messages are sent **as your own channel account**.

1. In StreamBridge, choose **Log in with Twitch**.
2. StreamBridge shows a short code (for example `ABCD-EFGH`) and opens
   `twitch.tv/activate` in your browser.
3. Check that the code on the Twitch page matches, then click **Authorize**.
4. StreamBridge says "Logged in as @yourname". Done.

The login is remembered. You only log in again if you have not used
StreamBridge for 30 days, if you change your Twitch password, or if you
disconnect StreamBridge on Twitch.

## 2. Using a separate bot account (advanced)

Some streamers prefer messages to come from a second account, for example
`yourname_bot`. This is optional.

**The bot must be a moderator of your channel.** StreamBridge checks this every
time you press Start and will not start Twitch until it is.

1. **Create the bot account** on Twitch (log out first, or use a private
   browser window), and give it a clear name such as `yourname_bot`.
2. **Make it a moderator** of your channel. Either:
   - type `/mod yourname_bot` in your own Twitch chat, or
   - go to **Creator Dashboard → Community → Roles**, click **Add New**,
     choose **Moderator** and enter the bot's name.
3. **Log in as the bot** in StreamBridge (**Use a separate bot account**).
   ⚠️ When the Twitch page opens, make sure you are logged in **as the bot**
   in that browser, not as your main account. If needed, open the link in a
   private window and log in with the bot there.
4. Enter **your channel name** (where the bot should post).
5. StreamBridge checks that the bot is a moderator. If it is not, you will see:
   *"The bot @yourname_bot is not a moderator of channel yourname. Type
   /mod yourname_bot in your Twitch chat, then try again."*

To check the moderator list yourself, type `/mods` in your chat, or look in
Creator Dashboard → Community → Roles.

## Troubleshooting

| You see | What to do |
|---|---|
| "Twitch login expired; please log in again" | Log in again (section 1 or 2). |
| "...is not a moderator of channel..." | Make the bot a moderator (section 2, step 2), then Start again. |
| "Twitch does not allow this account to chat here" | The bot lost its moderator role, or the account is banned or timed out in your channel. |
| A message was refused with a reason from Twitch | Twitch's AutoMod or your chat settings blocked that message. Other messages keep flowing. |
| Messages arrive late during busy moments | Twitch allows about 100 messages per 30 seconds. StreamBridge stays below that and never drops Twitch messages, so some may arrive a little late. |

## Privacy and removing access

- Your Twitch login is stored only on your PC, in the **Windows Credential
  Manager**. It is never written to StreamBridge's settings file or logs.
- To remove StreamBridge's access completely, go to
  [twitch.tv/settings/connections](https://www.twitch.tv/settings/connections)
  and click **Disconnect** next to StreamBridge.

## For developers (command line)

```powershell
.\.venv\Scripts\python.exe tools\cli.py --twitch-login        # streamer account
.\.venv\Scripts\python.exe tools\cli.py --twitch-login-bot    # bot account
.\.venv\Scripts\python.exe tools\cli.py --tiktok @username --twitch
.\.venv\Scripts\python.exe tools\cli.py --tiktok @username --twitch --twitch-channel yourname
.\.venv\Scripts\python.exe tools\cli.py --twitch-logout
```
