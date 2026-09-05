#!/usr/bin/env python3
"""听力音频生成（edge-tts 多音色）—— 供 `cli.py tts` 使用。

- 一段文稿（独白）→ 单一音色 mp3；多人对话 → 每话轮一个音色、独立 mp3，
  再原生拼接（同一服务/编码参数，帧级拼接无损，无需 ffmpeg）。
- 时长用纯 stdlib 的 MPEG 帧遍历估算（不依赖 afinfo/ffprobe）。
- edge_tts 仅在调用时导入（未安装给出安装提示，不拖累 CLI 其它命令）。

音频一律落在 data/audio/（与数据库同目录的 audio/，不入 git），
试卷 JSON 里 passage.audio 先写"合成规格"，生成后改写为"清单"（含 file/duration/segments）。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------- mp3 时长（帧遍历）
_MPEG1 = 3
_BITRATE = {  # [version][bitrate_index] kbps
    _MPEG1: {1: 32, 2: 40, 3: 48, 4: 56, 5: 64, 6: 80, 7: 96, 8: 112,
             9: 128, 10: 160, 11: 192, 12: 224, 13: 256, 14: 320},
    2: {1: 8, 2: 16, 3: 24, 4: 32, 5: 40, 6: 48, 7: 56, 8: 64,
        9: 80, 10: 96, 11: 112, 12: 128, 13: 144, 14: 160},
    0: {1: 8, 2: 16, 3: 24, 4: 32, 5: 40, 6: 48, 7: 56, 8: 64,
        9: 80, 10: 96, 11: 112, 12: 128, 13: 144, 14: 160},
}
_SRATE = {_MPEG1: [44100, 48000, 32000], 2: [22050, 24000, 16000], 0: [11025, 12000, 8000]}


def _id3_skip(data: bytes) -> int:
    if data[:3] == b"ID3":
        size = ((data[6] & 0x7F) << 21) | ((data[7] & 0x7F) << 14) | \
               ((data[8] & 0x7F) << 7) | (data[9] & 0x7F)
        return 10 + size
    return 0


def mp3_duration(path: str | Path) -> float:
    """遍历 MPEG 帧累计采样点 → 秒。edge-tts 输出为 CBR MPEG1/2 Layer III。"""
    with open(path, "rb") as f:
        data = f.read()
    pos = _id3_skip(data)
    total = 0.0
    n = len(data)
    while pos + 4 <= n:
        b0, b1, b2, b3 = data[pos], data[pos + 1], data[pos + 2], data[pos + 3]
        if b0 != 0xFF or (b1 & 0xE0) != 0xE0:  # 找帧同步
            pos += 1
            continue
        ver = (b1 >> 3) & 0x03  # 0=MPEG2.5 2=MPEG2 3=MPEG1
        layer = (b1 >> 1) & 0x03
        if layer != 1 or ver == 1:  # 只要 Layer III
            pos += 1
            continue
        bi = (b2 >> 4) & 0x0F
        si = (b2 >> 2) & 0x03
        pad = (b2 >> 1) & 0x01
        kbps = _BITRATE.get(ver, {}).get(bi)
        srate = _SRATE.get(ver, [])[si] if si < 3 else None
        if not kbps or not srate:
            pos += 1
            continue
        samples = 1152 if ver == _MPEG1 else 576
        flen = (144 if ver == _MPEG1 else 72) * kbps * 1000 // srate + pad
        total += samples / srate
        pos += max(flen, 1)
    return round(total, 3)


# ---------------------------------------------------------------- 合成
def _synth_one(text: str, voice: str, rate: str, out: Path):
    """合成一段音频（blocking，内部跑 asyncio）。"""
    import asyncio

    try:
        import edge_tts
    except ImportError:
        sys.exit("缺少 edge-tts：先安装 → python3 -m pip install edge-tts "
                 "（国内网络可加 -i https://pypi.tuna.tsinghua.edu.cn/simple）")

    async def run():
        comm = edge_tts.Communicate(text, voice, rate=rate)
        with open(out, "wb") as f:
            async for chunk in comm.stream():
                if chunk["type"] == "audio":
                    f.write(chunk["data"])

    asyncio.run(run())


def synthesize(audio_spec: dict, paper_stem: str, pidx: int, audio_dir: Path,
               force: bool = False) -> dict:
    """按规格合成一个 passage 的音频，返回清单（manifest）。

    audio_spec（规格，写在试卷 JSON 里）: {
      "mode": "tts",
      "voice": "en-GB-SoniaNeural",   # 默认音色（segments 可逐个覆盖）
      "rate": "-4%",                  # 默认语速（segments 可逐个覆盖）
      "segments": [ {"label": "Ruth（导览员）", "voice": "...", "text": "..."} ]
    }
    清单（回写 JSON/DB）: { "file": "xxx_p1.mp3", "duration": 55.6,
      "segments": [{"label","voice","text","file","start","end"}] }
    """
    segs = audio_spec.get("segments") or []
    if not segs:
        raise ValueError("audio.mode='tts' 需要 segments（至少一段）")
    base = f"{paper_stem}_p{pidx}"
    default_voice = audio_spec.get("voice", "en-GB-SoniaNeural")
    default_rate = audio_spec.get("rate", "-4%")
    seg_files, out_segs = [], []
    for i, s in enumerate(segs, 1):
        text = str(s.get("text") or "").strip()
        if not text:
            raise ValueError(f"第 {i} 段说话内容为空")
        voice = s.get("voice") or default_voice
        rate = s.get("rate") or default_rate
        fpath = audio_dir / f"{base}_{i}.mp3"
        if force or not fpath.is_file():
            t0 = time.time()
            _synth_one(text, voice, rate, fpath)
            print(f"  🔊 {s.get('label', '?')} [{voice}] {len(text)}词 "
                  f"→ {fpath.name} ({time.time()-t0:.1f}s)")
        out_segs.append({"label": s.get("label", ""), "voice": voice,
                         "text": text, "file": fpath.name})
        seg_files.append(fpath)
    combined = audio_dir / f"{base}.mp3"
    if force or not combined.is_file() or any(
            not p.is_file() for p in seg_files):
        with open(combined, "wb") as out:
            for p in seg_files:
                out.write(p.read_bytes())
    manifest_segs, start = [], 0.0
    for seg, path in zip(out_segs, seg_files):
        dur = mp3_duration(path)
        manifest_segs.append({**seg, "start": round(start, 3),
                              "end": round(start + dur, 3)})
        start += dur
    return {"file": combined.name, "duration": round(start, 3),
            "segments": manifest_segs}


def strip_spec(audio: dict) -> dict:
    """去掉合成规格、只留清单字段（写回试卷 JSON 时防冗余）。"""
    if not audio:
        return audio
    keep = {"file", "duration", "segments"}
    out = {k: v for k, v in audio.items() if k in keep}
    for s in out.get("segments") or []:
        for k in list(s.keys()):
            if k not in ("label", "voice", "text", "file", "start", "end"):
                del s[k]
    return out


def needs_synth(audio: dict) -> bool:
    """True = 还是合成规格（缺 file 清单）或文件缺失。"""
    if not isinstance(audio, dict):
        return False
    if audio.get("mode") != "tts" or audio.get("file"):
        return False
    return bool(audio.get("segments"))
