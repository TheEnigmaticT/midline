# mvp.py - Modified to play a MIDI file

import fluidsynth
import time
import mido # Import the mido library
import os

# --- Configuration ---
SOUNDFONT = "/usr/share/sounds/sf2/FluidR3_GM.sf2"
# Use the filename you specified
MIDI_FILENAME = "Outpost (1995) - MARS.MID"

# Check if required files exist
if not os.path.exists(SOUNDFONT):
    print(f"Error: SoundFont not found at {SOUNDFONT}")
    exit()

if not os.path.exists(MIDI_FILENAME):
    print(f"Error: MIDI file not found at {MIDI_FILENAME}")
    print("Please make sure it's in the same directory as mvp.py")
    exit()


# --- FluidSynth Initialization ---
fs = None
try:
    fs = fluidsynth.Synth()
    print("Synth created.")

    # Start the synth using the default audio driver
    # If you had issues before, you might need to specify one, e.g.:
    # fs.start(driver='alsa')
    fs.start()
    print("Synth started.")

    # Load the SoundFont
    sfid = fs.sfload(SOUNDFONT)
    if sfid == -1:
        print(f"Error: Failed to load SoundFont: {SOUNDFONT}")
        exit()
    print(f"SoundFont loaded successfully (ID: {sfid}).")

    # --- MIDI File Playback using Mido ---
    print(f"Opening MIDI file: {MIDI_FILENAME}")
    try:
        mid = mido.MidiFile(MIDI_FILENAME)
        print("MIDI file opened. Starting playback...")

        # Get total playback time (optional, for info)
        total_time = mid.length
        print(f"Estimated duration: {total_time:.2f} seconds")

        # Iterate through messages, waiting between them using mido's timing
        # Note: msg.time holds the delay *before* this message should be played
        for msg in mid.play(): # mid.play() yields messages with time context
            # Send MIDI messages to FluidSynth
            if msg.type == 'note_on':
                fs.noteon(msg.channel, msg.note, msg.velocity)
            elif msg.type == 'note_off':
                fs.noteoff(msg.channel, msg.note)
            elif msg.type == 'program_change':
                fs.program_change(msg.channel, msg.program)
            elif msg.type == 'control_change':
                fs.cc(msg.channel, msg.control, msg.value)
            elif msg.type == 'pitchwheel': # Handling pitch bend
                # FluidSynth pitch_bend range is 0-16383, center is 8192
                # Mido pitch bend range is -8192 to +8191, center is 0
                fs.pitch_bend(msg.channel, msg.pitch + 8192)
            # Add other message types here if needed (e.g., sysex, channel_pressure)

        print("Playback finished.")

    except Exception as e:
        print(f"Error during MIDI playback: {e}")


except Exception as e:
    print(f"An error occurred during FluidSynth setup: {e}")

finally:
    # Clean up the synthesizer instance
    if fs:
        print("Deleting synth instance...")
        fs.delete()
        print("Synth deleted.")