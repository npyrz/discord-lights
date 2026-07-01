# discord-lights

A Discord bot that controls your Cozylady / Tuya Wi-Fi LED strip with a `/light` slash command.

```
/light power:on
/light color:blue
/light brightness:75
/light power:on color:purple brightness:50   (combine them)
/lightaccess state:off                        (admin role: lock the lights for everyone else)
/lightinfo                                    (troubleshooting: shows real device codes)
```

## Restricting who can use the lights
Set `LIGHT_ADMIN_ROLE_ID` in `.env` to a Discord role ID. Then:
- Members with that role can **always** control the lights.
- Anyone with that role can run `/lightaccess state:off` to **lock** the lights so
  only the admin role can use `/light`, and `/lightaccess state:on` to unlock them.
- The lock state is remembered across restarts (saved in `state.json`).

To get a role ID: Discord **Settings -> Advanced -> Developer Mode**, then right-click
the role (in Server Settings -> Roles) -> **Copy Role ID**. Leave the variable blank
to let everyone use the lights.

## 1. Install Python + dependencies
Make sure Python 3.9+ is installed (`python --version`). Then in this folder:

```powershell
pip install -r requirements.txt
```

## 2. Create the Discord bot
1. Go to https://discord.com/developers/applications -> **New Application**.
2. Left sidebar -> **Bot** -> **Reset Token** -> copy the token.
3. Paste it into `.env` as `DISCORD_TOKEN`.
4. Left sidebar -> **Installation** (or **OAuth2 -> URL Generator**):
   - Scopes: **bot** and **applications.commands**
   - Bot permissions: **Send Messages**
   - Copy the generated URL, open it, and invite the bot to your server.

## 3. Fill in `.env`
Open `.env` and paste in:
- `DISCORD_TOKEN` – from step 2
- `DISCORD_GUILD_ID` – (optional) your server ID, so commands appear instantly
- `TUYA_CLIENT_ID` / `TUYA_CLIENT_SECRET` / `TUYA_DEVICE_ID` – from your Tuya cloud project
- `TUYA_REGION` – `us` for a Western America data center (default)

## 4. Run it
```powershell
py bot.py
```
Or use the helper script (installs deps, then starts the bot):
```powershell
.\run.ps1        # or double-click run.bat
```
You should see `Logged in as ... Slash commands synced.` Then type `/light` in your server.

## Run with Docker (optional)
Make sure your `.env` is filled in, then:
```bash
docker compose up -d --build      # start in the background
docker compose logs -f            # watch the logs
docker compose down               # stop
```
Or without compose:
```bash
docker build -t discord-lights .
docker run -d --name discord-lights --env-file .env --restart unless-stopped discord-lights
```

## Troubleshooting
- **Command doesn't appear:** set `DISCORD_GUILD_ID` (global sync is slow). Re-run the bot.
- **`/light` runs but the strip doesn't change:** your strip may use different Tuya "DP codes".
  Run `/lightinfo` and send me the output — we'll adjust the codes in `bot.py`
  (e.g. `bright_value_v2` -> `bright_value`, or `colour_data_v2` -> `colour_data`).
- **Auth / region errors:** the Tuya data center in your cloud project must match your Smart Life
  account's region (US = Western America). Fix in iot.tuya.com and update `TUYA_REGION`.
```
