"""Deterministic preparation-only standalone ESM, no network or subprocess."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def expected_bundle():
 base=(ROOT/'serverless/youtube-connection/bundle.mjs').read_text().replace('export default {','const inheritedParkedConnection = {')
 parts=[base]
 for name in ('runtime-contract.mjs','operation-gate.mjs','generation-adapter.mjs','runtime.mjs'):
  text=(ROOT/'serverless/youtube-connection'/name).read_text()
  parts.append('// SUCCESSOR MODULE '+name+'\n'+'\n'.join(line for line in text.splitlines() if not line.startswith('import '))+'\n')
 return '\n'.join(parts)
if __name__=='__main__':(ROOT/'serverless/youtube-connection/runtime-bundle.mjs').write_text(expected_bundle())
