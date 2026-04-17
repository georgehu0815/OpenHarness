# Option B — Multiple Telegram Bots on a Single Gateway (Design)

> **Status: Design only — no code changes made.**  
> This document describes the intended architecture and the specific files
> that need to change. Implementation is a separate step.

Run two (or more) Telegram bots inside the single `brain-copilot-usi-demo-app`
Container App. Both bots share the same gateway process, the same session pool,
and the same Azure OpenAI connection.

---

## Motivation vs Option A

| | Option A (two apps) | Option B (one app, two bots) |
|---|---|---|
| Code changes | None | Yes |
| Compute cost | 2× | 1× |
| Shared session memory | No | Yes — bots share the same agent memory |
| Bot A crash affects Bot B | No | Yes (same process) |
| Config complexity | Two separate `az containerapp update` calls | One config file, multiple channel entries |

Choose Option B when you want **both bots to share conversation context and
agent memory** — for example, a user who switches between two bot usernames
should resume the same session.

---

## Architecture

```
Telegram Bot A  ──┐
                  ├──▶  ChannelManager
Telegram Bot B  ──┘         │  (two TelegramChannel instances)
                             ▼
                         MessageBus  (inbound / outbound queues)
                             │
                             ▼
                      OhmoGatewayBridge
                             │
                      SessionRuntimePool  (keyed by channel:chat_id)
                             │
                      OpenHarness Engine → Azure OpenAI
```

Each `TelegramChannel` instance runs its own independent long-poll loop.
They write to the same `bus.inbound` queue and read from the same
`bus.outbound` queue. Session keys incorporate the channel name
(`telegram_a:chat_id` vs `telegram_b:chat_id`), so each bot's conversations
remain isolated unless you intentionally merge the keys.

---

## Changes Required

### 1. `gateway.json` — new multi-channel Telegram config

**Current shape (single bot):**

```json
{
  "channel_configs": {
    "telegram": {
      "token": "BOT_TOKEN_A",
      "allow_from": ["*"],
      "reply_to_message": true
    }
  }
}
```

**Proposed shape (multiple bots):**

```json
{
  "enabled_channels": ["telegram_a", "telegram_b"],
  "channel_configs": {
    "telegram_a": {
      "type": "telegram",
      "token": "BOT_TOKEN_A",
      "allow_from": ["*"],
      "reply_to_message": true
    },
    "telegram_b": {
      "type": "telegram",
      "token": "BOT_TOKEN_B",
      "allow_from": ["123456789"],
      "reply_to_message": true
    }
  }
}
```

The `"type": "telegram"` discriminator tells `ChannelManager` which adapter
class to instantiate, regardless of the key name.

---

### 2. `openharness/channels/impl/telegram.py` — no logic change needed

`TelegramChannel` already takes its token from the config dict passed at
construction. Each instance is independent. **No changes needed here** as long
as `ChannelManager` constructs one instance per config entry.

---

### 3. `openharness/channels/impl/manager.py` — iterate over typed channel entries

**Current behavior:** `ChannelManager._init_channels()` looks for a hardcoded
set of channel keys (`"telegram"`, `"slack"`, `"discord"`, `"feishu"`) in
`channel_configs`.

**Required change:** when a config entry has a `"type"` field, use that to
select the adapter class, and allow multiple entries of the same type.

Pseudocode:

```python
for name, cfg in channel_configs.items():
    adapter_type = cfg.get("type", name)   # fall back to key name for backwards compat
    if adapter_type == "telegram":
        channel = TelegramChannel(name=name, config=cfg, bus=self.bus)
        self._channels[name] = channel
    elif adapter_type == "slack":
        ...
```

This is backwards-compatible: existing configs with `"telegram"` as the key and
no `"type"` field continue to work because `adapter_type` falls back to the key.

---

### 4. `openharness/channels/config.py` (or equivalent config model)

Add a `type` field to the Telegram channel config dataclass / Pydantic model:

```python
@dataclass
class TelegramChannelConfig:
    token: str
    allow_from: list[str] = field(default_factory=lambda: ["*"])
    reply_to_message: bool = True
    type: str = "telegram"   # new — used by ChannelManager discriminator
```

---

### 5. `docker-entrypoint.sh` — multi-token env var convention

The entrypoint currently reads a single `OHMO_TELEGRAM_TOKEN` and writes one
`telegram` entry. For multiple bots, extend the convention:

```bash
# Existing (Bot A — backwards compatible)
OHMO_TELEGRAM_TOKEN=BOT_TOKEN_A

# Bot B
OHMO_TELEGRAM_TOKEN_B=BOT_TOKEN_B
```

Entrypoint logic (pseudocode):

```bash
if [ -n "$OHMO_TELEGRAM_TOKEN" ]; then
    write_channel_entry "telegram_a" "telegram" "$OHMO_TELEGRAM_TOKEN"
fi

# Discover additional tokens: OHMO_TELEGRAM_TOKEN_B, OHMO_TELEGRAM_TOKEN_C, …
for var in $(env | grep '^OHMO_TELEGRAM_TOKEN_' | cut -d= -f1); do
    suffix=$(echo "$var" | sed 's/OHMO_TELEGRAM_TOKEN_//')
    write_channel_entry "telegram_$(echo $suffix | tr '[:upper:]' '[:lower:]')" \
                        "telegram" \
                        "${!var}"
done
```

---

### 6. ACA secrets and env vars — one secret per token

```bash
az containerapp secret set \
  --name brain-copilot-usi-demo-app \
  --resource-group rg-copilot-usi-demo \
  --secrets \
      telegram-token-a="$BOT_TOKEN_A" \
      telegram-token-b="$BOT_TOKEN_B"

az containerapp update \
  --name brain-copilot-usi-demo-app \
  --resource-group rg-copilot-usi-demo \
  --set-env-vars \
      OHMO_TELEGRAM_TOKEN=secretref:telegram-token-a \
      OHMO_TELEGRAM_TOKEN_B=secretref:telegram-token-b
```

No image rebuild is required for the ACA secret/env change, but a **new
revision** is needed to pick up the additional env var. The code changes in
§2–4 require a rebuild and redeploy.

---

## Session key behaviour

By default, `OhmoGatewayBridge` computes:

```
session_key = f"{channel_name}:{chat_id}"
```

With two bots this produces:

```
telegram_a:12345678   ← Bot A conversation with user 12345678
telegram_b:12345678   ← Bot B conversation with same user (separate session)
```

To share a session across both bots for the same user, the session key
computation would need to strip the channel prefix:

```python
# shared-session variant (optional future work)
session_key = f"telegram:{chat_id}"   # same for both bots
```

This is a deliberate design decision — leave it per-channel by default
(isolated sessions) unless shared memory is explicitly required.

---

## Implementation checklist (when ready to code)

- [ ] Add `type` discriminator field to Telegram channel config model
- [ ] Update `ChannelManager._init_channels()` to support multiple entries of the same type
- [ ] Update `docker-entrypoint.sh` to scan for `OHMO_TELEGRAM_TOKEN_*` env vars
- [ ] Update `gateway.json` schema documentation
- [ ] Add a second secret + env var to the ACA deployment (`deploy.sh`)
- [ ] Write integration test: two `TelegramChannel` instances on the same bus, confirm both receive and reply independently
- [ ] Decide and document session key policy (isolated vs shared across bots)
