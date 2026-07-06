# Environment And Secrets

`.env` is per-target state. It is ignored by git and excluded from deploy.

## Asterisk VM

Required for PBX:

```text
SIP_EXTENSIONS
SIP_EXT_<num>_PASSWORD
ASTERISK_VERSION
```

Optional:

```text
MONITORING_IP       required only for zabbix-agent2 setup
OPENAI_API_KEY      required for voicebot agents
LIVEKIT_API_KEY     required for LiveKit lane
LIVEKIT_API_SECRET  required for LiveKit lane
VOICEBOT_MODEL_PROFILE optional shared model/cost profile name
VOICEBOT_STT_MODEL     optional shared STT model override
VOICEBOT_LLM_MODEL     optional shared LLM model override
VOICEBOT_TTS_MODEL     optional shared TTS model override
VOICEBOT_TTS_VOICE     optional shared TTS voice override
```

Voicebot model overrides are comparable only when LiveKit and Pipecat read the
same values. The observer service must not receive provider or SIP secrets; it
reads generated `/var/lib/voicebot` artifacts only.

## SBC VM

Required for SBC:

```text
SBC_IP
ASTERISK_IP
```

Optional:

```text
MONITORING_IP
ZABBIX_VERSION
```

`SBC_IP` is the SBC VM's own DHCP address. `ASTERISK_IP` is the Asterisk VM
address. Read both from libvirt DHCP after boot.

## Monitoring VM

Required:

```text
MONITORING_IP
ZABBIX_DB_PASSWORD
ZABBIX_VERSION
```

## Host

Host-side tools may use local secrets for test generation, such as
`ELEVENLABS_API_KEY` and `ELEVENLABS_VOICE_ID`. These are not VM deploy inputs.
