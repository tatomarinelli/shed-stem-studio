"""Corre dentro del venv de stems (tiene numpy + soundfile): duración y volumen por stem."""
import json
import math
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

out = {}
for path in sorted(Path(sys.argv[1]).glob("*.flac")):
    data, rate = sf.read(path, dtype="float32")
    rms = float(np.sqrt(np.mean(data ** 2)))
    out[path.name] = {"duration": len(data) / rate, "rate": rate, "rms_db": 20 * math.log10(max(rms, 1e-9))}
print(json.dumps(out))
