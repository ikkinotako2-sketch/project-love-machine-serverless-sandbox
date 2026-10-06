"""Deterministic offline-only ESM assembly; no external process or network."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def expected_bundle():
    old=(ROOT/'serverless/youtube-live/worker.mjs').read_text().replace('export default {','const historicalParkedWorker = {')
    parts=[old]
    for f in ('mapping.mjs','dispatch.mjs','checkpoint.mjs','sender.mjs','connection.mjs'):
        source=(ROOT/'serverless/youtube-connection'/f).read_text()
        source='\n'.join(line for line in source.splitlines() if not line.startswith('import '))+'\n'
        parts.append('// MODULE '+f+'\n'+source)
    return '\n'.join(parts)

if __name__=='__main__':(ROOT/'serverless/youtube-connection/bundle.mjs').write_text(expected_bundle())
