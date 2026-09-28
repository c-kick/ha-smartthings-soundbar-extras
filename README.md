# SmartThings Soundbar Extras

**The soundbar controls missing from Home Assistant's SmartThings integration.**

Night mode, voice amplifier and bass boost as native switches, plus sound modes
and individual speaker levels for HW-Q930D. Uses the SmartThings
connection you already have: no personal access token, second login, or YAML helpers.

This is a **companion integration**, not a replacement for SmartThings and not a
Home Assistant add-on. Keep the built-in integration for power, volume and mute.

## Controls

| Entity | Behavior |
| --- | --- |
| Night mode switch | Remembers the last command accepted by SmartThings |
| Voice amplifier switch | Same assumed-state behavior |
| Bass boost switch | Same assumed-state behavior |
| Sound mode selector | Standard, Surround, Game Pro, Adaptive Sound; assumed state |
| Woofer level | Whole-number adjustments from −12 to +6 dB; assumed state |
| Channel levels | Center, side, wide, front top, rear, rear top, rear side; −6 to +6 dB each |
| Reported input source sensor | Shows the last source reported by SmartThings; disabled by default when the local API is on |

**Assumed state is deliberate.** Samsung's advanced-audio readback is unreliable.
The switches restore their previous assumed state after restarting HA, but cannot
detect changes made in the SmartThings app or with the physical remote. A new
control starts as unknown. Rejected commands leave the previous state untouched.
Cloud acceptance does not prove the soundbar applied the setting.

Mode and level controls also restore their last accepted value. They send **no
commands at startup** and never initialize your speaker levels to zero. Channel
adjustments update only the selected channel. All levels use sliders with
1 dB steps: channels from −6 to +6, the woofer from −12 to +6.

There is no cloud input control. The Q930D's cloud capability only offers
`setNextInputSource`, and on the real soundbar SmartThings answers `ACCEPTED` but the
input never changes. To switch inputs, use the `Input (local)` selector from the local
API below. The source sensor can lag or remain stale if Samsung does not send an update.

## Local API (optional)

Samsung's 2024 (D) and newer Wi-Fi soundbars can be reached directly over the local
network with IP Control (TLS on port 1516), alongside the cloud connection. This adds six `(local)` entities —
codec, input, sound mode, power, volume and mute — all read back from the device
itself, not assumed. It also changes the cloud sound mode selector: once the local
API confirms a reading, the selector shows that confirmed state instead of an assumed
one. The selector can set only the four cloud-settable modes (`standard`,
`surround`, `game` and `adaptive`). Other modes the soundbar reports, such as
`MUSIC`, are shown in the selector too, but can only be set with
**Sound mode (local)**.

Some models accept a local value but ignore it (a Q990F answers MUSIC with success
and stays in its mode) or refuse it outright. A refused value shows an error; an
ignored one shows briefly and then reverts at the confirming read.

The local API also adds **Player (local)**, a media player for power, volume, mute,
input and sound mode. It reacts faster than the SmartThings media player and keeps
working without the cloud. It has no play/pause or track info, because IP Control
doesn't offer them. You can switch it off under **Configure** (**Add a local media
player**). Every local control shows a command's result as soon as the soundbar
accepts it, without waiting for the next poll. A full reading confirms it shortly after.

After you change the mode with the cloud selector, it stays assumed for about
2 seconds: SmartThings accepting the command doesn't mean the soundbar has applied
it yet, so only a local reading taken after that settles the state.

While the soundbar can't be reached over the local API, polling slows down to the
off interval until it answers again.

To enable it:

1. In the SmartThings app, turn on IP control for the soundbar.
2. Open the integration entry, choose **Configure**, and turn on **Use local API**.
3. Pick the soundbar from the discovered list, or type its address, then set the
   two polling intervals (defaults: 5 s while on, 60 s while off). **Add a local
   media player** is on by default.

Discovered addresses come from AirPlay advertisements the soundbar already sends.
A later address change is only applied automatically when the new address presents
the same pinned certificate; otherwise nothing changes and you re-open Configure.
A DHCP reservation for the soundbar avoids address changes altogether.

The connection is pinned to the soundbar's certificate fingerprint the first time
it's confirmed. If the presented certificate ever changes, the local entities go
unavailable and a repair issue appears; re-saving the local API settings under
**Configure** trusts the new certificate. A second repair issue appears if
SmartThings reports the soundbar online but the local API stops answering for
30 minutes. Both issues clear automatically once a poll succeeds again, and are
removed if you disable the local API or remove the entry.

Standby readback works: with the soundbar off, the codec entity reads `UNKNOWN`,
shown exactly as the device reports it, not blanked out.

Night mode, voice amplifier, bass boost and the speaker levels have no local
readback at all — they stay assumed-state, local API or not.

## Requirements and compatibility

- Home Assistant **2026.9.0 or newer**. The test suite currently targets 2026.9.0.
- The built-in **SmartThings** integration, configured and connected.
- A Samsung soundbar registered there with `audioVolume` and `execute` capabilities.

### Compatibility

SmartThings no longer tells integrations what a soundbar supports, so setup offers every
control and pre-selects only what is known to work. Choose the controls the SmartThings
app shows for your soundbar.

| | Tested here | Reported working by other users | Expected | Not supported or unknown |
| --- | --- | --- | --- | --- |
| Night mode, voice amplifier, bass boost | HW-Q930D | Q990B, Q995B, Q930B, Q995GC | Most Q-series from 2020 | No reports yet for S-series, B-series and Q6x |
| Sound mode | HW-Q930D | QW950T, Q900A, Q930B, Q990B, Q990C | Q-series from 2020 | No reports yet for 2019 models |
| Woofer and channel levels | HW-Q930D | Q935B (woofer), Q90R (woofer), Q995GC (channels) | Channels your model's speaker layout has | Channels your model lacks |
| Local API and Player (local) | HW-Q930D | Q990D, Q800D, S800D, S700D, Q990F, Q935GF, Q930F, Q995F | 2024 (D) and newer Wi-Fi soundbars | 2023 (C) and older; Q800H and S61D answer power only |

HA core has its own sound mode control for some 2022–2023 soundbars (e.g. Q990C);
enabling this integration's sound mode as well works but is redundant.

Reports come from [YASSI](https://github.com/samuelspagl/ha_samsung_soundbar/issues),
[hass-samsung-soundbar-local](https://github.com/ZtF/hass-samsung-soundbar-local/issues),
the [HA community forum](https://community.home-assistant.io/t/samsung-soundbar-local/884397)
and [RTI's driver list](https://driverstore.rticontrol.com/driver/samsung-soundbars).
If you try another model, please open an issue with the **Works on my model** form,
whether it works or not, and attach the diagnostics.

**HW-Q930D** (firmware 1072.1) was checked on 2026-09-28: every cloud control in the
SmartThings app, and power, volume, mute, input and sound mode through the local API.

Multiple soundbars and multiple SmartThings
locations are supported, with one companion entry per soundbar.

The companion appears as its own device linked to the original SmartThings device.
The SmartThings controls add no polling loop or extra event-stream connection. Only the
optional local API polls the soundbar, on your network.

## Installation

Requires Home Assistant 2026.9 or later, with the built-in SmartThings integration
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

To change enabled audio controls, use **Reconfigure** on the integration entry.
Upgrading from 2.0 enables the eight new HW-Q930D controls once, without changing
your existing switch selections. Subsequent reconfiguration choices are retained.
To remove it, delete its entry under Devices & services. Your original SmartThings
integration and soundbar remain configured.

## Automations

Use the normal `switch.turn_on` and `switch.turn_off` actions. For example, substitute
your entity ID in this action:

```yaml
action: switch.turn_on
target:
  entity_id: switch.living_room_soundbar_night_mode
```

The original `soundbar_control.set` action is retained for compatibility:

```yaml
action: soundbar_control.set
data:
  setting: nightmode
  enabled: true
```

With multiple soundbars, add `device_id` with the SmartThings device ID. An ambiguous
request fails instead of choosing an arbitrary soundbar. Native switches do not
need device IDs in their automation actions.

## Troubleshooting

- **No soundbars found:** verify the built-in SmartThings integration is loaded and
  the soundbar appears there. This companion does not perform a second login.
- **Unavailable:** check the parent SmartThings connection and the device's cloud
  health. Standby is not automatically treated as offline.
- **Command failed:** the token refresh or command submission failed, or Samsung
  returned an unexpected result. The command is not automatically replayed, because
  a timed-out request might already have reached the soundbar.
- **State differs from the app:** advanced-audio state is assumed. Send the desired
  setting again from HA. Source state is Samsung's last reported value.
- **SmartThings was deleted and re-added:** the companion entry reports that its
  SmartThings integration no longer exists. Remove and re-add the companion entry to
  select the replacement connection. Normal SmartThings reloads are handled automatically.

Download diagnostics from the integration entry when reporting a problem. The
diagnostics contain model, capability names, availability and assumed states, plus
a local section (enabled, whether a certificate is pinned, poll intervals, last
error and last read status) when the local API is on. They exclude credentials,
account information, device IDs, the soundbar's address, MAC and certificate
fingerprint, and raw cloud responses.

## Further controls

See [the feature research](docs/features.md) for verification details, source
selection, EQ and possible local control.

## Development

```sh
python3.14 -m venv .venv
.venv/bin/pip install -r requirements_test.txt
.venv/bin/pytest
.venv/bin/ruff check .
```

On a shared Linux server with a systemd user manager, `scripts/test` runs the tests
with a 1536 MiB memory limit, no swap, and a three-minute deadline.

The only code coupled to the built-in SmartThings runtime is `smartthings.py`.
It reuses the parent's OAuth callback, including HA's refresh lock and credential
persistence. This is an internal HA interface: test this boundary when supporting
new HA versions. No credentials are copied from `.storage` or saved by this integration.

Tests exercise HA's actual entity registry, config flows, restored state and OAuth
session, while mocking network requests. The parent integration is modeled with its
real runtime types and `pysmartthings` (pinned to HA's version in
`requirements_test.txt`); events go through the library's own parsing and dispatch.
Bump that pin when HA does. CI runs tests and lint, with separate
HACS/hassfest validation workflows. A weekly run tests against the newest HA release
and the pysmartthings version it requires, to catch changes in the SmartThings
integration's internals early.

## Credits and license

Samsung's advanced-audio command paths were documented by
[YASSI](https://ha-samsung-soundbar.vercel.app/smartthings-api/extra_information).
Authentication belongs to Home Assistant's built-in
[SmartThings integration](https://www.home-assistant.io/integrations/smartthings/).
This independent community project is not affiliated with Samsung.

[MIT license](LICENSE).
