#!/usr/bin/env python3

import os
import random
import subprocess
import time
from pathlib import Path
import mido
from tqdm import tqdm
import requests
import tkinter as tk
from PIL import Image, ImageTk
from io import BytesIO
import re
import json
import tkinter.ttk as ttk

SOUNDFONT = "/usr/share/sounds/sf2/FluidR3_GM.sf2"
IGDB_API_URL = "https://api.igdb.com/v4/games"
BOX_ART_WIDTH = 640

# Load config from config.json
def load_config():
    config_path = Path(__file__).parent / "config.json"
    try:
        with open(config_path) as f:
            config = json.load(f)
            client_id = config.get("client_id") or config.get("IGDB_CLIENT_ID")
            access_token = config.get("access_token") or config.get("IGDB_ACCESS_TOKEN")
            
            if not client_id or not access_token:
                print("⚠️ Warning: Missing IGDB credentials in config.json")
                print("Please ensure your config.json contains:")
                print('{\n  "client_id": "your_client_id",\n  "access_token": "your_access_token",\n  "midi_dir": "your_midi_dir"\n}')
                return None
                
            return {
                "client_id": client_id,
                "access_token": access_token,
                "midi_dir": config.get("midi_dir") or config.get("MIDI_DIR", os.path.expanduser("~/Music"))
            }
    except FileNotFoundError:
        print("⚠️ Error: config.json not found")
        print("Please create a config.json file in the same directory as midiplay.py with your IGDB credentials:")
        print('{\n  "client_id": "your_client_id",\n  "access_token": "your_access_token",\n  "midi_dir": "your_midi_dir"\n}')
        return None
    except json.JSONDecodeError:
        print("⚠️ Error: config.json is not valid JSON")
        return None

# ANSI color codes
LIGHT_BLUE = "\033[1;94m"  # Bold light blue for title
CYAN = "\033[36m"          # Cyan for progress bar
RESET = "\033[0m"

def check_setup():
    if not os.path.isfile(SOUNDFONT):
        print(f"❌ Error: SoundFont not found at {SOUNDFONT}")
        exit(1)
    
    config = load_config()
    if not config:
        print("⚠️ Skipping setup due to missing config")
        exit(1)
    
    midi_dir = Path(config["midi_dir"])
    print(f"🔍 Looking for MIDI files in: {midi_dir}")
    
    if not midi_dir.exists():
        print(f"❌ Error: MIDI directory not found at {midi_dir}")
        print("💡 Tip: Make sure the path in config.json is correct and the directory exists")
        print(f"Current working directory: {os.getcwd()}")
        exit(1)
    
    # Check if there are any MIDI files in the directory or its subdirectories
    print("🔍 Searching for MIDI files...")
    
    # First, list all VGM directories to make sure we're searching everywhere
    vgm_dirs = list(midi_dir.glob("VGM - *"))
    print(f"📂 Found {len(vgm_dirs)} VGM directories:")
    for vgm_dir in vgm_dirs:
        print(f"  - {vgm_dir.name}")
    
    midi_files = []
    for vgm_dir in vgm_dirs:
        dir_files = list(vgm_dir.rglob("*.mid"))
        print(f"  Found {len(dir_files)} files in {vgm_dir.name}")
        midi_files.extend(dir_files)
    
    if not midi_files:
        print(f"❌ Error: No MIDI files found in {midi_dir} or its subdirectories")
        print("💡 Tip: Make sure the directory contains .mid files")
        exit(1)
    
    print(f"✅ Found {len(midi_files)} total MIDI files")
    print(f"📂 First few files found:")
    for file in midi_files[:5]:
        print(f"  - {file}")
    
    return midi_dir

def get_duration(file_path):
    try:
        mid = mido.MidiFile(file_path)
        if mid.length > 0:
            return int(mid.length)
            
        # If mido.length fails, calculate manually from ticks
        total_ticks = 0
        for track in mid.tracks:
            track_ticks = 0
            for msg in track:
                track_ticks += msg.time
            total_ticks = max(total_ticks, track_ticks)
            
        # Convert ticks to seconds using tempo
        tempo = 500000  # Default tempo (120 BPM)
        for track in mid.tracks:
            for msg in track:
                if msg.type == 'set_tempo':
                    tempo = msg.tempo
                    break
            if tempo != 500000:  # Stop if we found a non-default tempo
                break
                
        seconds = total_ticks * tempo / (mid.ticks_per_beat * 1000000)
        return int(seconds)
    except Exception as e:
        print(f"⚠️ Warning: Couldn't determine duration for {file_path}, defaulting to 120s ({e})")
        return 120

class GameDisplay:
    def __init__(self):
        self.window = tk.Tk()
        self.window.title("Now Playing")
        self.window.configure(bg='#1e1e1e')  # Dark background
        
        # Set minimum window size to prevent resizing issues
        self.window.minsize(BOX_ART_WIDTH, BOX_ART_WIDTH + 100)  # Height includes space for text
        
        # Create a frame with dark background
        self.frame = tk.Frame(self.window, bg='#1e1e1e')
        self.frame.pack(fill=tk.BOTH, expand=True)
        
        # Fixed-size image container (even when no image)
        self.image_container = tk.Frame(self.frame, width=BOX_ART_WIDTH, height=BOX_ART_WIDTH, bg='#2d2d2d')
        self.image_container.pack(pady=10)
        self.image_container.pack_propagate(False)  # Prevent container from shrinking
        
        self.image_label = tk.Label(self.image_container, bg='#2d2d2d')
        self.image_label.pack(expand=True)
        
        # Title with dark theme
        self.title_label = tk.Label(self.frame, 
                                  font=("Arial", 12, "bold"),
                                  fg='#ffffff',  # White text
                                  bg='#1e1e1e',  # Dark background
                                  wraplength=BOX_ART_WIDTH)
        self.title_label.pack(pady=5)
        
        # Progress frame
        self.progress_frame = tk.Frame(self.frame, bg='#1e1e1e')
        self.progress_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Progress bar
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(self.progress_frame, 
                                             variable=self.progress_var,
                                             mode='determinate',
                                             length=BOX_ART_WIDTH - 20)
        self.progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Time label
        self.time_label = tk.Label(self.frame,
                                 text="0:00 / 0:00",
                                 fg='#ffffff',  # White text
                                 bg='#1e1e1e')
        self.time_label.pack(pady=5)
        
    def update_display(self, image_url, title):
        self.title_label.configure(text=title)
        
        try:
            if image_url:
                response = requests.get(image_url)
                img = Image.open(BytesIO(response.content))
                # Maintain aspect ratio while fitting in container
                img.thumbnail((BOX_ART_WIDTH, BOX_ART_WIDTH))
                photo = ImageTk.PhotoImage(img)
                self.image_label.configure(image=photo)
                self.image_label.image = photo
            else:
                # Clear the image but maintain the space
                self.image_label.configure(image='')
        except Exception as e:
            print(f"⚠️ Warning: Failed to load image: {e}")
            self.image_label.configure(image='')
        
        self.window.update()
    
    def update_progress(self, current, total):
        # Update progress bar
        progress_percent = (current / total) * 100
        self.progress_var.set(progress_percent)
        
        # Update time label
        current_time = f"{int(current/60)}:{int(current%60):02d}"
        total_time = f"{int(total/60)}:{int(total%60):02d}"
        self.time_label.configure(text=f"{current_time} / {total_time}")
        
        self.window.update()

def get_igdb_box_art(game_name):
    config = load_config()
    if not config:
        print("⚠️ Skipping box art fetch due to missing config")
        return None

    # Clean up the filename to get a better search query
    search_query = re.sub(r'\.mid$', '', game_name)  # Remove .mid extension
    search_query = re.sub(r'[_-]', ' ', search_query)  # Replace underscores and hyphens with spaces
    
    # Extract game name from path structure
    match = re.search(r'/([^/]+?)(?:\s*-\s*[^/]*)*\.mid$', game_name)
    if match:
        game_title = match.group(1)
        # Clean up the game title
        game_title = re.sub(r'\([^)]*\)', '', game_title)  # Remove parentheses and their contents
        game_title = re.sub(r'\s+-\s+.*$', '', game_title)  # Remove everything after a dash
        game_title = game_title.strip()
        search_query = game_title
    
    print(f"🎮 Searching IGDB for: {search_query}")
    
    headers = {
        'Client-ID': config["client_id"],
        'Authorization': f'Bearer {config["access_token"]}'
    }
    
    # First try to get the game info
    game_data = f'''
    search "{search_query}";
    fields name,cover.url,screenshots.*,artworks.*;
    limit 1;
    '''
    
    try:
        print("📡 Connecting to IGDB API...")
        print(f"📡 Using Client-ID: {config['client_id'][:8]}...")  # Show first 8 chars only
        response = requests.post(IGDB_API_URL, headers=headers, data=game_data)
        print(f"📡 API Response Status: {response.status_code}")
        
        if response.status_code == 401:
            print("❌ Authentication failed. Please check your IGDB credentials.")
            print("Make sure your config.json has valid credentials and the access_token is an App Access Token, not a Client Secret")
            print(f"Response: {response.text}")
            return None
        elif response.status_code != 200:
            print(f"❌ API request failed with status {response.status_code}")
            print(f"Response: {response.text}")
            return None
        
        games = response.json()
        if games:
            game = games[0]
            print(f"✅ Found game: {game.get('name', 'Unknown')}")
            
            # Try cover art first
            if 'cover' in game:
                cover_url = game['cover']['url'].replace('t_thumb', 't_cover_big')
                print(f"📸 Found cover art: {cover_url}")
                return f"https:{cover_url}"
            
            # Try screenshots next
            if 'screenshots' in game and game['screenshots']:
                screenshot_url = game['screenshots'][0]['url'].replace('t_thumb', 't_screenshot_huge')
                print(f"📸 Found screenshot: {screenshot_url}")
                return f"https:{screenshot_url}"
            
            # Try artwork as last resort
            if 'artworks' in game and game['artworks']:
                artwork_url = game['artworks'][0]['url'].replace('t_thumb', 't_cover_big')
                print(f"📸 Found artwork: {artwork_url}")
                return f"https:{artwork_url}"
            
            print("❌ No images found for this game")
        else:
            print("❌ No games found matching this title")
            print(f"Raw Response: {response.text}")
    except requests.exceptions.RequestException as e:
        print(f"⚠️ Network error while fetching game images: {e}")
    except Exception as e:
        print(f"⚠️ Unexpected error while fetching game images: {e}")
    
    return None

def play_midi(file_path, display):
    print(f"\n🎵 Now Playing: {LIGHT_BLUE}{os.path.basename(file_path)}{RESET}")
    duration = get_duration(file_path)
    total_time = f"{duration // 60}:{duration % 60:02d}"
    print(f"Duration: {total_time}")

    # Initialize display first
    display.update_display(None, os.path.basename(file_path))
    display.update_progress(0, duration)
    
    # Start playing the MIDI file
    cmd = ["timidity", "-x", f"soundfont {SOUNDFONT}", "-o", "alsa", "-s", "44100", "-B2,8", file_path]
    process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # Now fetch the box art while the music is playing
    box_art_url = get_igdb_box_art(str(file_path))
    if box_art_url:
        display.update_display(box_art_url, os.path.basename(file_path))
    
    # Progress bar using tqdm
    start_time = time.time()
    with tqdm(total=duration, bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt}') as pbar:
        while process.poll() is None:
            elapsed = int(time.time() - start_time)
            if elapsed >= duration:
                break
            pbar.n = elapsed
            pbar.refresh()
            display.update_progress(elapsed, duration)
            time.sleep(0.5)
    process.wait()

def main():
    midi_dir = check_setup()
    midi_files = []
    for vgm_dir in list(midi_dir.glob("VGM - *")):
        dir_files = list(vgm_dir.rglob("*.mid"))
        midi_files.extend(dir_files)
    
    print(f"Found {len(midi_files)} MIDI files in {midi_dir} and its subdirectories.")
    
    random.shuffle(midi_files)
    display = GameDisplay()
    
    try:
        for file in midi_files:
            play_midi(str(file), display)
    except KeyboardInterrupt:
        print("\n🛑 Stopping playback...")
        subprocess.run(["pkill", "-9", "timidity"])
    finally:
        display.window.destroy()

if __name__ == "__main__":
    main()
