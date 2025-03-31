#!/usr/bin/env python3

import os
import random
import subprocess
import time
from pathlib import Path
import mido
import requests
import tkinter as tk
from PIL import Image, ImageTk
from io import BytesIO
import re
import json
import tkinter.ttk as ttk
import signal

# --- Constants and Setup Functions (Keep previous versions) ---
SOUNDFONT = "/usr/share/sounds/sf2/FluidR3_GM.sf2"
IGDB_API_URL = "https://api.igdb.com/v4/games"
BOX_ART_WIDTH = 640
LIGHT_BLUE = "\033[1;94m"
CYAN = "\033[36m"
RESET = "\033[0m"

def load_config():
    # ... (Keep existing load_config)
    config_path = Path(__file__).parent / "config.json"
    try:
        with open(config_path) as f:
            config = json.load(f)
            client_id = config.get("client_id") or config.get("IGDB_CLIENT_ID")
            access_token = config.get("access_token") or config.get("IGDB_ACCESS_TOKEN")

            if not client_id or not access_token:
                print("⚠️ Warning: Missing IGDB credentials in config.json")
                return None

            return {
                "client_id": client_id,
                "access_token": access_token,
                "midi_dir": config.get("midi_dir") or config.get("MIDI_DIR", os.path.expanduser("~/Music")),
            }
    except FileNotFoundError:
        print("⚠️ Error: config.json not found")
        return None
    except json.JSONDecodeError:
        print("⚠️ Error: config.json is not valid JSON")
        return None

def check_setup():
    # ... (Keep existing check_setup, ensure it returns midi_files)
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
        exit(1)

    print("🔍 Searching for MIDI files...")
    vgm_dirs = list(midi_dir.glob("VGM - *"))
    midi_files = []
    if vgm_dirs:
        print(f"📂 Found {len(vgm_dirs)} VGM directories.")
        for vgm_dir in vgm_dirs:
            dir_files = list(vgm_dir.rglob("*.mid"))
            midi_files.extend(dir_files)
    else:
        print(f"⚠️ No 'VGM - *' directories found directly under {midi_dir}. Searching all subdirectories.")
        midi_files = list(midi_dir.rglob("*.mid"))


    if not midi_files:
        print(f"❌ Error: No MIDI files found in {midi_dir} or its subdirectories")
        exit(1)

    print(f"✅ Found {len(midi_files)} total MIDI files")
    random.shuffle(midi_files) # Shuffle here once
    print(" Playlist shuffled.")
    return midi_dir, config, midi_files

def get_duration(file_path):
    # ... (Keep existing get_duration)
    try:
        mid = mido.MidiFile(file_path)
        if mid.length > 0:
            return int(mid.length)
        # Fallback calculation (simplified)
        total_time = sum(msg.time for track in mid.tracks for msg in track if not msg.is_meta)
        tempo = 500000
        ticks_per_beat = mid.ticks_per_beat if mid.ticks_per_beat else 480
        for track in mid.tracks:
             for msg in track:
                 if msg.type == 'set_tempo':
                     tempo = msg.tempo
                     break
             else: continue
             break
        seconds = mido.tick2second(total_time, ticks_per_beat, tempo)
        return int(seconds)

    except Exception as e:
        print(f"⚠️ Warning: Couldn't determine duration for {file_path}, defaulting to 120s ({e})")
        return 120

# --- GameDisplay Class (largely same as previous Play/Stop version) ---
class GameDisplay:
    def __init__(self, on_close_callback=None, play_stop_callback=None):
        self.window = tk.Tk()
        self.window.title("Now Playing (Continuous Toggle)") # Updated title
        self.window.configure(bg="#1e1e1e")
        self.window.minsize(BOX_ART_WIDTH, BOX_ART_WIDTH + 150)

        self.frame = tk.Frame(self.window, bg="#1e1e1e")
        self.frame.pack(fill=tk.BOTH, expand=True)

        self.image_container = tk.Frame(self.frame, width=BOX_ART_WIDTH, height=BOX_ART_WIDTH, bg="#2d2d2d")
        self.image_container.pack(pady=10)
        self.image_container.pack_propagate(False)
        self.image_label = tk.Label(self.image_container, bg="#2d2d2d")
        self.image_label.pack(expand=True)

        self.title_label = tk.Label(self.frame, font=("Arial", 12, "bold"), fg="#ffffff", bg="#1e1e1e", wraplength=BOX_ART_WIDTH)
        self.title_label.pack(pady=5)

        self.progress_frame = tk.Frame(self.frame, bg="#1e1e1e")
        self.progress_frame.pack(fill=tk.X, padx=10, pady=5)
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(self.progress_frame, variable=self.progress_var, mode="determinate", length=BOX_ART_WIDTH - 20)
        self.progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.time_label = tk.Label(self.frame, text="0:00 / 0:00", fg="#ffffff", bg="#1e1e1e")
        self.time_label.pack(pady=5)

        self.play_stop_button = tk.Button(self.frame, text="Play", command=self.handle_play_stop_click, bg="#333333", fg="#ffffff", activebackground="#555555", activeforeground="#ffffff", relief=tk.RAISED, borderwidth=2, width=8)
        self.play_stop_button.pack(pady=10)

        self._is_process_running = False # Internal state if timidity should be running
        self.process = None
        self.current_file_path = None
        self.on_close_callback = on_close_callback
        self.play_stop_callback = play_stop_callback

        self.window.protocol("WM_DELETE_WINDOW", self.on_window_close)

    def handle_play_stop_click(self):
        if self.play_stop_callback:
            # Pass internal state: is a process supposed to be running?
            self.play_stop_callback(self._is_process_running)

    def set_button_state(self, state):
        """Sets button text and internal process running flag."""
        if state == "Play":
            self.play_stop_button.config(text="Play", state=tk.NORMAL)
            self._is_process_running = False
        elif state == "Stop":
            self.play_stop_button.config(text="Stop", state=tk.NORMAL)
            self._is_process_running = True
        elif state == "Disabled":
            self.play_stop_button.config(text="Play", state=tk.DISABLED)
            self._is_process_running = False
        else:
            print(f"Warning: Invalid button state requested: {state}")

    def start_playback_process(self, file_path):
        if self.process and self.process.poll() is None:
            print("Warning: Start called when process already running. Stopping first.")
            self.stop_playback_process()

        self.current_file_path = file_path
        cmd = ["timidity", "-x", f"soundfont {SOUNDFONT}", "-o", "alsa", "-s", "44100", "-B2,8", self.current_file_path]
        try:
            self.process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            print(f"🚀 Started timidity process for: {os.path.basename(self.current_file_path)}")
            self._is_process_running = True # Mark process as active internally
            return True
        except FileNotFoundError:
             print("❌ Error: 'timidity' command not found.")
             self.process = None; self._is_process_running = False; return False
        except Exception as e:
            print(f"❌ Error starting timidity: {e}")
            self.process = None; self._is_process_running = False; return False

    def stop_playback_process(self):
        stopped = False
        if self.process and self.process.poll() is None:
            print(f"⏹️ Stopping timidity process for: {os.path.basename(self.current_file_path or 'Unknown')}")
            stopped = True
            try:
                self.process.terminate()
                try: self.process.wait(timeout=0.5)
                except subprocess.TimeoutExpired:
                    print("⏳ Timidity didn't terminate gracefully, sending SIGKILL.")
                    self.process.kill(); self.process.wait()
            except ProcessLookupError: print("🤔 Process already finished.")
            except Exception as e: print(f"⚠️ Error stopping timidity: {e}")
            self.process = None
        self._is_process_running = False # Mark process as inactive internally
        return stopped # Return True if a running process was actually stopped

    def update_display(self, image_url, title):
        # ... (Keep existing update_display)
        self.title_label.configure(text=title or "---")
        try:
            if image_url:
                response = requests.get(image_url, timeout=10); response.raise_for_status()
                img = Image.open(BytesIO(response.content)); img.thumbnail((BOX_ART_WIDTH, BOX_ART_WIDTH))
                photo = ImageTk.PhotoImage(img)
                self.image_label.configure(image=photo); self.image_label.image = photo
            else: self.image_label.configure(image=""); self.image_label.image = None
        except requests.exceptions.RequestException as e: print(f"⚠️ Img DL Error: {e}"); self.image_label.configure(image=""); self.image_label.image = None
        except Exception as e: print(f"⚠️ Img Load Error: {e}"); self.image_label.configure(image=""); self.image_label.image = None

    def update_progress(self, current, total):
        # ... (Keep existing update_progress)
        if total > 0: progress_percent = min(100, (current / total) * 100); self.progress_var.set(progress_percent)
        else: self.progress_var.set(0)
        current_time_str = f"{int(current // 60)}:{int(current % 60):02d}"
        total_time_str = f"{int(total // 60)}:{int(total % 60):02d}"
        self.time_label.configure(text=f"{current_time_str} / {total_time_str}")

    def on_window_close(self):
        print("🚪 Window close requested...")
        self.stop_playback_process()
        if self.on_close_callback:
            self.on_close_callback()

# --- get_igdb_box_art, cleanup_processes (Keep previous versions) ---
def get_igdb_box_art(config, game_name_from_path):
    # ... (Keep existing get_igdb_box_art)
    if not config: return None
    base_name = os.path.basename(game_name_from_path); search_query = re.sub(r"\.mid$", "", base_name); search_query = re.sub(r"[_-]", " ", search_query)
    path_parts = Path(game_name_from_path).parts; game_title_guess = ""
    if len(path_parts) > 1: parent_folder = path_parts[-2];
    if "vgm -" not in parent_folder.lower(): game_title_guess = parent_folder
    if not game_title_guess: game_title_guess = search_query
    game_title_guess = re.sub(r'\([^)]*\)', '', game_title_guess).strip(); game_title_guess = re.sub(r'\s+-\s+.*$', '', game_title_guess).strip()
    if len(game_title_guess) > 2: search_query = game_title_guess
    print(f"🎮 Guessing game title: '{search_query}'")
    headers = {"Client-ID": config["client_id"], "Authorization": f'Bearer {config["access_token"]}'}; game_data = f'search "{search_query}"; fields name, cover.url, screenshots.url, artworks.url; limit 1;'
    try:
        response = requests.post(IGDB_API_URL, headers=headers, data=game_data, timeout=10); response.raise_for_status()
        games = response.json()
        if games:
            game = games[0]; print(f"✅ Found IGDB game: {game.get('name', 'Unknown')}"); image_info = None; size = None
            if "cover" in game and game["cover"]: image_info, size = game["cover"], "t_cover_big"
            elif "screenshots" in game and game["screenshots"]: image_info, size = game["screenshots"][0], "t_screenshot_huge"
            elif "artworks" in game and game["artworks"]: image_info, size = game["artworks"][0], "t_screenshot_huge"
            if image_info and "url" in image_info:
                url = image_info["url"];
                if url.startswith("//"): url = "https:" + url
                url = url.replace("t_thumb", size); print(f"📸 Using image URL: {url}"); return url
            else: print(" GDB game found, but no suitable image URL.")
        else: print(f"❌ No games found on IGDB matching '{search_query}'")
    except requests.exceptions.Timeout: print("⚠️ IGDB request timed out.")
    except requests.exceptions.RequestException as e: print(f"⚠️ Network error fetching from IGDB: {e}")
    except json.JSONDecodeError: print(f"⚠️ Failed to decode IGDB response.")
    except Exception as e: print(f"⚠️ Unexpected error fetching game images: {e}")
    return None

def cleanup_processes():
    # ... (Keep existing cleanup_processes)
    print("\n🧹 Cleaning up any remaining timidity processes...")
    try:
        subprocess.run(["pkill", "-15", "timidity"], capture_output=True, text=True, check=False); time.sleep(0.2)
        subprocess.run(["pkill", "-9", "timidity"], capture_output=True, text=True, check=False); print("🧹 Cleanup complete.")
    except FileNotFoundError: print("⚠️ 'pkill' command not found.")
    except Exception as e: print(f"⚠️ Error during cleanup: {e}")

# --- Main Application Logic ---
# --- Main Application Logic ---
def main():
    # (Initial setup: check_setup, shuffle midi_files, state variables, callbacks...)
    midi_dir, config, midi_files = check_setup()
    if not midi_files: exit(1)

    current_index = 0
    main_window_closed = False
    continuous_play_enabled = False
    start_playback_requested = False
    stop_playback_requested = False

    def on_main_window_close(): nonlocal main_window_closed; print("Main window close requested."); main_window_closed = True
    def handle_play_stop_action(is_process_running):
        nonlocal continuous_play_enabled, start_playback_requested, stop_playback_requested
        if is_process_running: print("⏹️ Stop pressed."); continuous_play_enabled = False; stop_playback_requested = True
        else: print("▶️ Play pressed."); continuous_play_enabled = True; start_playback_requested = True

    display = GameDisplay(on_close_callback=on_main_window_close, play_stop_callback=handle_play_stop_action)
    display.set_button_state("Play")

    try:
        while current_index < len(midi_files) and not main_window_closed:
            # --- Prepare display for current track ---
            file_path = str(midi_files[current_index])
            base_name = os.path.basename(file_path)
            duration = get_duration(file_path)
            box_art_url = None # Reset for this track

            print(f"\n[{current_index + 1}/{len(midi_files)}] Preparing: {LIGHT_BLUE}{base_name}{RESET}")

            # 1. Clear old info, set title, reset progress
            display.update_display(None, base_name)
            display.update_progress(0, duration)

            # 2. *** Fetch and display box art UNCONDITIONALLY here ***
            #    (Do this *before* potentially waiting for user input)
            box_art_url = get_igdb_box_art(config, file_path)
            if box_art_url:
                display.update_display(box_art_url, base_name) # Update *with* new art if found

            # 3. Set initial button state based on mode before waiting/playing
            if continuous_play_enabled:
                display.set_button_state("Stop") # Expecting to play immediately
            else:
                display.set_button_state("Play") # Expecting to wait

            # 4. Update window to show the prepared state (title, art, button)
            display.window.update()

            # --- Wait for 'Play' if continuous mode is OFF ---
            start_playback_requested = False # Reset flag
            if not continuous_play_enabled:
                print(" Continuous play OFF. Waiting for Play command...")
                while not start_playback_requested and not main_window_closed:
                    if display.window.winfo_exists(): display.window.update()
                    else: main_window_closed = True; break
                    time.sleep(0.1)

            if main_window_closed: break
            # If we reach here, either continuous play is ON, or Play was just pressed.

            # --- Start Playback ---
            print(f" Attempting to start: {base_name}")
            success = display.start_playback_process(file_path)
            if not success:
                print(f"❌ Failed to start {base_name}. Stopping continuous play.")
                continuous_play_enabled = False # Turn off on error
                display.set_button_state("Play")
                current_index += 1 # Skip failed track
                continue # Go to next iteration

            # Playback started successfully
            display.set_button_state("Stop") # Ensure button is Stop

            # *** REMOVED redundant/conditional art fetch from here ***

            start_time = time.time()
            stop_playback_requested = False # Reset stop flag for this track

            # --- Monitoring Loop ---
            # (No changes needed in the monitoring loop itself)
            print(" Playback active. Monitoring...")
            playback_this_song_active = True
            while playback_this_song_active and not main_window_closed:
                 # (Check stop_requested, process_finished, elapsed, update UI...)
                 if stop_playback_requested: print(" Stop requested."); playback_this_song_active = False; break
                 current_time = time.time(); elapsed = current_time - start_time
                 process_finished = (display.process is None or display.process.poll() is not None)
                 if process_finished or elapsed >= duration:
                     if process_finished: print(" Process ended.")
                     else: print(" Duration reached.")
                     playback_this_song_active = False; break
                 if display.window.winfo_exists(): display.update_progress(elapsed, duration); display.window.update()
                 else: main_window_closed = True; break
                 time.sleep(0.1)


            # --- After Song Finishes or is Stopped ---
            # (No changes needed in the logic here regarding art)
            was_stopped_by_user = stop_playback_requested
            display.stop_playback_process()
            stop_playback_requested = False

            if main_window_closed: break

            if was_stopped_by_user:
                print(" Playback stopped by user command.")
                display.set_button_state("Play")
                # Stay on current_index
            else: # Song finished naturally
                print(" Song finished naturally.")
                current_index += 1 # Advance index
                if current_index >= len(midi_files):
                     # (Handle playlist end...)
                     print("\nPlaylist finished.")
                     continuous_play_enabled = False; display.set_button_state("Disabled")
                     display.update_display(None, "Playlist Finished"); display.update_progress(0,0); display.time_label.configure(text="")
                     while not main_window_closed:
                          if display.window.winfo_exists(): display.window.update()
                          else: main_window_closed = True
                          time.sleep(0.1)
                     break
                else: # More songs left
                    if continuous_play_enabled:
                        print(f" Continuous play ON. Moving to track {current_index + 1}")
                        display.set_button_state("Stop") # Ready for next track
                    else:
                        print(" Continuous play OFF. Ready for next track (requires Play).")
                        display.set_button_state("Play")

    # (except KeyboardInterrupt, tk.TclError, Exception...)
    # ...
    finally:
        # (Final cleanup...)
        print(" Final cleanup phase...")
        if 'display' in locals() and display and display.window.winfo_exists():
            display.stop_playback_process(); print(" Destroying Tkinter window."); display.window.destroy()
        cleanup_processes(); print("Exiting script.")

if __name__ == "__main__":
    main()