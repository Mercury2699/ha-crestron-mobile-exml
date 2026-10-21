#!/usr/bin/env python3
"""Crestron Mobile Project Join Extractor.

Parses Crestron Mobile iPad/iPhone XML project files (or extracts them
from a Crestron processor / project zip) and automatically generates
Home Assistant YAML configuration for lights and covers.

Usage:
  python3 extract_crestron_config.py --dir /path/to/extracted/ipad_project/
  python3 extract_crestron_config.py --zip /path/to/Equipment_Room,iPad_Project.zip
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import xml.etree.ElementTree as ET
import zipfile


def parse_xml_file(filepath: str) -> dict | None:
    """Parse an individual Crestron Mobile XML subpage or page."""
    try:
        tree = ET.parse(filepath)
        root = tree.getroot()
    except Exception as err:
        return None

    # Get page name
    control_elem = root.find(".//Control[@Name]")
    page_name = control_elem.get("Name", "") if control_elem is not None else ""
    if not page_name:
        page_name = os.path.splitext(os.path.basename(filepath))[0]

    # Clean up name: e.g. "[Living Room] [Art] Control" -> "Living Room Art"
    clean_name = re.sub(r"[\[\]]", " ", page_name).strip()
    clean_name = re.sub(r"\s+", " ", clean_name)
    clean_name = re.sub(r"\s+Control(-\d+)?$", "", clean_name, flags=re.I).strip()

    # Find digital joins
    digital_joins = []
    for cmd in root.findall(".//Command[@Type='Digital']"):
        jid = cmd.get("Id")
        action = cmd.get("Action")
        if jid and jid.isdigit():
            digital_joins.append((int(jid), action))

    # Find analog joins
    analog_joins = []
    for cmd in root.findall(".//Command[@Type='Analog']"):
        jid = cmd.get("Id")
        if jid and jid.isdigit():
            analog_joins.append(int(jid))

    unique_digitals = []
    seen = set()
    for jid, act in digital_joins:
        if jid not in seen:
            seen.add(jid)
            unique_digitals.append(jid)

    unique_analogs = sorted(list(set(analog_joins)))

    return {
        "raw_name": page_name,
        "clean_name": clean_name,
        "digital_joins": unique_digitals,
        "analog_joins": unique_analogs,
    }


def analyze_project(folder_path: str):
    """Analyze all XML files in a folder and generate HA YAML."""
    lights = []
    covers = []

    for fname in sorted(os.listdir(folder_path)):
        if not fname.endswith(".xml") or "Manifest" in fname or "Resource" in fname:
            continue

        res = parse_xml_file(os.path.join(folder_path, fname))
        if not res:
            continue

        cname = res["clean_name"]
        d_joins = res["digital_joins"]
        a_joins = res["analog_joins"]

        # Check if it is a cover/shade (has analog slider or shade/drape keywords)
        is_cover = bool(a_joins) or any(
            kw in cname.lower() for kw in ["shade", "drape", "blind", "curtain", "window"]
        )

        if is_cover and a_joins:
            analog_j = a_joins[0]
            # Heuristic for open/close/stop from digital joins if present
            open_j = d_joins[1] if len(d_joins) > 1 else None
            close_j = d_joins[0] if len(d_joins) > 0 else None
            stop_j = d_joins[2] if len(d_joins) > 2 else None
            covers.append(
                {
                    "name": cname,
                    "analog_join": analog_j,
                    "open_join": open_j,
                    "close_join": close_j,
                    "stop_join": stop_j,
                }
            )
        elif d_joins:
            # It's a light or switch
            # In standard Crestron D3Pro mobile templates:
            # button order in XML is usually: Down, Toggle, Up
            if len(d_joins) == 3:
                dn_j, tog_j, up_j = d_joins[0], d_joins[1], d_joins[2]
            elif len(d_joins) == 1:
                tog_j, up_j, dn_j = d_joins[0], None, None
            else:
                tog_j = d_joins[0]
                up_j = d_joins[1] if len(d_joins) > 1 else None
                dn_j = d_joins[2] if len(d_joins) > 2 else None

            lights.append(
                {
                    "name": cname,
                    "toggle_join": tog_j,
                    "up_join": up_j,
                    "down_join": dn_j,
                }
            )

    # Print YAML configuration
    print("\n# ==================================================================")
    print("# Auto-Generated Home Assistant Configuration for Crestron Mobile EXML")
    print("# Copy and paste this block into your configuration.yaml")
    print("# ==================================================================\n")
    print("crestron_mobile_exml:")
    print("  host: YOUR_CRESTRON_IP   # e.g. 192.168.1.50")
    print("  port: 41790")
    print('  passcode: "1234"           # Mobile G password in Crestron SIMPL\n')

    if lights:
        print("  lights:")
        for l in lights:
            print(f'    - name: "{l["name"]}"')
            print(f'      toggle_join: {l["toggle_join"]}')
            if l["up_join"] and l["down_join"]:
                print(f'      up_join: {l["up_join"]}')
                print(f'      down_join: {l["down_join"]}')
                print("      ramp_time: 5.0")
            print()

    if covers:
        print("  covers:")
        for c in covers:
            print(f'    - name: "{c["name"]}"')
            print(f'      analog_join: {c["analog_join"]}')
            if c["open_join"]:
                print(f'      open_join: {c["open_join"]}')
            if c["close_join"]:
                print(f'      close_join: {c["close_join"]}')
            if c["stop_join"]:
                print(f'      stop_join: {c["stop_join"]}')
            print()


def main():
    parser = argparse.ArgumentParser(
        description="Extract joins from Crestron Mobile XML project files."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dir", help="Path to directory containing Crestron XML files")
    group.add_argument("--zip", help="Path to Crestron iPad Project .zip file")

    args = parser.parse_args()

    if args.zip:
        tmp_dir = "/tmp/crestron_xml_extract"
        os.makedirs(tmp_dir, exist_ok=True)
        with zipfile.ZipFile(args.zip, "r") as z:
            z.extractall(tmp_dir)
        analyze_project(tmp_dir)
    elif args.dir:
        analyze_project(args.dir)


if __name__ == "__main__":
    main()
