"""Choose original, non-overlapping speaker audio for local voice conditioning."""
import hashlib
import json


def source_bounds(line):
    return line.get("source_start", line["start"]), line.get("source_end", line["end"])


def reference_signature(project, speaker_id):
    source = project["assets"].get("vocals") or project["assets"].get("original_audio")
    own = [source_bounds(l) for l in project["dialogue"] if l["speaker"] == speaker_id]
    lines = sorted((l["id"], l["speaker"], *source_bounds(l)) for l in project["dialogue"]
                   if l["speaker"] == speaker_id or any(source_bounds(l)[0] < b and source_bounds(l)[1] > a for a, b in own))
    return hashlib.sha256(json.dumps([source, speaker_id, lines], sort_keys=True).encode()).hexdigest()


def reference_segments(project, speaker_id, maximum=12):
    own = [source_bounds(l) for l in project["dialogue"] if l["speaker"] == speaker_id]
    others = [source_bounds(l) for l in project["dialogue"] if l["speaker"] != speaker_id]
    candidates = []
    for start, end in own:
        pieces = [(start, end)]
        for other_start, other_end in others:
            trimmed = []
            for a, b in pieces:
                if other_end <= a or other_start >= b:
                    trimmed.append((a, b))
                else:
                    if a < other_start:
                        trimmed.append((a, other_start))
                    if other_end < b:
                        trimmed.append((other_end, b))
            pieces = trimmed
        candidates.extend((a, b) for a, b in pieces if b-a >= .3)
    merged = []
    for a, b in sorted(candidates):
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    selected, total = [], 0
    for a, b in sorted(merged, key=lambda span: span[1]-span[0], reverse=True):
        length = min(b-a, maximum-total)
        if length < .3:
            break
        selected.append((a, a+length)); total += length
    if total < 3-1e-6:
        raise ValueError("This speaker needs at least 3 seconds of non-overlapping original dialogue for a voice reference. Correct speaker assignments, or turn off original references and upload a clean sample.")
    return sorted(selected)
