import { Repository, MemoryRepository, Unrelated, helper as renamedHelper } from './domain';
export function load(repo: Repository): string { return repo.fetch(); }
export function run(): string { return load(new MemoryRepository()) + renamedHelper(); }
export function decoy(): string { return new Unrelated().fetch(); }
