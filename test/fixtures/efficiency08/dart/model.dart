class Event {
  final String data;
  const Event(this.data);
}

class EventDto {
  final String data;
  const EventDto(this.data);
  Map<String, String> toJson() => {'data': data};
}
