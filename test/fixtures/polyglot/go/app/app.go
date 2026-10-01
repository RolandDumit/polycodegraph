package app

import d "fixture.test/graph/domain"
func Load(repo d.Repository) string { return repo.Fetch() }
func Run() string { return Load(&d.MemoryRepository{Label: d.Helper()}) }
func Decoy() string { return d.Unrelated{}.Fetch() }
