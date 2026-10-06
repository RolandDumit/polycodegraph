export interface Store { fetch(id: string): string; }
export class MemoryStore implements Store {
  fetch(id: string): string { return `item:${id}`; }
}
export function load(store: Store, id: string): string { return store.fetch(id); }
export function page(store: Store): string { return load(store, 'home'); }
