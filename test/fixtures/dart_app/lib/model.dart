part of 'domain.dart';

class User {
  User(this.name);
  User.guest() : this('guest');
  final String name;
}
