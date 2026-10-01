export interface Repository { fetch(): string; }
export class MemoryRepository implements Repository {
  fetch(): string { return 'memory'; }
}
export class Unrelated { fetch(): string { return 'other'; } }
export function helper(): string { return 'ok'; }
