import { MemoryRepository } from '../domain';
export function altRun(): string { return new MemoryRepository().fetch(); }
