// Symptom: negative quantities reduce the amount instead of being ignored.
int total(List<int> quantities, int unitPrice) {
  return quantities.fold(0, (sum, quantity) => sum + quantity * unitPrice);
}
