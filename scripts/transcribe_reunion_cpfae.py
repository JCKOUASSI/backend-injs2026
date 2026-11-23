#!/usr/bin/env python3
"""Transcription audio réunion CPFAE (segments) avec faster-whisper."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Aucun chemin machine en dur : le fichier audio est passé avec --audio (P00-03).
DEFAULT_AUDIO = None
# ffmpeg est résolu via le PATH système (installations macOS Homebrew incluses).
FFMPEG = 'ffmpeg'


def extract_segment(src: Path, start_sec: float, duration_sec: float, out_wav: Path) -> None:
    cmd = [
        FFMPEG, '-y', '-hide_banner', '-loglevel', 'error',
        '-ss', str(start_sec), '-t', str(duration_sec),
        '-i', str(src), '-ac', '1', '-ar', '16000', str(out_wav),
    ]
    subprocess.run(cmd, check=True)


def transcribe_file(wav: Path, model_name: str = 'small') -> list[dict]:
    from faster_whisper import WhisperModel

    model = WhisperModel(model_name, device='cpu', compute_type='int8')
    segments, info = model.transcribe(
        str(wav),
        language='fr',
        beam_size=5,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500),
    )
    out = []
    for seg in segments:
        out.append({
            'start': round(seg.start, 2),
            'end': round(seg.end, 2),
            'text': seg.text.strip(),
        })
    return out


def format_timestamp(sec: float) -> str:
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    if h:
        return f'{h:02d}:{m:02d}:{s:02d}'
    return f'{m:02d}:{s:02d}'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--audio', type=Path, default=DEFAULT_AUDIO,
                        required=DEFAULT_AUDIO is None,
                        help="Chemin du fichier audio à transcrire (obligatoire)")
    parser.add_argument('--start', type=float, default=0, help='Début en secondes')
    parser.add_argument('--duration', type=float, default=3600, help='Durée segment (s)')
    parser.add_argument('--model', default='small')
    parser.add_argument('--out', type=Path, default=ROOT / 'docs' / 'archives' / 'transcripts' / 'reunion-cpfae-segment.txt')
    parser.add_argument('--offset', type=float, default=0, help='Offset horodatage affiché')
    args = parser.parse_args()

    if not args.audio.exists():
        print(f'Fichier introuvable: {args.audio}', file=sys.stderr)
        sys.exit(1)

    args.out.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
        wav_path = Path(tmp.name)

    try:
        print(f'Extraction {args.start}s + {args.duration}s…', flush=True)
        extract_segment(args.audio, args.start, args.duration, wav_path)
        print(f'Transcription ({args.model})…', flush=True)
        segments = transcribe_file(wav_path, args.model)
    finally:
        wav_path.unlink(missing_ok=True)

    lines = []
    for seg in segments:
        t = format_timestamp(args.offset + seg['start'])
        if seg['text']:
            lines.append(f'[{t}] {seg["text"]}')

    text = '\n'.join(lines)
    args.out.write_text(text, encoding='utf-8')
    meta = {
        'audio': str(args.audio),
        'start': args.start,
        'duration': args.duration,
        'offset': args.offset,
        'segments': len(segments),
        'chars': len(text),
        'out': str(args.out),
    }
    (args.out.with_suffix('.json')).write_text(json.dumps(meta, indent=2), encoding='utf-8')
    print(json.dumps(meta, indent=2))
    print(f'\n--- Aperçu ---\n{text[:3000]}')


if __name__ == '__main__':
    main()
