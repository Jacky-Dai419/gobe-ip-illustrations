#!/usr/bin/env node
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';

const OPENCLI_BIN = process.env.OPENCLI_BIN || 'opencli';
const CHATGPT_URL = 'https://chatgpt.com/';
const OPENCLI_EXTENSION_URL = 'https://chromewebstore.google.com/detail/opencli/ildkmabpimmkaediidaifkhjpohdnifk';
const PROMPT_SELECTOR_CANDIDATES = [
  '#prompt-textarea',
  'textarea[data-testid="prompt-textarea"]',
  'textarea',
  'div.ProseMirror',
  '[contenteditable="true"]',
];

const ASSISTANT_STATE_JS = `(() => {
  const textOf = (node) => (node.innerText || node.textContent || '').replace(/\\s+$/g, '').trim();
  const isVisibleImage = (img) => {
    if (!(img instanceof HTMLImageElement)) return false;
    const style = window.getComputedStyle(img);
    if (style.display === 'none' || style.visibility === 'hidden') return false;
    const rect = img.getBoundingClientRect();
    const width = img.naturalWidth || img.width || rect.width || 0;
    const height = img.naturalHeight || img.height || rect.height || 0;
    const src = img.currentSrc || img.src || '';
    const generatedGalleryAsset = /\\/backend-api\\/estuary\\/content/i.test(src) && width >= 128 && height >= 128;
    if (!generatedGalleryAsset && (rect.width < 96 || rect.height < 96 || width < 128 || height < 128)) return false;
    const alt = img.alt || '';
    const cls = String(img.className || '');
    return !/avatar|profile|logo|icon/i.test(alt + ' ' + cls);
  };
  const conversationTurns = Array.from(document.querySelectorAll('section[data-testid^="conversation-turn-"]'));
  const assistantTurns = conversationTurns.filter((node) => /ChatGPT/i.test(node.querySelector('h4')?.textContent || ''));
  const userTurns = conversationTurns.filter((node) => /你说|You said/i.test(node.querySelector('h4')?.textContent || ''));
  const assistantNodes = Array.from(new Set([
    ...document.querySelectorAll('[data-message-author-role="assistant"]'),
    ...assistantTurns,
  ]));
  const userNodes = Array.from(new Set([
    ...document.querySelectorAll('[data-message-author-role="user"]'),
    ...userTurns,
  ]));
  const assistants = assistantNodes
    .map(textOf)
    .filter(Boolean);
  const users = userNodes
    .map(textOf)
    .filter(Boolean);
  const busy = Boolean(
    document.querySelector('[data-testid="stop-button"], button[aria-label*="Stop"], button[aria-label*="停止"], button[aria-label*="Cancel"], button[aria-label*="中止"]')
  );
  const images = assistantNodes.flatMap((node) => Array.from(node.querySelectorAll('img')))
    .filter(isVisibleImage)
    .map((img) => ({
      src: img.currentSrc || img.src || '',
      alt: img.alt || '',
      width: img.naturalWidth || img.width || 0,
      height: img.naturalHeight || img.height || 0
    }))
    .filter((item) => item.src);
  const uniqueImages = Array.from(new Map(images.map((item) => [item.src, item])).values());
  return JSON.stringify({
    url: location.href,
    title: document.title,
    assistantCount: assistants.length,
    userCount: users.length,
    lastAssistant: assistants.at(-1) || '',
    busy,
    imageCount: uniqueImages.length,
    lastImages: uniqueImages.slice(-8)
  });
})()`;

function usage() {
  console.log(`node chatgpt_web_bridge.mjs ui-chatgpt

用 OpenCLI 控制已登录的 ChatGPT 界面。

用法:
  node chatgpt_web_bridge.mjs ui-chatgpt setup
  node chatgpt_web_bridge.mjs ui-chatgpt doctor
  node chatgpt_web_bridge.mjs ui-chatgpt status
  node chatgpt_web_bridge.mjs ui-chatgpt open
  node chatgpt_web_bridge.mjs ui-chatgpt state
  node chatgpt_web_bridge.mjs ui-chatgpt send "你的提示词"
  node chatgpt_web_bridge.mjs ui-chatgpt ask "你的问题" --timeout 180
  node chatgpt_web_bridge.mjs ui-chatgpt ask "你的问题" --url https://chatgpt.com/c/...
  node chatgpt_web_bridge.mjs ui-chatgpt read
  node chatgpt_web_bridge.mjs ui-chatgpt image "图片需求" --timeout 300
  node chatgpt_web_bridge.mjs ui-chatgpt research "研究主题" --timeout 900
  node chatgpt_web_bridge.mjs ui-chatgpt images --json
  node chatgpt_web_bridge.mjs ui-chatgpt download-images --output-dir ./chatgpt-output --prefix slide

常用选项:
  --browser             使用 chatgpt.com 浏览器界面，默认
  --desktop             使用 ChatGPT macOS 桌面 App
  --timeout <seconds>   等待回复的最长秒数
  --prompt-file <path>  从文件读取提示词
  --clipboard           从剪贴板读取提示词
  --output-dir <path>   保存 ChatGPT 当前会话图片
  --prefix <name>       下载图片文件名前缀
  --limit <n>           每次最多下载最近 n 张可见图片，默认 8
  --url <chat-url>      在指定 ChatGPT 会话中发送
  --current             不重新打开首页，直接使用当前浏览器页
`);
}

function parseArgs(argv) {
  const opts = {
    mode: process.env.GOBE_CHATGPT_MODE || 'browser',
    timeout: undefined,
    promptFile: undefined,
    clipboard: false,
    json: false,
    focus: true,
    current: false,
    url: undefined,
  };
  const positional = [];
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--browser') opts.mode = 'browser';
    else if (arg === '--desktop') opts.mode = 'desktop';
    else if (arg === '--auto') opts.mode = 'auto';
    else if (arg === '--json') opts.json = true;
    else if (arg === '--no-focus') opts.focus = false;
    else if (arg === '--current') opts.current = true;
    else if (arg === '--url') opts.url = argv[++i];
    else if (arg.startsWith('--url=')) opts.url = arg.slice('--url='.length);
    else if (arg === '--clipboard') opts.clipboard = true;
    else if (arg === '--output-dir') opts.outputDir = argv[++i];
    else if (arg.startsWith('--output-dir=')) opts.outputDir = arg.slice('--output-dir='.length);
    else if (arg === '--op') opts.outputDir = argv[++i];
    else if (arg.startsWith('--op=')) opts.outputDir = arg.slice('--op='.length);
    else if (arg === '--prefix') opts.prefix = argv[++i];
    else if (arg.startsWith('--prefix=')) opts.prefix = arg.slice('--prefix='.length);
    else if (arg === '--limit') opts.limit = Number(argv[++i]);
    else if (arg.startsWith('--limit=')) opts.limit = Number(arg.slice('--limit='.length));
    else if (arg === '--model') opts.model = argv[++i];
    else if (arg.startsWith('--model=')) opts.model = arg.slice('--model='.length);
    else if (arg === '--timeout') opts.timeout = Number(argv[++i]);
    else if (arg.startsWith('--timeout=')) opts.timeout = Number(arg.slice('--timeout='.length));
    else if (arg === '--prompt-file') opts.promptFile = argv[++i];
    else if (arg.startsWith('--prompt-file=')) opts.promptFile = arg.slice('--prompt-file='.length);
    else positional.push(arg);
  }
  return { opts, positional };
}

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    encoding: 'utf-8',
    stdio: options.capture ? ['ignore', 'pipe', 'pipe'] : 'inherit',
    env: { ...process.env, ...(options.env || {}) },
  });
  if (options.check !== false && result.status !== 0) {
    if (options.capture) {
      if (result.stdout) process.stdout.write(result.stdout);
      if (result.stderr) process.stderr.write(result.stderr);
    }
    process.exit(result.status || 1);
  }
  return result;
}

function runOpenCLI(args, options = {}) {
  const env = {
    OPENCLI_WINDOW_FOCUSED: options.focus === false ? '0' : '1',
    ...options.env,
  };
  return run(OPENCLI_BIN, args, { ...options, env });
}

function cleanOutput(text) {
  return (text || '')
    .split(/\r?\n/)
    .filter((line) => !line.startsWith('⚠  Could not create symlink'))
    .join('\n')
    .trim();
}

function openUrl(url) {
  if (fs.existsSync('/Applications/Google Chrome.app')) {
    run('/usr/bin/open', ['-a', 'Google Chrome', url], { check: false });
    return;
  }
  run('/usr/bin/open', [url], { check: false });
}

function desktopInstalled() {
  return fs.existsSync('/Applications/ChatGPT.app');
}

function desktopRunning() {
  const out = run('/usr/bin/osascript', ['-e', 'application "ChatGPT" is running'], { capture: true, check: false });
  return cleanOutput(out.stdout) === 'true';
}

function modeFrom(opts) {
  if (opts.mode === 'auto') {
    return desktopInstalled() ? 'desktop' : 'browser';
  }
  return opts.mode || 'browser';
}

function readPrompt(opts, positional) {
  if (opts.promptFile) {
    return fs.readFileSync(path.resolve(opts.promptFile), 'utf-8').trim();
  }
  if (opts.clipboard) {
    const out = run('/usr/bin/pbpaste', [], { capture: true, check: false });
    return cleanOutput(out.stdout);
  }
  if (positional.length > 0) return positional.join(' ').trim();
  if (!process.stdin.isTTY) {
    return fs.readFileSync(0, 'utf-8').trim();
  }
  console.error('缺少提示词。可以直接写在命令后面，或使用 --prompt-file / --clipboard。');
  process.exit(2);
}

function browserDoctor() {
  const res = runOpenCLI(['doctor'], { capture: true, check: false, focus: false });
  const stdout = cleanOutput(res.stdout);
  const stderr = cleanOutput(res.stderr);
  const text = [stdout, stderr].filter(Boolean).join('\n');
  return {
    ok: /\[OK\]\s+Connectivity/.test(text) && !/\[FAIL\]\s+Connectivity/.test(text),
    text,
  };
}

function requireBrowserReady() {
  const doctor = browserDoctor();
  if (doctor.ok) return;
  console.error('OpenCLI 已安装，但 Browser Bridge 扩展还没有连上。');
  console.error('');
  console.error('先运行: node chatgpt_web_bridge.mjs ui-chatgpt setup');
  console.error('然后在 Chrome 里安装 OpenCLI 扩展、登录 chatgpt.com，再重试。');
  console.error('');
  console.error(doctor.text);
  process.exit(2);
}

function browserOpen(opts = {}) {
  requireBrowserReady();
  const url = opts.url || CHATGPT_URL;
  runOpenCLI(['browser', 'open', url], {
    capture: opts.quiet === true,
    focus: opts.focus !== false,
  });
  if (opts.quiet !== true) console.log(`已打开 ChatGPT: ${url}`);
}

function browserEval(js, opts = {}) {
  const res = runOpenCLI(['browser', 'eval', js], { capture: true, check: false, focus: opts.focus !== false });
  const stdout = cleanOutput(res.stdout);
  const stderr = cleanOutput(res.stderr);
  if (res.status !== 0) {
    if (stdout) console.error(stdout);
    if (stderr) console.error(stderr);
    process.exit(res.status || 1);
  }
  return stdout;
}

function browserStateObject(opts = {}) {
  const raw = browserEval(ASSISTANT_STATE_JS, opts);
  try {
    return JSON.parse(raw);
  } catch {
    return {
      url: '',
      title: '',
      assistantCount: 0,
      userCount: 0,
      lastAssistant: raw,
      busy: false,
      imageCount: 0,
      lastImages: [],
    };
  }
}

function imageExtFromMime(mime) {
  if (/png/i.test(mime || '')) return '.png';
  if (/webp/i.test(mime || '')) return '.webp';
  if (/gif/i.test(mime || '')) return '.gif';
  if (/jpeg|jpg/i.test(mime || '')) return '.jpg';
  return '.png';
}

function safeName(value) {
  return String(value || 'chatgpt')
    .replace(/[\\/:*?"<>|]+/g, '-')
    .replace(/\s+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 80) || 'chatgpt';
}

async function browserDownloadImages(opts = {}) {
  requireBrowserReady();
  const outputDir = path.resolve(opts.outputDir || './chatgpt-output');
  const prefix = safeName(opts.prefix || 'chatgpt-image');
  const limit = Number.isFinite(Number(opts.limit)) && Number(opts.limit) > 0 ? Math.min(50, Number(opts.limit)) : 8;
  fs.mkdirSync(outputDir, { recursive: true });
  const stamp = new Date().toISOString().replace(/[-:.TZ]/g, '').slice(0, 14);
  const js = `(
    async () => {
      const isVisible = (el) => {
        if (!(el instanceof HTMLElement)) return false;
        const style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden') return false;
        const rect = el.getBoundingClientRect();
        const width = el.naturalWidth || el.width || rect.width || 0;
        const height = el.naturalHeight || el.height || rect.height || 0;
        const src = el.currentSrc || el.src || '';
        const generatedGalleryAsset = /\\/backend-api\\/estuary\\/content/i.test(src) && width >= 128 && height >= 128;
        return generatedGalleryAsset || (rect.width > 96 && rect.height > 96);
      };
      const conversationTurns = Array.from(document.querySelectorAll('section[data-testid^="conversation-turn-"]'));
      const assistantTurns = conversationTurns.filter((node) => /ChatGPT/i.test(node.querySelector('h4')?.textContent || ''));
      const assistantNodes = Array.from(new Set([
        ...document.querySelectorAll('[data-message-author-role="assistant"]'),
        ...assistantTurns,
      ]));
      const candidates = assistantNodes.flatMap((node) => Array.from(node.querySelectorAll('img')))
        .filter((img) => img instanceof HTMLImageElement && isVisible(img))
        .map((img) => ({
          src: img.currentSrc || img.src || '',
          alt: img.alt || '',
          width: img.naturalWidth || img.width || 0,
          height: img.naturalHeight || img.height || 0,
          cls: String(img.className || '')
        }))
        .filter((item) => item.src && item.width >= 128 && item.height >= 128)
        .filter((item) => !/avatar|profile|logo|icon/i.test(item.alt + ' ' + item.cls));
      const seen = new Set();
      const unique = candidates.filter((item) => {
        if (seen.has(item.src)) return false;
        seen.add(item.src);
        return true;
      }).slice(-${limit});
      const extFromMime = (mime) => {
        if (/webp/i.test(mime || '')) return '.webp';
        if (/gif/i.test(mime || '')) return '.gif';
        if (/jpe?g/i.test(mime || '')) return '.jpg';
        return '.png';
      };
      const assets = [];
      const prefix = ${JSON.stringify(prefix)};
      const stamp = ${JSON.stringify(stamp)};
      for (const item of unique) {
        try {
          let mimeType = 'image/png';
          const res = await fetch(item.src, { credentials: 'include' });
          const blob = await res.blob();
          mimeType = blob.type || mimeType;
          const ext = extFromMime(mimeType);
          const fileName = prefix + '-' + stamp + '-' + String(assets.length + 1).padStart(2, '0') + ext;
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = fileName;
          a.style.display = 'none';
          document.body.appendChild(a);
          a.click();
          setTimeout(() => URL.revokeObjectURL(url), 15000);
          a.remove();
          assets.push({ fileName, mimeType, alt: item.alt, width: item.width, height: item.height, src: item.src });
        } catch (error) {
          assets.push({ error: error?.message || String(error), src: item.src, alt: item.alt, width: item.width, height: item.height });
        }
      }
      return JSON.stringify({ url: location.href, title: document.title, count: assets.length, assets });
    }
  )()`;
  const raw = browserEval(js, opts);
  let payload;
  try {
    payload = JSON.parse(raw);
  } catch {
    console.error('无法解析图片下载结果。');
    console.error(raw);
    process.exit(1);
  }
  const saved = [];
  const failed = [];
  const downloadsDir = path.join(os.homedir(), 'Downloads');
  const waitForFile = (file, timeoutMs = 30000) => {
    const started = Date.now();
    while (Date.now() - started < timeoutMs) {
      if (fs.existsSync(file) && !fs.existsSync(`${file}.crdownload`)) return true;
      Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 500);
    }
    return false;
  };
  for (let i = 0; i < (payload.assets || []).length; i += 1) {
    const asset = payload.assets[i];
    if (!asset.fileName || asset.error) {
      failed.push(asset);
      continue;
    }
    const from = path.join(downloadsDir, asset.fileName);
    const to = path.join(outputDir, asset.fileName);
    if (!waitForFile(from)) {
      failed.push({ ...asset, error: `download not found in ${downloadsDir}` });
      continue;
    }
    fs.renameSync(from, to);
    saved.push({ file: to, width: asset.width, height: asset.height, mimeType: asset.mimeType, alt: asset.alt || '' });
  }
  const manifest = { url: payload.url, title: payload.title, outputDir, saved, failed };
  fs.writeFileSync(path.join(outputDir, `${prefix}-${stamp}-manifest.json`), JSON.stringify(manifest, null, 2));
  if (opts.json) console.log(JSON.stringify(manifest, null, 2));
  else {
    console.log(`已保存 ${saved.length} 张图片到: ${outputDir}`);
    for (const item of saved) console.log(item.file);
    if (failed.length) console.log(`有 ${failed.length} 张图片下载失败，详情见 manifest。`);
  }
}

function tryBrowserPromptSelector(text, opts = {}) {
  let lastError = '';
  for (const selector of PROMPT_SELECTOR_CANDIDATES) {
    const find = runOpenCLI(['browser', 'find', '--css', selector, '--limit', '1'], {
      capture: true,
      check: false,
      focus: opts.focus !== false,
    });
    if (find.status !== 0 || /"matches_n"\s*:\s*0/.test(find.stdout || '')) {
      lastError = cleanOutput(find.stderr || find.stdout);
      continue;
    }
    runOpenCLI(['browser', 'click', selector, '--nth', '0'], { capture: true, focus: opts.focus !== false });
    runOpenCLI(['browser', 'keys', 'Control+a'], { capture: true, focus: opts.focus !== false });
    const typed = runOpenCLI(['browser', 'type', selector, text, '--nth', '0'], {
      capture: true,
      check: false,
      focus: opts.focus !== false,
    });
    if (typed.status === 0) return selector;
    lastError = cleanOutput(typed.stderr || typed.stdout);
  }
  console.error('没有找到 ChatGPT 输入框。请确认 chatgpt.com 已打开并已登录。');
  if (lastError) console.error(lastError);
  process.exit(3);
}

function browserSend(prompt, opts = {}) {
  if (!opts.current) browserOpen({ ...opts, quiet: true });
  else requireBrowserReady();
  runOpenCLI(['browser', 'wait', 'selector', '#prompt-textarea, textarea, div.ProseMirror, [contenteditable="true"]', '--timeout', '30000'], {
    capture: true,
    check: false,
    focus: opts.focus !== false,
  });
  const selector = tryBrowserPromptSelector(prompt, opts);
  runOpenCLI(['browser', 'keys', 'Enter'], { capture: true, focus: opts.focus !== false });
  console.log(`已发送到 ChatGPT 浏览器界面。输入框选择器: ${selector}`);
}

async function sleep(ms) {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

async function browserAsk(prompt, opts = {}) {
  if (!opts.current) browserOpen({ ...opts, quiet: true });
  else requireBrowserReady();
  const before = browserStateObject(opts);
  runOpenCLI(['browser', 'wait', 'selector', '#prompt-textarea, textarea, div.ProseMirror, [contenteditable="true"]', '--timeout', '30000'], {
    capture: true,
    check: false,
    focus: opts.focus !== false,
  });
  tryBrowserPromptSelector(prompt, opts);
  runOpenCLI(['browser', 'keys', 'Enter'], { capture: true, focus: opts.focus !== false });

  const timeoutSeconds = Number(opts.timeout || 180);
  const deadline = Date.now() + timeoutSeconds * 1000;
  let last = browserStateObject(opts);
  let stableText = '';
  let stableTicks = 0;
  let stableImageCount = before.imageCount || 0;
  let stableImageTicks = 0;

  while (Date.now() < deadline) {
    await sleep(2500);
    last = browserStateObject(opts);
    const changed =
      last.assistantCount > before.assistantCount ||
      last.lastAssistant !== before.lastAssistant ||
      (last.imageCount || 0) > (before.imageCount || 0);
    if (!changed) continue;
    if (last.busy) continue;
    if ((last.imageCount || 0) > (before.imageCount || 0)) {
      if (last.imageCount === stableImageCount) stableImageTicks += 1;
      else {
        stableImageCount = last.imageCount || 0;
        stableImageTicks = 1;
      }
      if (stableImageTicks >= 2) break;
    }
    if (last.lastAssistant && last.lastAssistant === stableText) stableTicks += 1;
    else {
      stableText = last.lastAssistant || '';
      stableTicks = 1;
    }
    if (stableTicks >= 2) break;
  }

  if (opts.json) {
    console.log(JSON.stringify(last, null, 2));
    return;
  }
  if (last.lastAssistant) {
    console.log(last.lastAssistant);
  } else {
    console.log(`在 ${timeoutSeconds}s 内没有读到可见回复。ChatGPT 可能仍在生成，或当前回复是图片/画布类内容。`);
  }
  if (last.imageCount > 0) {
    console.log('');
    console.log(`检测到 ${last.imageCount} 张图片。可运行: node chatgpt_web_bridge.mjs ui-chatgpt images --json`);
  }
}

function desktopCommand(command, prompt, opts = {}) {
  if (!desktopInstalled()) {
    console.error('没有找到 /Applications/ChatGPT.app。当前机器未安装 ChatGPT 桌面版。');
    process.exit(2);
  }
  if (!desktopRunning()) {
    run('/usr/bin/open', ['-a', 'ChatGPT'], { check: false });
  }
  const args = ['chatgpt-app', command];
  if (command === 'ask' || command === 'send') {
    if (opts.model) args.push('--model', opts.model);
    if (command === 'ask') args.push('--timeout', String(opts.timeout || 180), '--format', opts.json ? 'json' : 'plain');
    args.push(prompt);
  } else if (command === 'read') {
    args.push('--format', opts.json ? 'json' : 'plain');
  }
  runOpenCLI(args, { focus: false });
}

function commandSetup() {
  console.log('已准备本地 OpenCLI。接下来需要给浏览器装桥接扩展，并登录 ChatGPT。');
  console.log('');
  console.log('1. 安装 OpenCLI Chrome 扩展:');
  console.log(`   ${OPENCLI_EXTENSION_URL}`);
  console.log('2. 打开并登录 ChatGPT:');
  console.log(`   ${CHATGPT_URL}`);
  console.log('3. 验证:');
  console.log('   node chatgpt_web_bridge.mjs ui-chatgpt doctor');
  console.log('');
  openUrl(OPENCLI_EXTENSION_URL);
  openUrl(CHATGPT_URL);
}

function commandDoctor() {
  console.log('OpenCLI:');
  runOpenCLI(['--version'], { focus: false });
  console.log('');
  runOpenCLI(['doctor'], { focus: false });
  console.log('');
  console.log(`ChatGPT 桌面版: ${desktopInstalled() ? (desktopRunning() ? '已安装，正在运行' : '已安装，未运行') : '未安装'}`);
}

function commandStatus() {
  const version = runOpenCLI(['--version'], { capture: true, check: false, focus: false });
  const doctor = browserDoctor();
  console.log(`OpenCLI: ${cleanOutput(version.stdout) || 'unknown'}`);
  console.log(`Browser Bridge: ${doctor.ok ? 'connected' : 'not connected'}`);
  console.log(`ChatGPT Desktop: ${desktopInstalled() ? (desktopRunning() ? 'running' : 'installed, stopped') : 'not installed'}`);
  console.log(`Default mode: ${process.env.GOBE_CHATGPT_MODE || 'browser'}`);
}

async function main() {
  const argv = process.argv.slice(2);
  if (argv.length === 0 || argv[0] === '-h' || argv[0] === '--help') {
    usage();
    return;
  }
  const scope = argv.shift();
  if (scope !== 'ui-chatgpt') {
    console.error(`未知命令: ${scope}`);
    usage();
    process.exit(2);
  }
  const sub = argv.shift() || 'help';
  const { opts, positional } = parseArgs(argv);

  if (sub === 'help' || sub === '-h' || sub === '--help') return usage();
  if (sub === 'setup') return commandSetup();
  if (sub === 'doctor') return commandDoctor();
  if (sub === 'status') return commandStatus();

  if (sub === 'open' || sub === 'new') {
    if (positional[0]) opts.url = positional[0];
    return browserOpen(opts);
  }
  if (sub === 'state') {
    requireBrowserReady();
    return runOpenCLI(['browser', 'state'], { focus: opts.focus });
  }
  if (sub === 'images') {
    requireBrowserReady();
    const state = browserStateObject(opts);
    if (opts.json) console.log(JSON.stringify(state.lastImages || [], null, 2));
    else console.log((state.lastImages || []).map((img) => img.src).join('\n'));
    return;
  }
  if (sub === 'download-images') return browserDownloadImages(opts);
  if (sub === 'read') {
    if (modeFrom(opts) === 'desktop') return desktopCommand('read', '', opts);
    requireBrowserReady();
    const state = browserStateObject(opts);
    if (opts.json) console.log(JSON.stringify(state, null, 2));
    else console.log(state.lastAssistant || '没有读到可见的 Assistant 回复。');
    return;
  }

  if (['send', 'ask', 'image', 'research'].includes(sub)) {
    let prompt = readPrompt(opts, positional);
    if (sub === 'image') {
      prompt = `请直接生成图片，不要只给文字说明。图片需求如下：\n\n${prompt}`;
      opts.timeout = opts.timeout || 300;
    }
    if (sub === 'research') {
      prompt = `请尽量使用 ChatGPT 的 Deep Research/深度研究能力完成这个任务。如果当前界面无法自动切换深度研究工具，就先给出可执行的研究计划，再基于可访问资料完成尽可能扎实的研究报告。\n\n研究主题：\n${prompt}`;
      opts.timeout = opts.timeout || 900;
    }
    const mode = modeFrom(opts);
    if (mode === 'desktop') {
      return desktopCommand(sub === 'send' ? 'send' : 'ask', prompt, opts);
    }
    requireBrowserReady();
    if (sub === 'send') return browserSend(prompt, opts);
    return browserAsk(prompt, opts);
  }

  console.error(`未知 ui-chatgpt 子命令: ${sub}`);
  usage();
  process.exit(2);
}

main().catch((error) => {
  console.error(error?.message || String(error));
  process.exit(1);
});
