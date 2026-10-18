# prompt2claudevideo

Video pendek 9:16 (30 saat) "3 cara guna Claude yang betul", dijana daripada voiceover.

- `assets/voiceover.wav`: audio asal
- `render.py`: lukis setiap frame (Pillow), tambah SFX whoosh/pop, encode dengan ffmpeg
- `output/claude-3-cara.mp4`: hasil akhir (1080x1920, 30fps)

## Render semula

```bash
pip install pillow numpy   # ffmpeg perlu ada dalam PATH
python3 render.py                       # video penuh -> output/claude-3-cara.mp4
python3 render.py --preview 3.5 15 26   # simpan frame PNG pada saat tertentu
```

Timing setiap frasa ada dalam `SEGS` (diukur dari jeda dalam audio). Kalau tukar audio, kemas kini `SEGS` dan `CUTS`.
Term yang di-highlight dalam caption dikawal oleh set `HIGHLIGHT`.
