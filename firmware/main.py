"""
Boot entry point.  MicroPython runs this automatically on reset.

Swap the active block below to change which program the badge boots:

    disco      -- SILENT DISCO (current): CHANNEL cycles tracks, each track
                  loops rather than advancing, LED colour comes from the track
                  name, SYNC listens for a neighbour's IR timecode.
    mp3player  -- plain MP3 player: flat alphabetical playlist, play/pause,
                  volume, tap/hold for next/previous track, self-driving lights.
    jukebox    -- the earlier build: same playback, but SYNC cycles LED modes
                  and there is no track navigation.
    audiolab   -- button-driven audio diagnostic rig (tone/sweep/music/silence/
                  freq), for chasing hardware problems.  See BADGE.md.

CPU clock comes from config.CPU_FREQ, now 276 MHz -- chosen by ear because the
supply-coupled buzz shifts pitch with sys_clk.  See the notes there.
"""

import disco
disco.run()

# --- plain player ---------------------------------------------------------
# import mp3player
# mp3player.run()

# --- audio diagnostics ----------------------------------------------------
# Autostarts a continuous tone; SYNC cycles TONE/SWEEP/MUSIC/ZEROS/CLKOFF/FREQ.
# In ZEROS, VOL+/- step the CPU clock.  In FREQ, they step tone frequency.
# import audiolab
# audiolab.run(autostart=True, mode=audiolab.FREQ, level=12)
