#!/usr/bin/env python3

import os
import random
import subprocess
import time
from pathlib import Path
import mido
from tqdm import tqdm

MIDI_DIR = "/media/tlongino/Rocinante/Music/video-game-music-90000-midi-files"
SOUNDFONT = "/usr/share/sounds/sf2/FluidR3_GM.sf2"

# ANSI color codes
LIGHT_BLUE = "\033[1;94m"  # Bold light blue for title
CYAN = "\033[36m"          # Cyan for progress bar
RESET = "\033[0m"

def check_setup():
    if not os.path.isfile(SOUNDFONT):
        print(f"❌ Error: SoundFont not found at {SOUNDFONT}")
        exit(1)
    if not os.path.isdir(MIDI_DIR):
        print(f"❌ Error: MIDI directory not found at {MIDI_DIR}")
        exit(1)

def get_duration(file_path):
    try:
        mid = mido.MidiFile(file_path)
        duration = mid.length  # Duration in seconds, accounting for tempo
        return int(duration)
    except Exception as e:
        print(f"⚠️ Warning: Couldn’t determine duration for {file_path}, defaulting to 120s ({e})")
        return 120

def play_midi(file_path):
    print(f"\n🎵 Now Playing: {LIGHT_BLUE}{os.path.basename(file_path)}{RESET}")
    duration = get_duration(file_path)
    total_time = f"{duration // 60}:{duration % 60:02d}"
    print(f"Duration: {total_time}")

    cmd = ["timidity", "-x", f"soundfont {SOUNDFONT}", "-o", "alsa", "-s", "44100", "-B2,8", file_path]
    process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    with tqdm(total=duration, desc="Progress", unit="s", 
              bar_format=f"{CYAN}{{l_bar}}{{bar}}{RESET}| {{n_fmt}}/{{total_fmt}}") as pbar:
        elapsed = 0
        while process.poll() is None and elapsed < duration:
            time.sleep(0.5)
            elapsed += 0.5
            pbar.update(0.5)
        process.wait()

def main():
    check_setup()
    midi_files = list(Path(MIDI_DIR).rglob("*.mid"))
    if not midi_files:
        print("❌ No MIDI files found in", MIDI_DIR)
        exit(1)
    random.shuffle(midi_files)
    print(f"Found {len(midi_files)} MIDI files to play.")
    
    try:
        for file in midi_files:
            play_midi(str(file))
    except KeyboardInterrupt:
        print("\n🛑 Stopping playback...")
        subprocess.run(["pkill", "-9", "timidity"])

if __name__ == "__main__":
    main()
