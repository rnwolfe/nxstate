# VHS tape for the README hero GIF. Render with: vhs demo/nxstate.tape
# https://github.com/charmbracelet/vhs  (committed as source so the GIF can be regenerated in CI)
#
# These commands run WITHOUT a real device — they showcase the read-only-by-design safety
# surface (help, schema, the WRITE_REFUSED boundary), so the demo is deterministic.

Output demo/nxstate.gif
Set FontSize 18
Set Width 1100
Set Height 700
Set Padding 18
Set Theme "Catppuccin Mocha"

Type "# nxstate — read-only Cisco Nexus state, built for agents"
Enter
Sleep 1s

Type "nxstate --help | head -n 20"
Enter
Sleep 2.5s

Type "# Self-describing: machine-readable schema + safety state"
Enter
Type "nxstate schema | jq '{tool, read_only, safety}'"
Enter
Sleep 2.5s

Type "# It physically cannot configure a switch:"
Enter
Type "nxstate show 'configure terminal' --host sw1 --json; echo exit=$?"
Enter
Sleep 3s

Type "# Self-describing usage guide, embedded in the tool:"
Enter
Type "nxstate agent | head -n 12"
Enter
Sleep 3s
