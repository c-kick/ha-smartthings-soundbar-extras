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

Mode/channel implementation evidence:
[YASSI SoundbarDevice.py, revision e8c5d38](https://github.com/samuelspagl/ha_samsung_soundbar/blob/e8c5d38fdec8426e992c1dfcb1f1f6d90124b25b/custom_components/samsung_soundbar/api_extension/SoundbarDevice.py),
[speaker identifiers](https://github.com/samuelspagl/ha_samsung_soundbar/blob/e8c5d38fdec8426e992c1dfcb1f1f6d90124b25b/custom_components/samsung_soundbar/api_extension/const.py),
and [Samsung's Q930D/Q800D/Q700D manual](https://downloadcenter.samsung.com/content/UM/202403/20240307105603275/AH81-17413A-00_WUG_HW-Q930D_Q800D_Q700D_ZA_ENG_240228.0.pdf),
English pages 6–8. Payload shapes were independently implemented; no upstream
implementation code is bundled.
