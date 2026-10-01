part 'model.dart';

abstract class UserRepository {
  UserRepository();
  String fetch();
}

mixin Logging {
  void log(String value) {}
}

class MemoryRepository extends UserRepository with Logging {
  MemoryRepository();
  final String prefix = 'user';
  @override
  String fetch() {
    log(prefix);
    return prefix;
  }
}

class ChildRepository extends MemoryRepository {
  ChildRepository() : super();
  @override
  String fetch() => super.fetch();
}

class AliasRepository = MemoryRepository with Logging;

enum LoadState { idle, loaded }

typedef Loader = String Function();

extension UserLabel on User {
  String get label => name.toUpperCase();
}

String helper() => 'help';

class Unrelated {
  String fetch() => 'other';
}
