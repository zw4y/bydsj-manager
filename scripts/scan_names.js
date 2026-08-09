'use strict';

const names = __NAMES__;
const ranges = Process.enumerateRanges({ protection: 'r--', coalesce: true });
const hits = [];
let totalBytes = 0;

function utf16leHex(s) {
  const parts = [];
  for (const ch of s) {
    const code = ch.codePointAt(0);
    parts.push((code & 0xff).toString(16).padStart(2, '0'));
    parts.push((code >> 8).toString(16).padStart(2, '0'));
  }
  return parts.join(' ');
}

function utf8Hex(s) {
  const parts = [];
  const bytes = [];
  for (const ch of s) {
    const code = ch.codePointAt(0);
    if (code < 0x80) bytes.push(code);
    else if (code < 0x800) bytes.push(0xc0 | (code >> 6), 0x80 | (code & 0x3f));
    else bytes.push(0xe0 | (code >> 12), 0x80 | ((code >> 6) & 0x3f), 0x80 | (code & 0x3f));
  }
  return bytes.map((b) => b.toString(16).padStart(2, '0')).join(' ');
}

send({ type: 'start', rangeCount: ranges.length });

let scannedRanges = 0;
const t0 = Date.now();

for (const range of ranges) {
  totalBytes += Number(range.size);
  for (const n of names) {
    for (const [enc, pattern] of [
      ['utf16', utf16leHex(n.name)],
      ['utf8', utf8Hex(n.name)],
    ]) {
      const matches = Memory.scanSync(range.base, range.size, pattern);
      for (const m of matches) {
        hits.push({
          key: n.key,
          name: n.name,
          encoding: enc,
          address: m.address.toString(),
          rangeBase: range.base.toString(),
          rangeSize: range.size.toString(),
          module: range.file ? range.file.path : null,
        });
      }
    }
  }
  scannedRanges += 1;
  if (scannedRanges % 20 === 0) {
    send({
      type: 'progress',
      scannedRanges,
      hitCount: hits.length,
      elapsedMs: Date.now() - t0,
    });
  }
}

send({
  type: 'done',
  hits,
  scannedRanges,
  totalBytes: totalBytes.toString(),
  elapsedMs: Date.now() - t0,
});
