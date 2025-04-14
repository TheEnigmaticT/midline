#!/usr/bin/env python3

import os
# import random # Not needed for this MVP
# import subprocess # Not needed for this MVP
import time
from pathlib import Path
# import mido # Not needed for this MVP
# import requests # Keep for images
import tkinter as tk
from PIL import Image, ImageTk
from io import BytesIO
import re
import json
import tkinter.ttk as ttk
# import signal # Not needed for this MVP

# --- New Imports for Visualizer ---
import math
import colorsys # For HSV/HSL color manipulation

# --- Constants ---
# SOUNDFONT = "/usr/share/sounds/sf2/FluidR3_GM.sf2" # Not needed for MVP
IGDB_API_URL = "https://api.igdb.com/v4/games"
BOX_ART_WIDTH = 320 # Reduced size slightly for testing layout
BOX_ART_HEIGHT = 320

# --- Visualizer Constants ---
NUM_BINS = 90          # Number of frequency bins/lines to draw
UPDATE_MS = 33         # Target update interval (~30 FPS)
SWEEP_PERIOD_S = 5.0   # Time for the fake peak to sweep back and forth
INNER_RADIUS_FRAC = 0.35 # Inner radius as fraction of canvas width/2
OUTER_RADIUS_FRAC = 0.48 # Outer radius (max length) as fraction of width/2
LINE_WIDTH = 3


# --- Config Loading & Setup (Keep relevant parts) ---
def load_config():
    # ... (Keep existing load_config - needed for IGDB / image loading) ...
    config_path = Path(__file__).parent / "config.json"
    try:
        with open(config_path) as f:
            config = json.load(f)
            # Only need image stuff for this MVP test
            client_id = config.get("client_id") or config.get("IGDB_CLIENT_ID")
            access_token = config.get("access_token") or config.get("IGDB_ACCESS_TOKEN")
            # midi_dir = config.get("midi_dir") ... # Not needed

            # Assuming IGDB might still be wanted for a placeholder image
            if not client_id or not access_token:
                print("⚠️ Warning: Missing IGDB credentials in config.json (needed for image test)")
                # return None # Allow running without it for vis test
            return { "client_id": client_id, "access_token": access_token }
    except Exception as e:
        print(f"Error loading config: {e}")
        return None

# Removed check_setup, get_duration, ANSI colors, get_igdb_box_art (or keep get_igdb if you want placeholder art)
# Simplified get_igdb_box_art if kept:
def get_placeholder_art(config):
     # Minimal fetch just to have an image if config is present
     if not config or not config.get("client_id") or not config.get("access_token"): return None
     headers = {"Client-ID": config["client_id"], "Authorization": f'Bearer {config["access_token"]}'}
     # Search for a common game like "Mario" just to get *an* image
     game_data = f'search "mario"; fields cover.url; limit 1;'
     try:
        response = requests.post(IGDB_API_URL, headers=headers, data=game_data, timeout=5)
        response.raise_for_status()
        games = response.json()
        if games and "cover" in games[0] and games[0]["cover"]:
             url = games[0]["cover"]["url"].replace("t_thumb", "t_cover_big")
             if url.startswith("//"): url = "https:" + url
             print(f"Using placeholder art URL: {url}")
             return url
     except Exception as e: print(f"Could not fetch placeholder art: {e}")
     return None


class GameDisplay:
    def __init__(self, config, on_close_callback=None): # Removed play_stop_callback
        self.window = tk.Tk()
        self.window.title("Visualizer MVP Test")
        self.window.geometry("600x750") # Give it a defined size
        self.window.configure(bg="#1e1e1e")

        # --- Create Canvas for Visualizer (behind everything else) ---
        self.canvas_bg = "#1e1e1e"
        self.canvas = tk.Canvas(self.window, bg=self.canvas_bg, highlightthickness=0)
        # Place it to fill the window initially
        self.canvas.place(relx=0, rely=0, relwidth=1.0, relheight=1.0)
        # Get canvas size later in update_visualizer or bind to resize

        # --- Frame for Content (on top of canvas) ---
        # Make frame background transparent by setting its color to canvas color
        self.content_frame = tk.Frame(self.window, bg=self.canvas_bg)
        # Place frame centered, leaving space around it maybe? Or fill? Let's center content.
        self.content_frame.place(relx=0.5, rely=0.5, anchor=tk.CENTER)


        # --- Image Container (inside content_frame) ---
        self.image_container = tk.Frame(self.content_frame, width=BOX_ART_WIDTH, height=BOX_ART_HEIGHT, bg="#2d2d2d") # Give it a background
        self.image_container.pack(pady=10) # Pack inside the content frame
        self.image_container.pack_propagate(False)

        self.image_label = tk.Label(self.image_container, bg="#2d2d2d")
        self.image_label.pack(expand=True)

        # --- Labels, Progress Bar (Inside content_frame) ---
        self.title_label = tk.Label(self.content_frame, text="Visualizer Test", font=("Arial", 12, "bold"), fg="#ffffff", bg=self.canvas_bg)
        self.title_label.pack(pady=5)

        # Placeholder progress/time - not updated in this MVP
        self.progress_frame = tk.Frame(self.content_frame, bg=self.canvas_bg)
        self.progress_frame.pack(fill=tk.X, padx=10, pady=5)
        self.progress_var = tk.DoubleVar(value=50) # Dummy value
        self.progress_bar = ttk.Progressbar(self.progress_frame, variable=self.progress_var, mode="determinate", length=BOX_ART_WIDTH - 20)
        self.progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.time_label = tk.Label(self.content_frame, text="0:30 / 1:00", fg="#ffffff", bg=self.canvas_bg)
        self.time_label.pack(pady=5)

        # Dummy button - not functional for audio
        self.play_stop_button = tk.Button(self.content_frame, text="Play", bg="#333333", fg="#ffffff", width=8)
        self.play_stop_button.pack(pady=10)


        self.on_close_callback = on_close_callback
        self.window.protocol("WM_DELETE_WINDOW", self.on_window_close)

        # --- Visualizer State ---
        self.vis_data = [0.0] * NUM_BINS
        self.vis_update_job = None

        # --- Load Placeholder Image ---
        placeholder_url = get_placeholder_art(config)
        self.update_display(placeholder_url, "Visualizer Test")

        # --- Start the Visualizer Animation ---
        # Schedule the first call slightly later to allow window init
        self.window.after(100, self.start_visualizer_loop)


    def generate_fake_data(self):
        """Generates a fake spectrum with a peak sweeping back and forth."""
        current_time = time.time()
        # Create value oscillating between 0 and 1 over the period
        oscillation = (math.sin(current_time * 2 * math.pi / SWEEP_PERIOD_S) + 1) / 2.0
        peak_index = int(oscillation * (NUM_BINS - 1))

        data = [0.0] * NUM_BINS
        # Simple peak with falloff
        data[peak_index] = 1.0
        if peak_index > 0:
            data[peak_index - 1] = 0.5
        if peak_index < NUM_BINS - 1:
            data[peak_index + 1] = 0.5
        # Maybe add tiny noise floor?
        # data = [max(d, 0.05) for d in data]
        return data


    def update_visualizer(self):
        """Clears canvas and redraws visualizer based on self.vis_data."""
        self.canvas.delete("vis_line") # Clear only visualizer lines using tags

        try:
             # Get current canvas size for centering
             canvas_width = self.canvas.winfo_width()
             canvas_height = self.canvas.winfo_height()
             if canvas_width < 50 or canvas_height < 50: # Avoid drawing if canvas not ready
                 # print("DEBUG: Canvas too small, skipping draw.")
                 return
             center_x = canvas_width / 2
             center_y = canvas_height / 2 # Center vertically too
             max_dimension = min(canvas_width, canvas_height) # Base radii on smallest dimension
             r_inner = max_dimension / 2 * INNER_RADIUS_FRAC
             r_outer_max = max_dimension / 2 * OUTER_RADIUS_FRAC
             length_scale = r_outer_max - r_inner # Max length of a bar
        except tk.TclError: # Handle cases where widget might be destroyed during update
             # print("DEBUG: TclError getting canvas size.")
             return
        except Exception as e: # Catch other potential errors during calculation
             print(f"DEBUG: Error during size/radii calculation: {e}")
             return

        # --- Loop through data and draw lines ---
        for i, magnitude in enumerate(self.vis_data):
            if magnitude < 0.01: # Don't draw tiny lines
                 continue

            try:
                # Angle sweeps from 0 (right) counter-clockwise
                angle = (i / NUM_BINS) * 2 * math.pi

                # Calculate start and end points
                start_x = center_x + r_inner * math.cos(angle)
                start_y = center_y + r_inner * math.sin(angle)
                current_length = length_scale * min(magnitude, 1.0) # Cap magnitude at 1
                end_x = center_x + (r_inner + current_length) * math.cos(angle)
                end_y = center_y + (r_inner + current_length) * math.sin(angle)

                # Calculate color (HSV -> RGB)
                hue = i / NUM_BINS # Varies hue around the circle
                saturation = 0.8 + magnitude * 0.2 # Slightly desaturate quiet bars?
                value = 0.6 + magnitude * 0.4     # Dim quiet bars? Or keep bright (1.0)?
                rgb = colorsys.hsv_to_rgb(hue, saturation, value)
                # Convert 0-1 RGB to #RRGGBB hex format
                color_hex = "#{:02x}{:02x}{:02x}".format(
                    int(rgb[0] * 255), int(rgb[1] * 255), int(rgb[2] * 255)
                )

                # --- Check coordinates before drawing ---
                coords = (start_x, start_y, end_x, end_y)
                if not all(isinstance(c, (int, float)) and math.isfinite(c) for c in coords):
                     # print(f"DEBUG: Invalid coords for bin {i}: {coords}")
                     continue # Skip drawing this line

                # --- Draw the actual line ---
                self.canvas.create_line(
                    coords, # Pass coordinates as a tuple or list
                    fill=color_hex,
                    width=LINE_WIDTH,
                    tags="vis_line" # Use tag for easy clearing
                )
            except Exception as e:
                 print(f"DEBUG: Error drawing line for bin {i}: {e}")
                 # Continue to next bin if one line fails

    def animate_visualizer(self):
        """Generates new data and schedules the next update."""
        # print(f"DEBUG: animate_visualizer called at {time.time()}") # Add this
        self.vis_data = self.generate_fake_data()
        self.update_visualizer()
        # Schedule the next call
        self.vis_update_job = self.window.after(UPDATE_MS, self.animate_visualizer)

    def start_visualizer_loop(self):
        print("Starting visualizer animation loop...")
        # Stop existing job if any
        if self.vis_update_job:
            self.window.after_cancel(self.vis_update_job)
            self.vis_update_job = None
        # Start the loop
        self.animate_visualizer()


    def update_display(self, image_url, title):
        """Loads image (if URL provided) and sets title."""
        self.title_label.configure(text=title or "---")
        try:
            if image_url:
                # Basic image loading from URL (replace with your more robust version if needed)
                response = requests.get(image_url, timeout=10); response.raise_for_status()
                img_data = response.content
                img = Image.open(BytesIO(img_data))
                img.thumbnail((BOX_ART_WIDTH, BOX_ART_HEIGHT)) # Use constants
                photo = ImageTk.PhotoImage(img)
                self.image_label.configure(image=photo)
                self.image_label.image = photo
            else:
                self.image_label.configure(image="")
                self.image_label.image = None
        except Exception as e:
            print(f"⚠️ Img Load Error: {e}")
            self.image_label.configure(image=""); self.image_label.image = None


    def on_window_close(self):
        print("🚪 Window close requested...")
        # Stop the visualizer loop
        if self.vis_update_job:
            self.window.after_cancel(self.vis_update_job)
            self.vis_update_job = None
            print("Visualizer loop stopped.")
        # Call original callback if it exists (it doesn't in this MVP)
        # if self.on_close_callback: self.on_close_callback()
        self.window.destroy() # Destroy window on close

# --- Main Execution ---
def main():
    config = load_config() # Load config for placeholder art potentially

    # Create the display instance
    display = GameDisplay(config=config) # Pass config

    # Start the Tkinter main loop - the visualizer runs via window.after
    print("Starting Tkinter main loop...")
    display.window.mainloop()
    print("Exiting.")


if __name__ == "__main__":
    main()