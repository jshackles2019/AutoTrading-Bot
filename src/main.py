#!/usr/bin/env python3
"""Starter main for Breakout Trading Bot (stub).

This file is a simple entry point and demonstrates loading config and env.
"""
import os
from pathlib import Path

from dotenv import load_dotenv
import yaml

load_dotenv()

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "settings.yaml"


def load_config(path=CONFIG_PATH):
    with open(path, "r") as f:
        return yaml.safe_load(f)


def main():
    config = load_config()
    print("Loaded config:", config)
    print("This is a starter stub. Implement the main loop as described in guide.txt.")


if __name__ == "__main__":
    main()
