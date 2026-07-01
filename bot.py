"""
Discord bot that controls a Tuya / Cozylady Wi-Fi LED strip via the Tuya Cloud API.

Slash command:
    /light  power:<on|off>  color:<name>  brightness:<1-100>
    /lightinfo   -> dumps the device's real status + supported codes (for troubleshooting)

All three arguments to /light are optional and can be combined, e.g.
    /light power:on color:blue brightness:75
"""

import os
import json
import asyncio
from typing import Optional

import discord
from discord import app_commands
import tinytuya
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Config (from .env)
# ---------------------------------------------------------------------------
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("DISCORD_GUILD_ID")  # optional: makes /commands appear instantly in one server

TUYA_REGION = os.getenv("TUYA_REGION", "us")       # us / eu / cn / in
TUYA_CLIENT_ID = os.getenv("TUYA_CLIENT_ID")
TUYA_CLIENT_SECRET = os.getenv("TUYA_CLIENT_SECRET")
TUYA_DEVICE_ID = os.getenv("TUYA_DEVICE_ID")

_missing = [k for k, v in {
    "DISCORD_TOKEN": DISCORD_TOKEN,
    "TUYA_CLIENT_ID": TUYA_CLIENT_ID,
    "TUYA_CLIENT_SECRET": TUYA_CLIENT_SECRET,
    "TUYA_DEVICE_ID": TUYA_DEVICE_ID,
}.items() if not v]
if _missing:
    raise SystemExit(
        "Missing values in your .env file: " + ", ".join(_missing) +
        "\nOpen the .env file next to this script and fill them in."
    )

# ---------------------------------------------------------------------------
# Tuya cloud connection
# ---------------------------------------------------------------------------
cloud = tinytuya.Cloud(
    apiRegion=TUYA_REGION,
    apiKey=TUYA_CLIENT_ID,
    apiSecret=TUYA_CLIENT_SECRET,
    apiDeviceID=TUYA_DEVICE_ID,
)

# Named colors -> hue (0-360). "white" is special (switches to white mode).
NAMED_COLORS = {
    "red": 0, "orange": 30, "yellow": 60, "green": 120, "cyan": 180,
    "blue": 240, "purple": 280, "magenta": 300, "pink": 330, "white": None,
}


def _send(commands):
    """Send a list of Tuya DP commands. Raise if Tuya rejects them."""
    resp = cloud.sendcommand(TUYA_DEVICE_ID, {"commands": commands})
    if isinstance(resp, dict) and resp.get("success") is False:
        msg = resp.get("msg") or resp.get("errorMsg") or resp
        tried = [c.get("code") for c in commands]
        raise RuntimeError(f"Tuya rejected the command ({msg}); codes tried: {tried}")
    return resp


# ---------------------------------------------------------------------------
# Capability detection: figure out which DP codes/ranges THIS strip supports
# (some strips use colour_data / bright_value with 0-255 ranges instead of the
#  _v2 codes with 0-1000 ranges). Detected once, then cached.
# ---------------------------------------------------------------------------
_caps = None


def _extract_functions(resp):
    if isinstance(resp, dict):
        if isinstance(resp.get("functions"), list):
            return resp["functions"]
        if "result" in resp:
            return _extract_functions(resp["result"])
    return []


def _parse_values(func):
    raw = func.get("values")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            return json.loads(raw)
        except ValueError:
            return {}
    return {}


def _get_caps():
    global _caps
    if _caps is not None:
        return _caps
    caps = {
        "power_code": "switch_led",
        "bright_code": "bright_value_v2", "bright_min": 10, "bright_max": 1000,
        "colour_code": "colour_data_v2", "s_max": 1000, "v_max": 1000,
        "has_work_mode": True,
    }
    try:
        funcs = _extract_functions(cloud.getfunctions(TUYA_DEVICE_ID))
        by_code = {f.get("code"): f for f in funcs if isinstance(f, dict)}
        if by_code:  # only override defaults if we actually learned the codes
            for c in ("switch_led", "switch", "led_switch"):
                if c in by_code:
                    caps["power_code"] = c
                    break
            caps["bright_code"] = None
            for c in ("bright_value_v2", "bright_value"):
                if c in by_code:
                    vals = _parse_values(by_code[c])
                    caps["bright_code"] = c
                    caps["bright_min"] = vals.get("min", 10)
                    caps["bright_max"] = vals.get("max", 1000)
                    break
            caps["colour_code"] = None
            for c in ("colour_data_v2", "colour_data"):
                if c in by_code:
                    vals = _parse_values(by_code[c])
                    caps["colour_code"] = c
                    caps["s_max"] = (vals.get("s") or {}).get("max", 1000)
                    caps["v_max"] = (vals.get("v") or {}).get("max", 1000)
                    break
            caps["has_work_mode"] = "work_mode" in by_code
    except Exception as e:
        print(f"[warn] could not read device capabilities, using defaults: {e}")
    _caps = caps
    print(f"[info] using device codes: {caps}")
    return caps


def _status_map():
    """Return the device's current status as {code: value}."""
    resp = cloud.getstatus(TUYA_DEVICE_ID)
    items = resp.get("result", []) if isinstance(resp, dict) else []
    return {i.get("code"): i.get("value") for i in items if isinstance(i, dict)}


def _current_hsv(status):
    """Parse the strip's current colour_data (a JSON string) into an h/s/v dict."""
    raw = status.get(_get_caps()["colour_code"])
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            raw = {}
    return raw if isinstance(raw, dict) else {}


def set_power(on: bool):
    caps = _get_caps()
    return _send([{"code": caps["power_code"], "value": bool(on)}])


def set_brightness(pct: int):
    caps = _get_caps()
    pct = max(1, min(100, int(pct)))
    try:
        status = _status_map()
    except Exception:
        status = {}
    cmds = [{"code": caps["power_code"], "value": True}]
    # In colour mode the strip ignores bright_value — brightness is the "v"
    # (value) channel inside colour_data. Adjust the right one for the mode.
    if status.get("work_mode") == "colour" and caps["colour_code"]:
        hsv = _current_hsv(status)
        h = int(hsv.get("h", 0))
        s = int(hsv.get("s", caps["s_max"]))
        v = int(round((pct / 100) * caps["v_max"]))
        cmds.append({"code": caps["colour_code"],
                     "value": json.dumps({"h": h, "s": s, "v": v})})
    elif caps["bright_code"]:
        lo, hi = caps["bright_min"], caps["bright_max"]
        cmds.append({"code": caps["bright_code"],
                     "value": int(lo + (pct / 100) * (hi - lo))})
    return _send(cmds)


def set_color(name: str):
    caps = _get_caps()
    name = name.lower()
    cmds = [{"code": caps["power_code"], "value": True}]
    if name == "white":
        if caps["has_work_mode"]:
            cmds.append({"code": "work_mode", "value": "white"})
        return _send(cmds)
    hue = NAMED_COLORS.get(name)
    if hue is None:
        return None
    if not caps["colour_code"]:
        raise RuntimeError("This strip reports no colour_data code — it may be white-only.")
    # Preserve the current brightness (v) when only changing color.
    v = caps["v_max"]
    try:
        cur = _current_hsv(_status_map())
        if cur.get("v"):
            v = int(cur["v"])
    except Exception:
        pass
    if caps["has_work_mode"]:
        cmds.append({"code": "work_mode", "value": "colour"})
    # colour_data is a Json DP: its value must be a JSON *string*, not an object.
    cmds.append({
        "code": caps["colour_code"],
        "value": json.dumps({"h": hue, "s": caps["s_max"], "v": v}),
    })
    return _send(cmds)


# ---------------------------------------------------------------------------
# Discord client
# ---------------------------------------------------------------------------
intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


@client.event
async def on_ready():
    if GUILD_ID:
        guild = discord.Object(id=int(GUILD_ID))
        tree.copy_global_to(guild=guild)
        await tree.sync(guild=guild)
    else:
        await tree.sync()  # global sync can take up to ~1 hour to appear
    print(f"Logged in as {client.user}. Slash commands synced.")


@tree.command(name="light", description="Control the LED strip")
@app_commands.describe(
    power="Turn the lights on or off",
    color="Set a color",
    brightness="Set brightness (1-100)",
)
@app_commands.choices(
    power=[
        app_commands.Choice(name="on", value="on"),
        app_commands.Choice(name="off", value="off"),
    ],
    color=[app_commands.Choice(name=c, value=c) for c in NAMED_COLORS],
)
async def light(
    interaction: discord.Interaction,
    power: Optional[app_commands.Choice[str]] = None,
    color: Optional[app_commands.Choice[str]] = None,
    brightness: Optional[int] = None,
):
    await interaction.response.defer(thinking=True)
    done = []
    try:
        # Power off first if requested alone; otherwise other actions imply "on".
        if power is not None:
            await asyncio.to_thread(set_power, power.value == "on")
            done.append(f"power **{power.value}**")
        if color is not None:
            await asyncio.to_thread(set_color, color.value)
            done.append(f"color **{color.value}**")
        if brightness is not None:
            await asyncio.to_thread(set_brightness, brightness)
            done.append(f"brightness **{max(1, min(100, brightness))}%**")

        if not done:
            await interaction.followup.send(
                "Give me something to do — set `power`, `color`, and/or `brightness`."
            )
            return

        await interaction.followup.send("💡 Set " + ", ".join(done) + ".")
    except Exception as e:
        await interaction.followup.send(f"⚠️ Error talking to the light: `{e}`")


@tree.command(name="lightinfo", description="Show the light's real status + supported codes (troubleshooting)")
async def lightinfo(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    try:
        status = await asyncio.to_thread(cloud.getstatus, TUYA_DEVICE_ID)
        functions = await asyncio.to_thread(cloud.getfunctions, TUYA_DEVICE_ID)
        msg = f"**Status:**\n```{status}```\n**Supported functions:**\n```{functions}```"
        await interaction.followup.send(msg[:1990])
    except Exception as e:
        await interaction.followup.send(f"⚠️ Error: `{e}`")


if __name__ == "__main__":
    client.run(DISCORD_TOKEN)
