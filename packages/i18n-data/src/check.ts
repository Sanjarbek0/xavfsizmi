import en from './en/common.json' with { type: 'json' };
import ru from './ru/common.json' with { type: 'json' };
import uz from './uz/common.json' with { type: 'json' };

type Catalogue = Record<string, unknown>;

function flatten(obj: Catalogue, prefix = ''): string[] {
  const out: string[] = [];
  for (const [k, v] of Object.entries(obj)) {
    const key = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === 'object' && !Array.isArray(v)) {
      out.push(...flatten(v as Catalogue, key));
    } else {
      out.push(key);
    }
  }
  return out;
}

const enKeys = new Set(flatten(en as Catalogue));
const ruKeys = new Set(flatten(ru as Catalogue));
const uzKeys = new Set(flatten(uz as Catalogue));

let drift = false;
function diff(name: string, base: Set<string>, other: Set<string>): void {
  const missing = [...base].filter((k) => !other.has(k));
  const extra = [...other].filter((k) => !base.has(k));
  if (missing.length || extra.length) {
    drift = true;
    console.error(`[${name}] drift detected`);
    if (missing.length) console.error(`  missing: ${missing.join(', ')}`);
    if (extra.length) console.error(`  extra:   ${extra.join(', ')}`);
  }
}

diff('uz vs en', enKeys, uzKeys);
diff('ru vs en', enKeys, ruKeys);

if (drift) {
  console.error('i18n drift — fix translations in packages/i18n-data');
  process.exit(1);
}
console.log('i18n catalogues are in sync (uz, ru, en)');
