## Core-system Skill
This skill allows the user to turn off (or restart) core system, with a voice confirmation (yes). And contains core features for system. 

## Features
- A simple skill to shutdown/restart system by voice.
- Manages "give me a second" remark during response latency
- Speaks phrase, required by user

## Intent
 Intent | Combination of Vocabs |
--------|-----------------------|
 Shutdown System | require("shutdown"), require("system")|
 Restart System |require("restart")|
 Mute microphone | require("mute"), optionally("microphone")|


## Examples
 - "shutdown system"
 - "restart system "
 - "reboot system"
