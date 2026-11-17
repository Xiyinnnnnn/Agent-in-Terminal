'use strict';

const fs = require('node:fs');
const path = require('node:path');

const dir = process.argv[2] || 'stage1/report';
const order = ['logger', 'report', 'index'];
const out = ["'use strict';", 'const __mods = {};'];

for (const name of order) {
  const p = path.join(dir, name + '.js');
  if (!fs.existsSync(p)) continue;
  let src = fs.readFileSync(p, 'utf8');
  src = src.replace(/^'use strict';\s*/, '');
  src = src.replace(/module\.exports\s*=\s*\{([\s\S]*?)\};?/g, 'return {$1};');
  src = src.replace(/module\.exports\s*=\s*([A-Za-z_$][\w$]*);?/g, 'return $1;');
  src = src.replace(/require\('\.\/([^']+)'\)/g, "__mods['./$1']");
  out.push("__mods['./" + name + "'] = (function () {");
  out.push(src);
  out.push('})();');
}

fs.mkdirSync('dist', { recursive: true });
fs.writeFileSync('dist/report.js', out.join('\n') + '\n');
for (const f of ['config.json', 'records.json']) {
  const src = path.join(dir, f);
  if (fs.existsSync(src)) fs.copyFileSync(src, path.join('dist', f));
}
console.log('bundle bytes=' + fs.statSync('dist/report.js').size);
