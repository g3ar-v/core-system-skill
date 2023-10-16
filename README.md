## Core-system Skill
the behavioural functions of the system.

## Features
- Shutdown/restart system by voice.
- Manages "give me a second" remark during response latency
- <s>speaks phrase, required by user</s>
- handles interrupted speech later on
- handles the dismissal of the system 

## Intent
 Intent | Combination of Vocabs |
--------|-----------------------|
 Shutdown System | require("shutdown"), require("system")|
 Restart System |require("restart")|
 Mute microphone | require("mute"), optionally("microphone")|
Dismissal| Nevermind, Forget it |



## Examples
 - "shutdown system"
 - "restart system "
 - "reboot system"
