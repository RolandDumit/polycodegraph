import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:get_it/get_it.dart';
import 'package:go_router/go_router.dart';
import 'domain.dart';

final userRepositoryProvider = Provider<UserRepository>(
  (ref) => MemoryUserRepository(),
);
final homeRoute = GoRoute(
  path: '/',
  builder: (context, state) => const HomeScreen(),
);

class UserCubit extends Cubit<User?> {
  UserCubit(this.loadUser) : super(null);
  final LoadUserUseCase loadUser;
  void load() => emit(loadUser());
}

void registerServices() {
  GetIt.I.registerLazySingleton<UserRepository>(() => MemoryUserRepository());
  GetIt.I.registerFactory<LoadUserUseCase>(
    () => LoadUserUseCase(GetIt.I<UserRepository>()),
  );
}

class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});
  @override
  Widget build(BuildContext context) =>
      const Scaffold(body: Text('dart-codegraph fixture'));
}

void main() {
  registerServices();
  runApp(const HomeScreen());
}
