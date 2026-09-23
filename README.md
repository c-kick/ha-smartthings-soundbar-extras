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
| Sound mode selector (HW-Q930D) | Standard, Surround, Game Pro, Adaptive Sound; assumed state |
| Woofer level (HW-Q930D) | Whole-number adjustments from −6 to +6 dB; assumed state |
| Channel levels (HW-Q930D) | Center, side, wide, front top, rear, rear top; −6 to +6 dB each |
| Next input source button | Cycles sources when `samsungvd.audioInputSource` is advertised |
| Reported input source sensor | Shows the last source reported by SmartThings |

**Assumed state is deliberate.** Samsung's advanced-audio readback is unreliable.
The switches restore their previous assumed state after restarting HA, but cannot
detect changes made in the SmartThings app or with the physical remote. A new
control starts as unknown. Rejected commands leave the previous state untouched.
Cloud acceptance does not prove the soundbar applied the setting.

Mode and level controls also restore their last accepted value. They send **no
commands at startup** and never initialize your speaker levels to zero. Channel
adjustments update only the selected channel. All seven levels use sliders with
1 dB steps from −6 to +6. The woofer currently exposes the
conservative −6 to +6 range; lower attenuation settings are not yet model-verified.

Source control has a different limitation: the Q930D's cloud capability offers
`setNextInputSource`, not direct input selection. We expose that exact behavior.
The source sensor can lag or remain stale if Samsung does not send an update;
pressing the button does not make the integration guess the new input.

## Local API (optional)

HW-Q930D and other soundbars with Samsung's TLS-based IP Control (port 1516) can be
polled directly, alongside the cloud connection. This adds six `(local)` entities —
codec, input, sound mode, power, volume and mute — all read back from the device
itself, not assumed. It also changes the cloud sound mode selector: once the local
API confirms a reading, the selector shows that confirmed state instead of an assumed
one, for its four cloud-settable modes.

To enable it:

1. In the SmartThings app, turn on IP control for the soundbar.
2. Open the integration entry, choose **Configure**, and turn on **Use local API**.
3. Pick the soundbar from the discovered list, or type its address, then set the
   two polling intervals (defaults: 5 s while on, 60 s while off).

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

**HW-Q930D:** all three audio switches tested on a physical device. The additional
source command is verified against its live capability schema and covered by
mocked tests; physical source cycling still needs validation. Mode/channel commands
are based on YASSI's known OCF formats and Samsung's Q930D manual, with exact-payload
tests. A HW-Q930D user reports the mode and level controls working. Live read probes for sound
mode, woofer, and channel levels all returned null, so no readback is claimed.

Other models may work, but are not claimed as tested. During setup, enable only
audio controls your model offers in the SmartThings app. HW-Q930D defaults to all
available audio controls; other models offer the original three switches and
default to none. Mode/level profiles are not assumed compatible with other models.
Multiple soundbars and multiple SmartThings
locations are supported, with one companion entry per soundbar.

The companion appears as its own device linked to the original SmartThings device.
It adds no polling loop or extra event-stream connection.

## Installation

This package is prepared for distribution; it has not yet been published to GitHub
or submitted to HACS. Use manual installation until publication.

1. Copy `custom_components/soundbar_control` into your HA `config/custom_components/`.
2. Restart Home Assistant.
3. Open **Settings → Devices & services → Add integration**.
4. Search for **SmartThings Soundbar Extras**, select your soundbar, and choose its controls.

After publication, the repository can be added to HACS as an **Integration** custom
repository. Restart after downloading, then follow steps 3–4. `hacs.json` and the
single-domain directory layout are included; HACS default-list approval is separate.

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
HACS/hassfest validation workflows for publication.

## Credits and license

Samsung's advanced-audio command paths were documented by
[YASSI](https://ha-samsung-soundbar.vercel.app/smartthings-api/extra_information).
Authentication belongs to Home Assistant's built-in
[SmartThings integration](https://www.home-assistant.io/integrations/smartthings/).
This independent community project is not affiliated with Samsung.

[MIT license](LICENSE).
