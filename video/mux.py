import json, pathlib, subprocess
HERE = pathlib.Path(__file__).parent
tl = json.load(open(HERE / "timeline.json"))
frames, starts, end = tl["frames"], tl["starts"], tl["end"]
t0 = frames[0][0]
lines = []
for i, (ts, name) in enumerate(frames):
    nxt = frames[i + 1][0] if i + 1 < len(frames) else end
    lines.append(f"file 'frames/{name}'\nduration {max(nxt - ts, 0.001):.4f}")
lines.append(f"file 'frames/{frames[-1][1]}'")
(HERE / "frames.txt").write_text("\n".join(lines))
inputs, filters = [], []
for i, s in enumerate(starts):
    inputs += ["-i", str(HERE / "audio" / f"b{i:02d}.wav")]
    d = int((s - t0) * 1000) + 120
    filters.append(f"[{i + 1}:a]adelay={d}|{d}[a{i}]")
mix = "".join(f"[a{i}]" for i in range(len(starts))) + f"amix=inputs={len(starts)}:normalize=0,apad[aout]"
total = end - t0
cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(HERE / "frames.txt"), *inputs,
       "-filter_complex", ";".join(filters) + ";" + mix + ";[0:v]fps=30,scale=1920:1080:flags=lanczos,format=yuv420p[v]",
       "-map", "[v]", "-map", "[aout]", "-t", f"{total:.2f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
       "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(HERE / "Pause_demo_Flexi.mp4")]
subprocess.run(cmd, check=True)
print("video length", round(total, 1), "s")
