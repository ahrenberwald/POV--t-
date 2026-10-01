# -*- coding: utf-8 -*-
"""
Player POV - Unified Pipeline
Replaces: Video_Conversion.py, vidoeSync.py, timeSyncMAybe.py, TimeSync.m

Authors: Emma Paulson (original), continued development by current team
Run with : uvicorn main:app --reload
"""

import numpy as np
import soundfile as sf
from scipy.signal import correlate
from moviepy import VideoFileClip, clips_array
import os
import subprocess


# ---------------------------------------------------------------------------
# 1. VIDEO CONVERSION
# ---------------------------------------------------------------------------

def convert_to_mp4(input_path: str, output_path: str) -> bool:
    """Convert any video file (HEVC, MOV, etc.) to H.264 MP4."""
    try:
        clip = VideoFileClip(input_path)
        clip.write_videofile(output_path, codec="libx264", audio_codec="aac", logger=None)
        clip.close()
        print(f"[convert] {input_path} -> {output_path}")
        return True
    except Exception as e:
        print(f"[convert] ERROR: {e}")
        return False


def extract_audio(input_video_path: str, output_wav_path: str) -> bool:
    """Extract audio track from a video file and save as WAV."""
    try:
        clip = VideoFileClip(input_video_path)
        if clip.audio is None:
            print(f"[audio] No audio track found in {input_video_path}")
            clip.close()
            return False
        clip.audio.write_audiofile(output_wav_path, codec="pcm_s16le", logger=None)
        clip.close()
        print(f"[audio] Extracted audio -> {output_wav_path}")
        return True
    except Exception as e:
        print(f"[audio] ERROR: {e}")
        return False


# ---------------------------------------------------------------------------
# 2. TIME SYNC  (Python port of MATLAB TimeSync - replaces the .m file)
# ---------------------------------------------------------------------------

def time_sync(audio1_path: str, audio2_path: str):
    """
    Find the time offset between two audio recordings of the same event.
    """
    a1, fs1 = sf.read(audio1_path)
    a2, fs2 = sf.read(audio2_path)

    # Mono conversion
    if a1.ndim > 1:
        a1 = a1.mean(axis=1)
    if a2.ndim > 1:
        a2 = a2.mean(axis=1)

    # Resample if sample rates differ
    if fs1 != fs2:
        from scipy.signal import resample
        a2 = resample(a2, int(len(a2) * fs1 / fs2))

    fs = fs1
    dur1 = len(a1) / fs
    dur2 = len(a2) / fs

    # Normalize
    a1 = (a1 - a1.mean()) / (a1.std() + 1e-9)
    a2 = (a2 - a2.mean()) / (a2.std() + 1e-9)

    # Always correlate longer against shorter
    if len(a1) >= len(a2):
        long_audio, short_audio = a1, a2
    else:
        long_audio, short_audio = a2, a1

    # Cross-correlation using FFT for better accuracy
    from numpy.fft import fft, ifft
    n = len(long_audio) + len(short_audio) - 1
    fft_size = 1
    while fft_size < n:
        fft_size *= 2

    F1 = fft(long_audio,  fft_size)
    F2 = fft(short_audio, fft_size)
    correlation = np.real(ifft(F1 * np.conj(F2)))

    # Only look at positive lags
    max_lag_samples = len(long_audio) - 1
    correlation = correlation[:max_lag_samples]

    best_lag = int(np.argmax(correlation))
    offset_seconds = best_lag / fs

    # Sanity check
    if offset_seconds >= dur1 or offset_seconds >= dur2:
        offset_seconds = 0.0

    print(f"[sync] Detected offset: {offset_seconds:.4f} s")
    return offset_seconds, dur1, dur2


# ---------------------------------------------------------------------------
# 3. VIDEO SYNC  (replaces vidoeSync.py + the manual MATLAB step)
# ---------------------------------------------------------------------------

def sync_videos(
    video1_path: str,
    video2_path: str,
    output_dir: str,
    final_name: str,
    progress_callback=None,
) -> dict:
    """
    Full pipeline: convert -> extract audio -> sync -> stack -> export.
    """
    os.makedirs(output_dir, exist_ok=True)

    def _progress(step, pct):
        print(f"[pipeline] {pct}% -- {step}")
        if progress_callback:
            progress_callback(step, pct)

    try:
        safe_name = final_name.replace(" ", "_")

        # --- Step 1: convert to MP4 ---
        _progress("Converting video 1 to MP4", 5)
        mp4_1 = os.path.join(output_dir, f"{safe_name}_cam1.mp4")
        if not convert_to_mp4(video1_path, mp4_1):
            return {"success": False, "error": "Failed to convert video 1"}

        _progress("Converting video 2 to MP4", 20)
        mp4_2 = os.path.join(output_dir, f"{safe_name}_cam2.mp4")
        if not convert_to_mp4(video2_path, mp4_2):
            return {"success": False, "error": "Failed to convert video 2"}

        # --- Step 2: extract audio ---
        _progress("Extracting audio from video 1", 35)
        wav_1 = os.path.join(output_dir, f"{safe_name}_cam1.wav")
        if not extract_audio(mp4_1, wav_1):
            return {"success": False, "error": "Failed to extract audio from video 1"}

        _progress("Extracting audio from video 2", 45)
        wav_2 = os.path.join(output_dir, f"{safe_name}_cam2.wav")
        if not extract_audio(mp4_2, wav_2):
            return {"success": False, "error": "Failed to extract audio from video 2"}

        # --- Step 3: time sync ---
        _progress("Running audio synchronisation", 55)
        offset, dur1, dur2 = time_sync(wav_1, wav_2)

        # --- Step 4: trim & stack using FFmpeg ---
        _progress("Trimming and stacking videos", 70)

        mp4_1_ff = mp4_1.replace("\\", "/")
        mp4_2_ff = mp4_2.replace("\\", "/")
        out1 = os.path.join(output_dir, f"{safe_name}_audio1.mp4")
        out2 = os.path.join(output_dir, f"{safe_name}_audio2.mp4")
        out1_ff = out1.replace("\\", "/")
        out2_ff = out2.replace("\\", "/")

        # Output 1: camera 1 audio
        _progress("Exporting synced video (camera 1 audio)", 80)
        cmd1 = [
            "ffmpeg", "-y",
            "-ss", str(offset), "-i", mp4_1_ff,
            "-ss", "0",         "-i", mp4_2_ff,
            "-filter_complex", "[0:v]scale=1080:-2[v0];[1:v]scale=1080:-2[v1];[v0][v1]vstack=inputs=2[v]",
            "-map", "[v]",
            "-map", "0:a",
            "-c:v", "libx264",
            "-c:a", "aac",
            "-preset", "fast",
            "-crf", "23",
            out1_ff
        ]
        result1 = subprocess.run(cmd1, capture_output=True, text=True)
        if result1.returncode != 0:
            raise Exception(f"FFmpeg error: {result1.stderr}")

        # Output 2: camera 2 audio
        _progress("Exporting synced video (camera 2 audio)", 92)
        cmd2 = [
            "ffmpeg", "-y",
            "-ss", str(offset), "-i", mp4_1_ff,
            "-ss", "0",         "-i", mp4_2_ff,
            "-filter_complex", "[0:v]scale=1080:-2[v0];[1:v]scale=1080:-2[v1];[v0][v1]vstack=inputs=2[v]",
            "-map", "[v]",
            "-map", "1:a",
            "-c:v", "libx264",
            "-c:a", "aac",
            "-preset", "fast",
            "-crf", "23",
            out2_ff
        ]
        result2 = subprocess.run(cmd2, capture_output=True, text=True)
        if result2.returncode != 0:
            raise Exception(f"FFmpeg error: {result2.stderr}")

        _progress("Done", 100)

        return {
            "success": True,
            "offset": round(offset, 4),
            "output_audio1": out1,
            "output_audio2": out2,
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# 4. SEGMENT STITCHING  (for POV glasses 10-min clips)
# ---------------------------------------------------------------------------

def stitch_segments(
    segment_paths: list,
    output_path: str,
    progress_callback=None,
) -> dict:
    """
    Concatenate multiple video segments into one long video in order.
    """
    def _progress(step, pct):
        print(f"[stitch] {pct}% -- {step}")
        if progress_callback:
            progress_callback(step, pct)

    try:
        from moviepy import concatenate_videoclips

        _progress(f"Loading {len(segment_paths)} segments...", 5)
        clips = []
        for i, path in enumerate(segment_paths):
            pct = int(5 + (i / len(segment_paths)) * 60)
            _progress(f"Loading segment {i+1} of {len(segment_paths)}", pct)
            clips.append(VideoFileClip(path))

        _progress("Concatenating segments...", 70)
        final = concatenate_videoclips(clips, method="compose")

        _progress("Exporting stitched video...", 80)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        final.write_videofile(output_path, codec="libx264", audio_codec="aac", logger=None)

        for c in clips:
            try: c.close()
            except: pass
        final.close()

        _progress("Done", 100)
        return {"success": True, "output": output_path}

    except Exception as e:
        return {"success": False, "error": str(e)}