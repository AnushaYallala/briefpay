// Polyfill for Node 26 experimental localStorage in jsdom environment
if (typeof globalThis !== "undefined" && "localStorage" in globalThis) {
  try {
    delete (globalThis as Record<string, unknown>).localStorage;
  } catch {
    // ignore
  }
}

let store: Record<string, string> = {};
Storage.prototype.getItem = vi.fn(function (key: string) {
  return store[key] ?? null;
});
Storage.prototype.setItem = vi.fn(function (key: string, value: string) {
  store[key] = String(value);
});
Storage.prototype.removeItem = vi.fn(function (key: string) {
  delete store[key];
});
Storage.prototype.clear = vi.fn(function () {
  store = {};
});
Storage.prototype.key = vi.fn(function (index: number) {
  return Object.keys(store)[index] ?? null;
});
Object.defineProperty(Storage.prototype, "length", {
  get: function () {
    return Object.keys(store).length;
  },
  configurable: true,
});

const mockStorage = Object.create(Storage.prototype);
Object.defineProperty(window, "localStorage", {
  value: mockStorage,
  configurable: true,
  writable: true,
});
