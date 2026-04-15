import subprocess


def get_audio_duration(audio_path: str) -> float:
    """
    Return the duration of an audio file in seconds using ffprobe.

    Raises:
        RuntimeError: If ffprobe returns a non-zero exit code.
    """
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        audio_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffprobe failed (exit {result.returncode}): {result.stderr.strip()}"
        )
    return float(result.stdout.strip())
