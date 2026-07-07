Dieses Ultra-Paket erweitert das Masterpaket um:
- isaac_ctl.sh           zentrales Steuer-Skript
- run_healthcheck.sh     direkter Healthcheck-Starter
- update_master.sh       Reinstall/Update aus demselben Bundle
- package/healthcheck_isaac.py
- package/launch_dashboard.sh
- package/stop_isaac.sh

Hinweis:
launch_dashboard.sh startet monitor_server.py und isaac_core.py parallel im Hintergrund
und schreibt PID-Dateien nach runtime/.
