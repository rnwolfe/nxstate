# VHS tape for the README hero GIF.  Render with:  vhs demo/nxstate.tape
# https://github.com/charmbracelet/vhs
#
# Credential-free by design: the live commands read the target + creds from the environment
# (NXSTATE_HOST, NXSTATE_USERNAME, NXSTATE_PASSWORD, NXSTATE_TRANSPORT) so this file contains
# no secrets and no hostname. To regenerate against a switch:
#   export NXSTATE_HOST=... NXSTATE_USERNAME=... NXSTATE_PASSWORD=... NXSTATE_TRANSPORT=ssh
#   vhs demo/nxstate.tape

Output demo/nxstate.gif
Set FontSize 18
Set Width 1200
Set Height 800
Set Padding 18
Set Theme "Catppuccin Mocha"

Type "# nxstate — read-only Cisco Nexus state, live against a Nexus 9000v"
Enter
Sleep 1.5s

Type "nxstate system version --json --select nxos_ver_str,chassis_id"
Enter
Sleep 7s

Type "nxstate interface list --format tsv --limit 5 --select interface,state,vlan"
Enter
Sleep 7s

Type "# Structured, projectable, bounded — clean for an agent. And it CANNOT configure:"
Enter
Type "nxstate show 'configure terminal'; echo exit=$?"
Enter
Sleep 3.5s

Type "nxstate schema | jq '{tool, read_only, safety}'"
Enter
Sleep 3.5s
