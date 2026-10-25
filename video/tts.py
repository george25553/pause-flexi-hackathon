import sys, json, pathlib, soundfile as sf
from kokoro_onnx import Kokoro
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from script import BEATS
OUT = pathlib.Path(__file__).parent / "audio"; OUT.mkdir(exist_ok=True)
VOICE = sys.argv[1] if len(sys.argv) > 1 else "af_heart"
SPEED = float(sys.argv[2]) if len(sys.argv) > 2 else 1.08
k = Kokoro("/home/claude/tts/kokoro-v1.0.onnx", "/home/claude/tts/voices-v1.0.bin")
durs = []
for i, b in enumerate(BEATS):
    samples, sr = k.create(b["say"], voice=VOICE, speed=SPEED, lang="en-us")
    sf.write(OUT / f"b{i:02d}.wav", samples, sr)
    durs.append(len(samples) / sr)
    print(i, round(durs[-1], 2), flush=True)
json.dump(durs, open(OUT / "durations.json", "w"))
print("total speech", round(sum(durs), 1), "s; with 0.35s gaps", round(sum(durs) + 0.35 * len(durs), 1))
