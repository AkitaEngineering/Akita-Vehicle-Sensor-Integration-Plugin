---
name: Bug Report
about: Create a report to help us improve AVSIP
title: "[BUG] Brief description of bug"
labels: bug, needs-triage
assignees: ''

---

**Describe the Bug**
A clear and concise description of what the bug is.

**To Reproduce**
Steps to reproduce the behavior:
1. Go to '...'
2. Configure '....'
3. Run AVSIP with '....'
4. See error '....'

**Expected Behavior**
A clear and concise description of what you expected to happen.

**Screenshots or Log Files (Important!)**
If applicable, add screenshots to help explain your problem.
**Crucially, please provide relevant AVSIP log output.** Set `log_level: "DEBUG"` in `avsip_config.json` for detailed logs. *Remember to remove or obfuscate any sensitive information (passwords, API keys, specific location data) before pasting logs.*

\`\`\`text
<Paste AVSIP log output here>
\`\`\`

**Configuration (`avsip_config.json`)**
Please provide the relevant sections of your `avsip_config.json` file. *REMEMBER TO REMOVE OR OBFUSCATE ANY SENSITIVE INFORMATION.*

\`\`\`json
{
  // Paste relevant config sections here
}
\`\`\`

**Environment (please complete the following information):**
* **AVSIP Version:** [e.g., Git commit SHA, release version if available]
* **Python Version:** [e.g., 3.9.2]
* **Operating System:** [e.g., Raspberry Pi OS Bullseye, Ubuntu 22.04, Windows 10]
* **Host System Hardware:** [e.g., Raspberry Pi 4B 4GB, Laptop Dell XPS]
* **OBD-II Adapter (if applicable):** [e.g., Vgate iCar Pro Bluetooth, Generic ELM327 USB]
* **CAN Interface (if applicable):** [e.g., PiCAN2, Kvaser Leaf Light]
* **Meshtastic Device (if applicable):** [e.g., LilyGo T-Beam v1.1, Heltec LoRa 32 V2]
* **Meshtastic Firmware Version (if applicable):** [e.g., 2.1.0]

**Additional Context**
Add any other context about the problem here. For example, was it working before a specific change? Are there specific conditions under which it occurs?

