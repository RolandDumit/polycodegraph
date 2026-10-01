package domain

type Repository interface { Fetch() string }
type MemoryRepository struct { Label string }
type Unrelated struct{}
func (r Unrelated) Fetch() string { return "other" }
func Helper() string { return "ok" }
