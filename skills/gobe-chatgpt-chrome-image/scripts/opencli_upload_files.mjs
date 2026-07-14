#!/usr/bin/env node

import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';

function resolveOpenCLIBrowserModule() {
  const configured = process.env.OPENCLI_BROWSER_MODULE;
  if (configured && fs.existsSync(configured)) return path.resolve(configured);

  const npm = process.env.NPM_BIN || 'npm';
  const result = spawnSync(npm, ['root', '-g'], { encoding: 'utf-8' });
  const globalRoot = (result.stdout || '').trim();
  if (result.status === 0 && globalRoot) {
    const candidate = path.join(
      globalRoot,
      '@jackwener',
      'opencli',
      'dist',
      'src',
      'browser',
      'index.js',
    );
    if (fs.existsSync(candidate)) return candidate;
  }

  throw new Error(
    'Cannot locate the OpenCLI browser module. Install @jackwener/opencli globally ' +
      'or set OPENCLI_BROWSER_MODULE to dist/src/browser/index.js.',
  );
}

function usage() {
  console.error('Usage: opencli_upload_files.mjs <css-selector> <file> [file ...]');
}

const [selector, ...rawFiles] = process.argv.slice(2);
if (!selector || rawFiles.length === 0) {
  usage();
  process.exit(2);
}

const files = rawFiles.map((item) => path.resolve(item));
for (const file of files) {
  if (!fs.existsSync(file) || !fs.statSync(file).isFile()) {
    console.error(`Reference image not found: ${file}`);
    process.exit(2);
  }
}

const { BrowserBridge } = await import(resolveOpenCLIBrowserModule());
const bridge = new BrowserBridge();

try {
  const page = await bridge.connect({ timeout: 30, workspace: 'browser:default' });
  const uploadId = `gobe-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  await page.evaluate(`(() => {
    window.__gobeFileUploads = window.__gobeFileUploads || {};
    window.__gobeFileUploads[${JSON.stringify(uploadId)}] = [];
    return true;
  })()`);

  for (const file of files) {
    const encoded = fs.readFileSync(file).toString('base64');
    const mime = file.toLowerCase().endsWith('.png')
      ? 'image/png'
      : file.toLowerCase().endsWith('.webp')
        ? 'image/webp'
        : 'image/jpeg';
    await page.evaluate(`(() => {
      window.__gobeFileUploads[${JSON.stringify(uploadId)}].push({
        name: ${JSON.stringify(path.basename(file))},
        type: ${JSON.stringify(mime)},
        chunks: []
      });
      return true;
    })()`);
    const itemIndex = files.indexOf(file);
    for (let offset = 0; offset < encoded.length; offset += 180_000) {
      const chunk = encoded.slice(offset, offset + 180_000);
      await page.evaluate(`(() => {
        window.__gobeFileUploads[${JSON.stringify(uploadId)}][${itemIndex}].chunks.push(${JSON.stringify(chunk)});
        return true;
      })()`);
    }
  }

  const applied = await page.evaluate(`(() => {
    const input = document.querySelector(${JSON.stringify(selector)});
    if (!(input instanceof HTMLInputElement) || input.type !== 'file') {
      return { ok: false, error: 'file input not found' };
    }
    const staged = window.__gobeFileUploads?.[${JSON.stringify(uploadId)}] || [];
    const transfer = new DataTransfer();
    for (const item of staged) {
      const binary = atob(item.chunks.join(''));
      const bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
      transfer.items.add(new File([bytes], item.name, { type: item.type }));
    }
    input.files = transfer.files;
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
    delete window.__gobeFileUploads[${JSON.stringify(uploadId)}];
    return { ok: true, count: transfer.files.length };
  })()`);
  if (!applied?.ok || applied.count !== files.length) {
    throw new Error(applied?.error || `only staged ${applied?.count || 0} of ${files.length} files`);
  }
  console.log(JSON.stringify({ ok: true, selector, count: files.length, files }, null, 2));
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
} finally {
  await bridge.close();
}
