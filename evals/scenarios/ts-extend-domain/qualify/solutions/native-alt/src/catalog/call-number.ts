// The house call-number scheme (docs/callnumbers.md) as a value with a shelf-order key.

type Key = (number | string)[];

const COLLECTION_ORDER = ['', 'J', 'YA', 'REF', 'OS'];
const COLLECTION_NAMES = ['Adult', "Children's", 'Young adult', 'Reference', 'Oversize'];
const WORD_CLASS_ORDER = ['', 'B', 'GN', 'FIC']; // '' stands for every Dewey number, which comes first
const WORD_CLASS_NAMES: Record<string, string> = { B: 'Biography', GN: 'Graphic novels', FIC: 'Fiction' };

export class BadCallNumber extends Error {}

export class CallNumber {
  readonly collection: string;
  readonly klass: string;
  readonly mark: string;
  readonly year: number | null;
  readonly volume: number | null;
  readonly copy: number | null;

  private constructor(collection: string, klass: string, mark: string, extras: (number | null)[]) {
    this.collection = collection;
    this.klass = klass;
    this.mark = mark;
    [this.year, this.volume, this.copy] = extras;
  }

  static parse(raw: string): CallNumber {
    const words = raw.trim().toUpperCase().split(/\s+/).filter((w) => w.length > 0);
    if (!words.length) throw new BadCallNumber('no call number');
    let collection = '';
    if (COLLECTION_ORDER.indexOf(words[0]) > 0) {
      collection = words.shift() as string;
      if (!words.length) throw new BadCallNumber(`no class after '${collection}'`);
    }
    const klass = words.shift() as string;
    const dewey = /^[0-9]/.test(klass);
    if (dewey && !/^[0-9]{3}(\.[0-9]+)?$/.test(klass)) throw new BadCallNumber(`bad class number '${klass}'`);
    if (!dewey && !(klass in WORD_CLASS_NAMES)) throw new BadCallNumber(`unknown class '${klass}'`);
    const what = dewey ? 'cutter' : 'name';
    const mark = words.shift();
    if (mark === undefined) throw new BadCallNumber(`no ${what} after '${klass}'`);
    if (!(dewey ? /^[A-Z]{1,3}[0-9]*$/ : /^[A-Z][A-Z'-]*$/).test(mark)) throw new BadCallNumber(`bad ${what} '${mark}'`);
    const extras: (number | null)[] = [null, null, null];
    const patterns = [/^((?:1[5-9]|20)[0-9]{2})$/, /^V\.([1-9][0-9]{0,2})$/, /^C\.([1-9][0-9]{0,2})$/];
    let next = 0;
    for (const word of words) {
      const at = patterns.findIndex((p, i) => i >= next && p.test(word));
      if (at < 0) throw new BadCallNumber(`unexpected '${word}'`);
      extras[at] = Number(patterns[at].exec(word)![1]);
      next = at + 1;
    }
    return new CallNumber(collection, klass, mark, extras);
  }

  toString(): string {
    const parts = [this.collection, this.klass, this.mark];
    if (this.year !== null) parts.push(String(this.year));
    if (this.volume !== null) parts.push(`V.${this.volume}`);
    if (this.copy !== null) parts.push(`C.${this.copy}`);
    return parts.filter((p) => p !== '').join(' ');
  }

  get heading(): string {
    const name = WORD_CLASS_NAMES[this.klass] ?? `${this.klass.charAt(0)}00s`;
    return `${COLLECTION_NAMES[COLLECTION_ORDER.indexOf(this.collection)]} · ${name}`;
  }

  /** Compared element by element, numbers as numbers and strings by code unit, this orders the shelf. */
  get key(): Key {
    const decimal = (digits: string) => digits.replace(/0+$/, '');
    const head: Key = [COLLECTION_ORDER.indexOf(this.collection)];
    if (this.klass in WORD_CLASS_NAMES) {
      head.push(WORD_CLASS_ORDER.indexOf(this.klass), 0, '', this.mark.replace(/['-]/g, ''), '');
    } else {
      const [whole, fraction = ''] = this.klass.split('.');
      const [, letters, digits] = /^([A-Z]+)([0-9]*)$/.exec(this.mark)!;
      head.push(0, Number(whole), decimal(fraction), letters, decimal(digits));
    }
    return [...head, this.year ?? 0, this.volume ?? 0, this.copy ?? 0];
  }
}

export function compareKeys(a: Key, b: Key): number {
  for (let i = 0; i < Math.min(a.length, b.length); i++) {
    if (a[i] !== b[i]) return a[i] < b[i] ? -1 : 1;
  }
  return a.length - b.length;
}
