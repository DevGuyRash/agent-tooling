const primes: number[] = [];
for (let n = 2; primes.length < 64; n++) if (primes.every(p => n % p !== 0)) primes.push(n);
const words = primes.map(p => Math.floor((Math.cbrt(p) % 1) * 0x100000000) >>> 0);
const initialState = primes.slice(0, 8).map(p => Math.floor((Math.sqrt(p) % 1) * 0x100000000) >>> 0);

/** Stable content identity over exact JavaScript code units, without normalization. */
export function fingerprint(value: string): string {
  const state = initialState.slice();
  const size = value.length * 2, padded = Math.ceil((size + 9) / 64) * 64, bytes = new Uint8Array(padded);
  for (let i = 0; i < value.length; i++) { const code = value.charCodeAt(i); bytes[i * 2] = code & 255; bytes[i * 2 + 1] = code >>> 8; }
  bytes[size] = 128;
  const bits = size * 8;
  for (let i = 0; i < 8; i++) bytes[padded - 1 - i] = Math.floor(bits / 2 ** (i * 8)) & 255;
  const rotate = (x: number, n: number) => (x >>> n) | (x << (32 - n));
  for (let offset = 0; offset < padded; offset += 64) {
    const w: number[] = [];
    for (let i = 0; i < 16; i++) { const p = offset + i * 4; w[i] = (bytes[p] << 24) | (bytes[p + 1] << 16) | (bytes[p + 2] << 8) | bytes[p + 3]; }
    for (let i = 16; i < 64; i++) { const x = w[i - 15], y = w[i - 2]; w[i] = (w[i - 16] + (rotate(x, 7) ^ rotate(x, 18) ^ (x >>> 3)) + w[i - 7] + (rotate(y, 17) ^ rotate(y, 19) ^ (y >>> 10))) | 0; }
    let [a, b, c, d, e, f, g, h] = state;
    for (let i = 0; i < 64; i++) {
      const one = (h + (rotate(e, 6) ^ rotate(e, 11) ^ rotate(e, 25)) + ((e & f) ^ (~e & g)) + words[i] + w[i]) | 0;
      const two = ((rotate(a, 2) ^ rotate(a, 13) ^ rotate(a, 22)) + ((a & b) ^ (a & c) ^ (b & c))) | 0;
      h = g; g = f; f = e; e = (d + one) | 0; d = c; c = b; b = a; a = (one + two) | 0;
    }
    for (const [i, x] of [a, b, c, d, e, f, g, h].entries()) state[i] = (state[i] + x) >>> 0;
  }
  return 'sha256-utf16le:' + state.map(x => x.toString(16).padStart(8, '0')).join('');
}
