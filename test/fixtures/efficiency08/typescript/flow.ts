export function destination(value: string): string { return value.trim(); }
function branch(value: string): string { return destination(value); }
function side(value: string): string { return value.toUpperCase(); }
export function entry(value: string, direct: boolean): string {
  return direct ? branch(value) : side(value);
}
