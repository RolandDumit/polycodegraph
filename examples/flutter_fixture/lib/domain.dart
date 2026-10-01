import 'package:freezed_annotation/freezed_annotation.dart';

@freezed
class User {
  const User(this.name);
  final String name;
}

abstract class UserRepository {
  User load();
}

class MemoryUserRepository implements UserRepository {
  @override
  User load() => const User('Ada');
}

class LoadUserUseCase {
  LoadUserUseCase(this.repository);
  final UserRepository repository;
  User call() => repository.load();
}
