import 'domain.dart';
export 'domain.dart' show User, UserRepository;

class LoadUserUseCase {
  LoadUserUseCase(this.repository);
  final UserRepository repository;
  User call() => User(repository.fetch());
}

String run() {
  final repository = MemoryRepository();
  final useCase = LoadUserUseCase(repository);
  final user = useCase();
  return user.label + helper();
}

String decoy() => Unrelated().fetch();
String unresolved(dynamic value) => value.fetch();
