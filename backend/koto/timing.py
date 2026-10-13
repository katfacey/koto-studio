"""Cheap, explicitly approximate English timing hints and shared playback rules."""
import hashlib
import json
import re


def estimate_seconds(text, wpm=150):
    words = re.findall(r"[A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)*",text)
    if not words:
        return 0
    pauses = len(re.findall(r'[,;:]',text))*.1 + len(re.findall(r'[.!?]+(?=\s|$)',text))*.15
    return round(len(words)*60/wpm+pauses,2)


def playback_rate(project,line,duration):
    factor=duration/(line['end']-line['start'])
    if project['settings'].get('fit_duration',True) and line.get('auto_fit',True) and .8<=factor<=1.25:
        return factor
    return float(line.get('playback_rate',1))


def adaptation_signature(line):
    return hashlib.sha256(json.dumps([line.get(k) for k in ('source','subtitle','translation','start','end')],ensure_ascii=False).encode()).hexdigest()
