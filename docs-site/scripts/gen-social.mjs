// Generate the GitHub repo social-preview card (1280×640) for nxstate — a proof-forward card
// showing a real read-only invocation + the WRITE_REFUSED boundary, in the network-teal brand.
// Output: .github/social-preview.png (uploaded manually in repo Settings → Social preview).
// Run from the docs-site dir (has @fontsource fonts + sharp): node scripts/gen-social.mjs
import { execFileSync } from 'node:child_process';
import { readFileSync, mkdirSync, writeFileSync, globSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import sharp from 'sharp';

const DOCS = resolve(dirname(fileURLToPath(import.meta.url)), '..'); // docs-site
const REPO = resolve(DOCS, '..');
const OUT = join(REPO, '.github', 'social-preview.png');
const CHROME = process.env.CHROME || '/usr/bin/google-chrome';
const W = 1280, H = 640;

function fontB64(family) {
  const [file] = globSync(`node_modules/@fontsource-variable/${family}/files/*-latin-wght-normal.woff2`, { cwd: DOCS });
  if (!file) throw new Error(`font not found: ${family}`);
  return readFileSync(join(DOCS, file)).toString('base64');
}
const inter = fontB64('inter');
const mono = fontB64('jetbrains-mono');

const html = `<!doctype html><html><head><meta charset="utf-8"><style>
@font-face{font-family:'Int';src:url(data:font/woff2;base64,${inter}) format('woff2');font-weight:100 900}
@font-face{font-family:'Mono';src:url(data:font/woff2;base64,${mono}) format('woff2');font-weight:100 800}
*{margin:0;box-sizing:border-box}
html,body{width:${W}px;height:${H}px}
body{background:#07100f;color:#e6f3f1;font-family:'Int',sans-serif;position:relative;overflow:hidden}
.bg{position:absolute;inset:0;background:
  radial-gradient(900px 520px at 8% -10%, rgba(14,165,165,.30), transparent 60%),
  radial-gradient(760px 520px at 110% 120%, rgba(20,120,120,.22), transparent 55%)}
.frame{position:absolute;inset:22px;border:1px solid rgba(94,234,212,.16);border-radius:18px}
.wrap{position:absolute;inset:0;padding:52px 60px;display:flex;flex-direction:column;justify-content:space-between}
.top{display:flex;align-items:center;justify-content:space-between;font-family:'Mono';font-size:24px}
.brand{display:flex;align-items:center;gap:14px;font-weight:600}
.dot{width:15px;height:15px;border-radius:50%;background:#5eead4;box-shadow:0 0 22px 4px rgba(94,234,212,.7)}
.top .meta{color:#5b8b88;letter-spacing:.12em;text-transform:uppercase;font-size:19px}
.title{font-weight:800;font-size:62px;line-height:1.05;letter-spacing:-.02em;max-width:1090px}
.title .ac{color:#5eead4}
.term{background:#04100f;border:1px solid rgba(94,234,212,.18);border-radius:14px;padding:22px 26px;font-family:'Mono';font-size:23px;line-height:1.5}
.dots{display:flex;gap:8px;margin-bottom:14px}
.dots i{width:13px;height:13px;border-radius:50%;display:inline-block}
.cmd{color:#e6f3f1}.cmd .p{color:#5eead4}.k{color:#7fd1ff}.n{color:#f6c177}.s{color:#9ece6a}.muted{color:#5b8b88}
.refuse{color:#ff8f6b}
.bottom{display:flex;align-items:center;justify-content:space-between;font-family:'Mono';font-size:22px}
.tags{display:flex;gap:12px}
.tag{border:1px solid rgba(94,234,212,.3);color:#9fe9df;border-radius:999px;padding:6px 14px;font-size:20px}
.install{color:#5eead4}
</style></head><body>
<div class="bg"></div><div class="frame"></div>
<div class="wrap">
  <div class="top">
    <div class="brand"><span class="dot"></span>nxstate</div>
    <div class="meta">read-only · NX-OS</div>
  </div>
  <div class="title">Read-only Cisco Nexus state,<br>as clean JSON <span class="ac">for your agent.</span></div>
  <div class="term">
    <div class="dots"><i style="background:#ff5f56"></i><i style="background:#ffbd2e"></i><i style="background:#27c93f"></i></div>
    <div class="cmd"><span class="p">$</span> nxstate interface list --json | jq '.[0]'</div>
    <div class="cmd"><span class="muted">{</span> <span class="k">"interface"</span>: <span class="s">"Ethernet1/1"</span>, <span class="k">"state"</span>: <span class="s">"up"</span>, <span class="k">"speed"</span>: <span class="n">"1000"</span> <span class="muted">}</span></div>
    <div class="cmd"><span class="p">$</span> nxstate run "conf t"   <span class="refuse">→ WRITE_REFUSED (exit 11)</span></div>
  </div>
  <div class="bottom">
    <div class="tags"><span class="tag">read-only</span><span class="tag">fleet fan-out</span><span class="tag">injection-fenced</span><span class="tag">MIT</span></div>
    <div class="install">$ uvx nxstate</div>
  </div>
</div></body></html>`;

mkdirSync(dirname(OUT), { recursive: true });
const tmp = join(tmpdir(), 'nxstate-social.html');
const raw = join(tmpdir(), 'nxstate-social-raw.png');
writeFileSync(tmp, html);
// This headless Chrome paints ~half the window height → render at 2× and crop the top.
execFileSync(CHROME, [
  '--headless=new', '--no-sandbox', '--hide-scrollbars', '--force-device-scale-factor=1',
  `--window-size=${W},${H * 2}`, '--default-background-color=00000000',
  '--virtual-time-budget=1500', `--screenshot=${raw}`, `file://${tmp}`,
], { stdio: 'ignore' });
await sharp(raw).extract({ left: 0, top: 0, width: W, height: H }).toFile(OUT);
console.log('wrote', OUT);
