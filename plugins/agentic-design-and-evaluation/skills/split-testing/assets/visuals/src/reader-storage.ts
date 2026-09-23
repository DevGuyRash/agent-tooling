import { exactJson } from './exact-json';
/** Shared browser storage ownership. Callbacks run synchronously in one IDB transaction. */
export interface StorageOwner { kind: "notebook" | "preferences"; reportId: string; revision: string }
export type OwnedStoreResult<T> =
  | { status: "ready" | "saved"; value: T | null; source: "database" | "legacy" | "empty" }
  | { status: "blocked" | "unavailable"; message: string; raw?: string; value?: T | null };
export interface OwnedStore<T> {
  read(): Promise<OwnedStoreResult<T>>;
  update(change: (current: T | null) => T): Promise<OwnedStoreResult<T>>;
  close(): void;
}
const databaseName = "agentic-visuals-reader-records";
const storeName = "records";
const databases = new WeakMap<IDBFactory, Promise<IDBDatabase>>();
interface Envelope<T> { version: 1; owner: StorageOwner; value: T }
function unavailable<T>(): OwnedStoreResult<T> { return { status: "unavailable", message: "Browser saving is unavailable. Keep this report open and export a copy of your records." }; }
function rawValue(value: unknown): string | undefined { try { return exactJson(value); } catch { return undefined; } }
function open(factory: IDBFactory): Promise<IDBDatabase> {
  const prior = databases.get(factory);
  if (prior) return prior;
  const pending = new Promise<IDBDatabase>((resolve, reject) => {
    let settled = false;
    const timeout = setTimeout(() => finish(), 5000);
    const finish = (database?: IDBDatabase): void => {
      if (settled) { database?.close(); return; }
      settled = true; clearTimeout(timeout);
      if (database) {
        database.onversionchange = () => { database.close(); databases.delete(factory); };
        resolve(database);
      } else reject(new Error("Browser record storage could not be opened."));
    };
    try {
      const request = factory.open(databaseName, 1);
      request.onupgradeneeded = () => { if (!request.result.objectStoreNames.contains(storeName)) request.result.createObjectStore(storeName); };
      request.onsuccess = () => finish(request.result);
      request.onerror = () => finish();
      request.onblocked = () => finish();
    } catch { finish(); }
  });
  databases.set(factory, pending);
  void pending.catch(() => { if (databases.get(factory) === pending) databases.delete(factory); });
  return pending;
}

/** Legacy bytes are never changed. A caller-owned strict decoder supplies its schema. */
export function createOwnedStore<T>(window: Window | null, key: string, owner: StorageOwner, decodeLegacy?: (raw: string) => T): OwnedStore<T> {
  if (typeof key !== "string" || !key.trim() || !owner.reportId?.trim() || !owner.revision?.trim() || !["notebook", "preferences"].includes(owner.kind)) throw new TypeError("Saved records need a key, kind, stable report ID and revision.");
  const identity = { kind: owner.kind, reportId: owner.reportId, revision: owner.revision };
  let closed = false;
  function legacy(): { result: OwnedStoreResult<T>; raw?: string } {
    let raw: string | null;
    try { if (!window?.localStorage) return { result: { status: "ready", value: null, source: "empty" } }; raw = window.localStorage.getItem(key); }
    catch { return { result: { status: "unavailable", message: "Earlier saved records could not be read. They remain protected; use session records and export." } }; }
    if (raw === null) return { result: { status: "ready", value: null, source: "empty" } };
    try {
      if (!decodeLegacy) throw new Error("No legacy decoder");
      return { result: { status: "ready", value: decodeLegacy(raw), source: "legacy" }, raw };
    } catch { return { result: { status: "blocked", raw, message: "Earlier saved data belongs to another record type, report or revision, or cannot be read safely. The original remains protected." }, raw }; }
  }
  function owned(value: unknown): OwnedStoreResult<T> {
    const item = value as Partial<Envelope<T>> | null;
    if (!item || typeof item !== "object" || Array.isArray(item) || item.version !== 1 || !item.owner || item.owner.kind !== identity.kind || item.owner.reportId !== identity.reportId || item.owner.revision !== identity.revision || !Object.prototype.hasOwnProperty.call(item, "value")) return { status: "blocked", raw: rawValue(value), message: "This saving key belongs to another record type, report or revision, or contains unsupported data. The original remains protected." };
    return { status: "ready", value: item.value!, source: "database" };
  }
  async function transact(change?: (current: T | null) => T): Promise<OwnedStoreResult<T>> {
    if (closed) return unavailable();
    let factory: IDBFactory | undefined, database: IDBDatabase;
    try { factory = window?.indexedDB; if (!factory) throw new Error("Unavailable"); database = await open(factory); }
    catch {
      if (change || closed) return unavailable();
      const prior = legacy().result;
      return prior.status === "ready" ? { ...unavailable<T>(), value: prior.value } : prior;
    }
    if (closed) return unavailable();
    return new Promise(resolve => {
      let result: OwnedStoreResult<T> | undefined;
      let transaction: IDBTransaction;
      try { transaction = database.transaction(storeName, change ? "readwrite" : "readonly"); }
      catch { databases.delete(factory!); resolve(unavailable()); return; }
      let finished = false;
      const finish = (outcome: OwnedStoreResult<T>): void => {
        if (finished) return;
        finished = true; clearTimeout(timeout); resolve(outcome);
      };
      // A suspended/broken transaction must not leave saving and export pending
      // forever. Request success alone still never means a durable commit.
      const timeout = setTimeout(() => {
        const failure: OwnedStoreResult<T> = { status: 'unavailable', message: 'Browser saving did not finish in time. The saved copy has not been confirmed. Keep this report open and export your session records.' };
        finish(failure);
        try { transaction.abort(); } catch { /* Completion may have raced the timeout. */ }
      }, 15000);
      transaction.oncomplete = () => finish(result || unavailable());
      transaction.onabort = () => finish(result?.status === "blocked" ? result : unavailable());
      transaction.onerror = () => { /* The transaction abort, not a request success, determines failure. */ };
      try {
        const records = transaction.objectStore(storeName), request = records.get(key);
        request.onerror = () => { result = unavailable(); };
        request.onsuccess = () => {
          if (finished) return;
          const fallback = request.result === undefined ? legacy() : { result: owned(request.result) };
          const current = fallback.result;
          if (current.status !== "ready" && current.status !== "saved") { result = current; return; }
          if (!change) { result = current; return; }
          try {
            const next = change(current.value);
            const put = records.put({ version: 1, owner: identity, value: next } satisfies Envelope<T>, key);
            put.onerror = () => { result = unavailable(); };
            result = { status: "saved", value: next, source: "database" };
          } catch {
            result = { status: "blocked", raw: fallback.raw ?? rawValue(current.value), message: "Saved records changed or could not be combined safely. Both your session records and the earlier saved copy remain available for export." };
            transaction.abort();
          }
        };
      } catch { result = unavailable(); try { transaction.abort(); } catch { finish(result); } }
    });
  }
  return { read: () => transact(), update: change => transact(change), close: () => { closed = true; } };
}
