#!/usr/bin/env bash
echo "[start] hopper cleaner: inbox hygiene before candidate promotion"
python3 scripts/clean_hopper.py --watch
