// Проверка переводов Mini App.
//   node scripts/i18n.mjs keys            — все ключи (русские тексты) из t('…'), N_('…') и plural(n, ['…','…','…'])
//   node scripts/i18n.mjs check           — в каждом src/locales/<язык>.json есть все ключи, подстановки {x} совпадают
//   node scripts/i18n.mjs missing <язык>  — JSON с непереведёнными ключами (для переводчика)
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const src = path.join(root, 'src');
const localesDir = path.join(src, 'locales');
const LANGS = ['en', 'uz', 'tg', 'ky', 'kk', 'az', 'hy'];

function files(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) return e.name === 'mock' || e.name === 'locales' ? [] : files(p);
    return /\.tsx?$/.test(e.name) && !e.name.endsWith('.d.ts') ? [p] : [];
  });
}

const literal = (n) => (n && (ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n)) ? n.text : null);

export function collectKeys() {
  const keys = new Set();
  const problems = [];
  for (const file of files(src)) {
    const sf = ts.createSourceFile(file, fs.readFileSync(file, 'utf8'), ts.ScriptTarget.Latest, true);
    const visit = (node) => {
      if (ts.isCallExpression(node) && ts.isIdentifier(node.expression)) {
        const name = node.expression.text;
        const where = () => `${path.relative(root, file)}:${sf.getLineAndCharacterOfPosition(node.getStart()).line + 1}`;
        if (name === 'N_' || name === 't') {
          const s = literal(node.arguments[0]);
          if (s != null) keys.add(s);
          else if (name === 'N_' || ts.isTemplateExpression(node.arguments[0])) problems.push(`${where()}: ${name}() с нестрокой`);
        } else if (name === 'plural') {
          const arr = node.arguments[1];
          if (arr && ts.isArrayLiteralExpression(arr)) {
            const forms = arr.elements.map(literal);
            if (forms.length === 3 && forms.every((f) => f != null)) keys.add(forms.join('|'));
            else problems.push(`${where()}: plural() без трёх строк`);
          }
        }
      }
      ts.forEachChild(node, visit);
    };
    visit(sf);
  }
  return { keys: [...keys].sort(), problems };
}

const placeholders = (s) => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort().join(',');

export function check() {
  const { keys, problems } = collectKeys();
  const errors = [...problems];
  for (const lang of LANGS) {
    const p = path.join(localesDir, `${lang}.json`);
    if (!fs.existsSync(p)) {
      errors.push(`${lang}: нет файла`);
      continue;
    }
    const dict = JSON.parse(fs.readFileSync(p, 'utf8'));
    const missing = keys.filter((k) => !dict[k]);
    if (missing.length) errors.push(`${lang}: нет перевода для ${missing.length}: ${missing.slice(0, 5).map((k) => JSON.stringify(k)).join(', ')}`);
    for (const k of keys) {
      const v = dict[k];
      if (!v) continue;
      if (placeholders(k) !== placeholders(v)) errors.push(`${lang}: подстановки не совпадают: ${JSON.stringify(k)} → ${JSON.stringify(v)}`);
      if (k.includes('|') && !(v.split('|').length >= 1 && v.split('|').length <= 3)) errors.push(`${lang}: формы: ${JSON.stringify(v)}`);
    }
    const extra = Object.keys(dict).filter((k) => !keys.includes(k));
    if (extra.length) errors.push(`${lang}: лишние ключи (${extra.length}): ${extra.slice(0, 5).map((k) => JSON.stringify(k)).join(', ')}`);
  }
  return { keys, errors };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const cmd = process.argv[2];
  if (cmd === 'keys') {
    const { keys, problems } = collectKeys();
    problems.forEach((p) => console.error(p));
    console.log(JSON.stringify(keys, null, 2));
  } else if (cmd === 'missing') {
    const lang = process.argv[3];
    const p = path.join(localesDir, `${lang}.json`);
    const dict = fs.existsSync(p) ? JSON.parse(fs.readFileSync(p, 'utf8')) : {};
    const out = Object.fromEntries(collectKeys().keys.filter((k) => !dict[k]).map((k) => [k, '']));
    console.log(JSON.stringify(out, null, 2));
  } else {
    const { keys, errors } = check();
    errors.forEach((e) => console.error(e));
    console.log(`ключей: ${keys.length}, ошибок: ${errors.length}`);
    process.exit(errors.length ? 1 : 0);
  }
}
