package demo;
public class MemoryRepository implements Repository {
  public String fetch() { return "memory"; }
  public String fetch(int index) { return "memory" + index; }
}
