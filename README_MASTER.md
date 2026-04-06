# Isaac Deploy Package

Dies ist der deploy-fertige bereinigte Isaac-Stand aus allen verfügbaren Quellen.

## Kanonischer Einstieg

```bash
python3 isaac_core.py
```

## Standardstart

```bash
sh run_isaac.sh
```

## Installation

Termux:
```bash
bash install_termux.sh /storage/emulated/0/Gpt-isaac/deploy/isaac_deploy_package
```

Alpine:
```bash
sh install_alpine.sh /storage/emulated/0/Gpt-isaac/deploy/isaac_deploy_package
```

## Sanity-Check

```bash
python3 sanity_check.py
```

## Hinweise

- `isaac_core.py` ist die primäre Laufzeitdatei.
- `start_isaac.sh` und `install.sh` sind nur Kompatibilitäts-Wrapper.
- Für `ACTIVE_PROVIDER=ollama` muss Ollama separat laufen.
- Browser-/Playwright-Teile sind optional und müssen separat installiert werden.
