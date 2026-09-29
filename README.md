# SmartThings Soundbar Extras

**The soundbar controls missing from Home Assistant's SmartThings integration.**

Night mode, voice amplifier and bass boost as native switches, plus sound modes
and individual speaker levels. I tested it on the HW-Q930D; for other models, see
[Compatibility](#compatibility). It uses the SmartThings connection you already
have, so no personal access token, no second login and no YAML helpers.

It's a **companion integration**. It doesn't replace SmartThings, and it isn't a
Home Assistant add-on. Keep using the built-in integration for power, volume and mute.

## Controls

| Entity | Behavior |
| --- | --- |
| Night mode switch | Remembers the last command accepted by SmartThings |
| Voice amplifier switch | Same assumed-state behavior |
| Bass boost switch | Same assumed-state behavior |
| Sound mode selector | Standard, Surround, Game Pro, Adaptive Sound; assumed state |
| Woofer level | Whole-number adjustments from −6 to +6 dB; assumed state |
| Channel levels | Center, side, wide, front top, rear, rear top, rear side; −6 to +6 dB each |
| Reported input source sensor | Shows the last source reported by SmartThings; disabled by default when the local API is on |

**Assumed state is on purpose.** Samsung's advanced-audio readback simply isn't
reliable. After an HA restart the switches restore their last assumed state, but
they can't see changes made in the SmartThings app or with the remote. A new
control starts as unknown. A rejected command leaves the previous state as it was.
And keep in mind: SmartThings accepting a command doesn't prove the soundbar
actually applied it.

Mode and level controls restore their last accepted value too. They send **no
commands at startup**, so your speaker levels are never reset to zero. Changing a
channel only touches that channel. All levels are sliders from −6 to +6, in 1 dB
steps. The woofer has one extra position, −12, directly below −6: the HW-Q930D
turns anything below −6 into −12 (I sent −8, and the SmartThings app then showed
−12). This integration stops at −6, so it never shows a value the soundbar doesn't
have. For −12, use the SmartThings app.

There's no cloud input control. The Q930D's cloud capability only offers
`setNextInputSource`, and on the real soundbar SmartThings answers `ACCEPTED`… but
the input never changes. To switch inputs, use the `Input (local)` selector from
the local API below. The source sensor can lag, or stay stale if Samsung doesn't
send an update.

## Local API (optional)

Samsung's 2024 (D) and newer Wi-Fi soundbars can also be reached directly on your
local network, through IP Control (TLS on port 1516), next to the cloud connection.
This adds six `(local)` entities: codec, input, sound mode, power, volume and mute.
All of them are read back from the device itself, not assumed.

It also changes the cloud sound mode selector. Once the local API confirms a
reading, the selector shows that confirmed state instead of an assumed one. The
selector can only set the four modes the cloud accepts (`standard`, `surround`,
`game` and `adaptive`). Other modes the soundbar reports, such as `MUSIC`, do show
up in the selector, but you can only set them with **Sound mode (local)**.

Some models accept a local value and then ignore it (a Q990F answers MUSIC with
success, and simply stays in its mode), or refuse it outright. A refused value
shows an error. An ignored one shows briefly, then reverts at the confirming read.

The local API also adds **Player (local)**, a media player for power, volume, mute,
input and sound mode. It reacts faster than the SmartThings media player, and it
keeps working without the cloud. There's no play/pause or track info, because IP
Control doesn't offer them. Don't need it? Switch it off under **Configure** (**Add
a local media player**). Every local control shows a command's result as soon as
the soundbar accepts it, without waiting for the next poll; a full reading confirms
it shortly after.

After you change the mode with the cloud selector, it stays assumed for about
2 seconds. SmartThings accepting the command doesn't mean the soundbar has applied
it yet, so only a local reading taken after that settles the state.

While the soundbar can't be reached over the local API, polling slows down to the
off interval until it answers again.

To enable it:

1. In the SmartThings app, turn on IP control for the soundbar.
2. Open the integration entry, choose **Configure**, and turn on **Use local API**.
3. Pick the soundbar from the discovered list (or type its address), then set the
   two polling intervals (defaults: 5 s while on, 60 s while off). **Add a local
   media player** is on by default.

The discovered addresses come from AirPlay advertisements the soundbar already
sends. If the address changes later, the new one is only applied automatically
when it presents the same pinned certificate. Otherwise nothing changes, and you
re-open Configure. Easiest is a DHCP reservation for the soundbar; then the address
doesn't change at all.

The connection is pinned to the soundbar's certificate fingerprint the first time
it's confirmed. If the certificate ever changes, the local entities go unavailable
and a repair issue appears. Re-saving the local API settings under **Configure**
trusts the new certificate. A second repair issue appears if SmartThings says the
soundbar is online, but the local API hasn't answered for 30 minutes. Both issues
clear by themselves once a poll succeeds again, and they're removed if you disable
the local API or remove the entry.

Standby readback works: with the soundbar off, the codec entity reads `UNKNOWN`.
That's exactly what the device reports, so it isn't blanked out.

Night mode, voice amplifier, bass boost and the speaker levels have no local
readback at all. They stay assumed-state, with or without the local API.

## Requirements and compatibility

- Home Assistant **2026.9.0 or newer**. The test suite currently targets 2026.9.0.
- The built-in **SmartThings** integration, configured and connected.
- A Samsung soundbar registered there with `audioVolume` and `execute` capabilities.

### Compatibility

SmartThings no longer tells integrations what a soundbar supports. So setup offers
every control, and only pre-selects what's known to work. Choose the controls the
SmartThings app shows for your soundbar.

| | Tested here | Reported working by other users | Expected | Not supported or unknown |
| --- | --- | --- | --- | --- |
| Night mode, voice amplifier, bass boost | HW-Q930D | Q990B, Q995B, Q930B, Q995GC | Most Q-series from 2020 | No reports yet for S-series, B-series and Q6x |
| Sound mode | HW-Q930D | QW950T, Q900A, Q930B, Q990B, Q990C | Q-series from 2020 | No reports yet for 2019 models |
| Woofer and channel levels | HW-Q930D | Q935B (woofer), Q90R (woofer), Q995GC (channels) | Channels your model's speaker layout has | Channels your model lacks |
| Local API and Player (local) | HW-Q930D | Q990D, Q800D, S800D, S700D, Q990F, Q935GF, Q930F, Q995F | 2024 (D) and newer Wi-Fi soundbars | 2023 (C) and older; Q800H and S61D answer power only |

Some 2022–2023 soundbars (e.g. Q990C) already get a sound mode control from HA core.
Enabling this integration's sound mode as well works, but it's redundant.

The reports come from [YASSI](https://github.com/samuelspagl/ha_samsung_soundbar/issues),
[hass-samsung-soundbar-local](https://github.com/ZtF/hass-samsung-soundbar-local/issues),
the [HA community forum](https://community.home-assistant.io/t/samsung-soundbar-local/884397)
and [RTI's driver list](https://driverstore.rticontrol.com/driver/samsung-soundbars).
Tried another model? Please open an issue with the **Works on my model** form,
whether it works or not, and attach the diagnostics.

**HW-Q930D** (firmware 1072.1) was checked on 2026-09-28: every cloud control in the
SmartThings app, plus power, volume, mute, input and sound mode through the local API.

Multiple soundbars and multiple SmartThings locations are supported, with one
companion entry per soundbar.

The companion shows up as its own device, linked to the original SmartThings device.
The SmartThings controls add no polling loop and no extra event-stream connection.
Only the optional local API polls the soundbar, and it does that on your own network.

## Installation

You need Home Assistant 2026.9 or later, with the built-in SmartThings integration
already set up for your soundbar.

**With HACS**

1. In HACS, open the menu and choose **Custom repositories**. Add
   `https://github.com/c-kick/ha-smartthings-soundbar-extras` with type **Integration**.
2. Search HACS for **SmartThings Soundbar Extras**, download it, and restart Home Assistant.
3. Open **Settings → Devices & services → Add integration**.
4. Search for **SmartThings Soundbar Extras**, select your soundbar, and choose its controls.

**Manually**

Copy `custom_components/soundbar_control` into your HA `config/custom_components/`,
restart Home Assistant, then follow steps 3–4.

To change which audio controls are enabled, use **Reconfigure** on the integration
entry. Upgrading from 2.0 enables the eight new HW-Q930D controls once, without
touching your existing switch selections. After that, your reconfiguration choices
are kept. To remove the integration, delete its entry under Devices & services.
Your original SmartThings integration and soundbar stay configured.

## Automations

Just use the normal `switch.turn_on` and `switch.turn_off` actions. For example
(with your own entity ID):

```yaml
action: switch.turn_on
target:
  entity_id: switch.living_room_soundbar_night_mode
```

The original `soundbar_control.set` action is still there, for compatibility:

```yaml
action: soundbar_control.set
data:
  setting: nightmode
  enabled: true
```

With multiple soundbars, add `device_id` with the SmartThings device ID. An
ambiguous request fails, rather than just picking one of your soundbars. The
native switches don't need device IDs in their automation actions.

## Troubleshooting

- **No soundbars found:** check that the built-in SmartThings integration is loaded
  and that the soundbar shows up there. This companion doesn't do a second login.
- **Unavailable:** check the parent SmartThings connection and the device's cloud
  health. Standby isn't automatically treated as offline.
- **Command failed:** the token refresh or command submission failed, or Samsung
  returned something unexpected. The command isn't replayed automatically, because
  a timed-out request might already have reached the soundbar.
- **State differs from the app:** advanced-audio state is assumed. Send the setting
  you want again from HA. The source state is simply Samsung's last reported value.
- **SmartThings was deleted and re-added:** the companion entry reports that its
  SmartThings integration no longer exists. Remove and re-add the companion entry to
  select the new connection. Normal SmartThings reloads are handled automatically.

When you report a problem, please download the diagnostics from the integration
entry. They contain the model, capability names, availability and assumed states.
With the local API on, there's also a local section (enabled, whether a certificate
is pinned, poll intervals, last error and last read status). They leave out
credentials, account information, device IDs, the soundbar's address, MAC and
certificate fingerprint, and raw cloud responses.

## Further controls

For verification details, source selection, EQ and possible local control, see
[the feature research](docs/features.md).

## Development

```sh
python3.14 -m venv .venv
.venv/bin/pip install -r requirements_test.txt
.venv/bin/pytest
.venv/bin/ruff check .
```

On a shared Linux server with a systemd user manager, `scripts/test` runs the tests
with a 1536 MiB memory limit, no swap and a three-minute deadline.

The only code tied to the built-in SmartThings runtime is `smartthings.py`. It
reuses the parent's OAuth callback, including HA's refresh lock and credential
persistence. That's an internal HA interface, so test this boundary when supporting
new HA versions. This integration copies no credentials from `.storage`, and saves
none either.

The tests run against HA's actual entity registry, config flows, restored state and
OAuth session; only the network requests are mocked. The parent integration is
modeled with its real runtime types and `pysmartthings` (pinned to HA's version in
`requirements_test.txt`), and events go through the library's own parsing and
dispatch. When HA bumps that version, bump the pin too. CI runs tests and lint, with
separate HACS/hassfest validation workflows. A weekly run tests against the newest
HA release and the pysmartthings version it requires, to catch changes in the
SmartThings integration's internals early.

## Credits and license

Samsung's advanced-audio command paths were documented by
[YASSI](https://ha-samsung-soundbar.vercel.app/smartthings-api/extra_information).
Authentication belongs to Home Assistant's built-in
[SmartThings integration](https://www.home-assistant.io/integrations/smartthings/).
This is an independent community project, not affiliated with Samsung.

[MIT license](LICENSE).
