// Pure oracle over pinned, whitelisted source snippets. No fetch or API clients.
import {readFileSync} from 'node:fs';
const sources = JSON.parse(readFileSync(new URL('./parity_sources.json', import.meta.url)));
const requests = JSON.parse(readFileSync(0, 'utf8'));
function expression(value, input) {
  if (typeof value !== 'string' || !value.startsWith('=')) return value;
  let code = value.slice(1).trim();
  if (code.startsWith('{{') && code.endsWith('}}')) code = code.slice(2, -2);
  return new Function('$json', `return (${code});`)(input);
}
function assignments(list, input) {
  return Object.fromEntries(list.map(a => [a.name, expression(a.value, input)]));
}
const results = requests.map(request => {
  if (request.op === 'normalize') return assignments(sources.normalization_assignments, request.input);
  if (request.op === 'render') return assignments(sources.render_assignments, request.input);
  if (request.op === 'dispatch') return expression(sources.dispatch_expression, request.input);
  if (request.op === 'guidance') {
    const $ = name => ({first: () => {
      if (name === 'Get row(s)1') throw new Error('no queue fixture');
      return {json: {theme: 'offline fixture'}};
    }});
    const result = new Function('$', '$input', sources.consumer_code)($, {first: () => ({json:request.input})});
    return result[0].json.improvement_guidance;
  }
  throw new Error('invalid_oracle_operation');
});
process.stdout.write(JSON.stringify(results));
