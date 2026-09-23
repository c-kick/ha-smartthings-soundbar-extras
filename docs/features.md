# Additional soundbar controls

Research on 2026-09-05, using the physical HW-Q930D's SmartThings capability/status
responses and the installed HA SmartThings implementation.

Follow-up: the HW-Q930D user reports the mode and level controls working after
restart. Levels use sliders from −6 to +6 dB in 1 dB steps.

| Feature | Evidence | Decision |
| --- | --- | --- |
| Next input | Live `samsungvd.audioInputSource` schema exposes `setNextInputSource` with no arguments | Implemented as a button; physical validation pending |
| Reported input | Live status exposes `inputSource`; Q930D advertises D.IN, HDMI1, BT, WIFI | Implemented as a sensor using existing push events |
| Choose an exact input | That cloud capability has no setter accepting an input name | Do not simulate selection by repeated next-source commands with stale feedback |
| Sound mode | Samsung Q930D manual lists Standard, Surround, Game Pro and Adaptive Sound; YASSI supplies the OCF values | Implemented for HW-Q930D as an assumed-state selector; user reports working |
| Subwoofer level | YASSI implements `/sec/networkaudio/woofer` | Implemented for HW-Q930D with a conservative −6…+6 range; user reports working |
| Channel levels | Samsung's manual lists center, side, wide, front top, rear and rear top at −6…+6; YASSI supplies `channelVolume` payloads | Implemented for HW-Q930D as separate assumed-state sliders; user reports working |
| EQ preset and bands | Documented `/sec/networkaudio/eq`, supported preset list and seven bands on some models | Candidate; discover model-specific bands, ranges and mode restrictions |
| Power, mute, volume | Already supplied by the built-in SmartThings media player | Keep in the parent integration |
| Codec and direct input via LAN | Existing local Q930D investigation found TLS JSON-RPC on port 1516 | Possible optional local transport, requiring IP setup, authentication and model tests |
| SpaceFit, AV sync | Not established by this investigation | Research only; no support claim |

The installed HA media player does not advertise source selection for the Q930D's
`samsungvd.audioInputSource` capability. Its input-select implementation handles
other capability families. Sending those other families' commands to this device
would be an unsupported guess.

Advanced OCF resources share one `execute` result slot. A future discovery/readback
feature must correlate responses to the requested resource and timestamp, serialize
reads, and tolerate absent responses. A null or stale result must not become a
false state or erase a valid assumed setting.

The live Q930D accepted read requests for soundmode, woofer, and channelVolume,
but all three returned `data.value: null`. The model-specific profile therefore
uses documented options, explicit assumed state, and no automatic discovery or
polling. Unknown values stay unknown until the user sends a command.

Wire details:

- `soundmode`: property `x.com.samsung.networkaudio.soundmode`, string values
  `standard`, `surround`, `game`, `adaptive sound`.
- `woofer`: property `x.com.samsung.networkaudio.woofer`, integer level.
- `channelVolume`: property `x.com.samsung.networkaudio.channelVolume`, a one-item
  array `[{"name": "Spk_Center", "value": 1}]`. Other identifiers are `Spk_Side`,
  `Spk_Wide`, `Spk_Front_Top`, `Spk_Rear`, `Spk_Rear_Top`. Never send unrelated
  channels with guessed defaults.

Next candidates: EQ and optional local source selection. The core companion
continues to require no IP address or extra login.

Sources: [YASSI's OCF documentation](https://ha-samsung-soundbar.vercel.app/smartthings-api/extra_information),
[HA SmartThings documentation](https://www.home-assistant.io/integrations/smartthings/),
and authenticated read-only responses from `/v1/capabilities/samsungvd.audioInputSource/1`
and `/v1/devices/{deviceId}/status`. No account-specific responses are bundled here.

## Local API (IP Control)

Live probes against the HW-Q930D, firmware 1072.1, on 2026-09-23, compared with
what SmartThings reported at the same moment:

| Method | Live result | SmartThings reported |
| --- | --- | --- |
| `getCodec` | `DTS` | not available |
| `powerControl` (no params) | `powerOn` | `off` |
| `inputSelectControl` (no params) | `E_ARC` | `D.IN` |
| `soundModeControl` (no params) | `ADAPTIVE` | not available |
| `getVolume` | `10` | `10` |
| `getMute` | `false` | `muted` |
| `getIdentifier` | `22_AV_HW-Q930D` | — |

SmartThings was stale on three of these at the moment of the probe: it reported
power `off` while the soundbar was locally reachable and answering (`powerOn`),
input `D.IN` where the local read said `E_ARC`, and mute `muted` where the local
read said `false`. This is exactly the gap the local entities close: they read the
device directly instead of relying on SmartThings' last pushed event.

A follow-up device check, soundbar in standby, confirmed writes and standby
behavior:

| Call | Live result |
| --- | --- |
| `volumeControl` `{"volume": 6}` (integer) | `{"success": true}` |
| `muteControl` `{"mute": false}` (bool) | `{"success": true}` |
| `inputSelectControl` `{"inputSource": "WIFI_SPOIFY"}` | `{"success": true}` |
| `soundModeControl` `{"soundMode": "ADAPTIVE"}` | `{"success": true}` |
| `powerControl` (standby) | `powerOff` |
| `inputSelectControl` (standby, Spotify was last used) | `WIFI_SPOIFY` (the firmware's own spelling) |
| `getCodec` (standby) | `UNKNOWN` |
| `getVolume`, `getMute`, `soundModeControl` (standby) | read normally (`"6"`, `false`, `ADAPTIVE`) |

All reads and writes work in standby, and a no-op write does not wake the soundbar.
A successful write returns `{"success": true}`, never the new value, so the
displayed state always comes from the refresh that follows a write. `UNKNOWN` is a
valid codec string in standby and is shown as is. `WIFI_SPOIFY` is not a known
input; it is added to the input selector's options as an observed value rather than
corrected.

Codec values seen by the deployed integration during an evening of normal use
(2026-09-23, TV over e-ARC):

| Codec | When |
| --- | --- |
| `DTS` | right after power-on |
| `MAT_PCM_ATMOS` | Atmos content (Dolby MAT carrying Atmos over e-ARC) |
| `MAT_PCM` | non-Atmos content over the same MAT link |
| `PCM` | Bluetooth input |
| `UNKNOWN` | standby |

The codec follows the content within one polling interval. Over the whole evening
the local input read `E_ARC` while SmartThings kept reporting `D.IN`.

Error replies are not JSON-RPC shaped. A bad token, an unknown method and a
rejected call all return HTTP 200 with the same body:

```json
{"code": -32700, "message": "Parse error"}
```

There is no way to tell these three cases apart from the reply alone; the client
treats any of them as a failure of that one call.

AirPlay discovery (`_airplay._tcp.local.`) advertises these TXT fields, used to
find the soundbar's current address and match it to a configured entry:

- `deviceid`: the MAC address (`02:00:00:00:00:01` on the test unit)
- `manufacturer`: `Samsung`
- `model`: `HW-Q930D`

Mode/channel implementation evidence:
[YASSI SoundbarDevice.py, revision e8c5d38](https://github.com/samuelspagl/ha_samsung_soundbar/blob/e8c5d38fdec8426e992c1dfcb1f1f6d90124b25b/custom_components/samsung_soundbar/api_extension/SoundbarDevice.py),
[speaker identifiers](https://github.com/samuelspagl/ha_samsung_soundbar/blob/e8c5d38fdec8426e992c1dfcb1f1f6d90124b25b/custom_components/samsung_soundbar/api_extension/const.py),
and [Samsung's Q930D/Q800D/Q700D manual](https://downloadcenter.samsung.com/content/UM/202403/20240307105603275/AH81-17413A-00_WUG_HW-Q930D_Q800D_Q700D_ZA_ENG_240228.0.pdf),
English pages 6–8. Payload shapes were independently implemented; no upstream
implementation code is bundled.
