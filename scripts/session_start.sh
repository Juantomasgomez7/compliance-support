#!/usr/bin/env bash
# Compliance Support, session banner (SessionStart).
#
# Prints an unmissable arming signal when a session starts with the plugin
# loaded, so a gateless session is visibly different from a guarded one: no
# banner means the plugin is not loaded and NOTHING is enforced. Also catches
# the wrong-directory launch: without .compliance.yml in the working directory
# the gates have no scope and stay silent, so the banner says so instead of
# claiming protection.
#
# Output is a single JSON object with only "systemMessage" (shown to the user;
# nothing is added to the model context, so the banner cannot influence review
# behavior). Static strings only: nothing here can fail, but if it ever does,
# a session banner must never block a session from starting.
if [ -f ".compliance.yml" ]; then
  echo '{"systemMessage":"Compliance Support armed: write-time block (CTRL-1/2) and turn-end review (CTRL-3/4) are active. PCI scope: .compliance.yml"}'
else
  echo '{"systemMessage":"Compliance Support is loaded, but there is no .compliance.yml in this directory, so the gates have no scope and stay silent. Launch from the repo root to arm them."}'
fi
exit 0
