import 'model.dart';

String display(Event event) => event.data;
String wire(EventDto dto) => dto.toJson()['data']!;
