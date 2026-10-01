package demo;
public class App {
  public static String load(Repository repo) { return repo.fetch(); }
  public static String run() { return load(new MemoryRepository()); }
  public static String decoy() { return new Unrelated().fetch(); }
  public static String overload() { return new MemoryRepository().fetch(1); }
}
