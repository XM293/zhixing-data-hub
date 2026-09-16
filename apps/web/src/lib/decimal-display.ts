/** Format an API decimal string without converting it to a JavaScript number. */
export function displayDecimal(value: string | null | undefined): string {
  if (value == null) return "—";
  if (!/^-?\d+\.\d+$/.test(value)) return value;
  return value.replace(/0+$/, "").replace(/\.$/, "");
}
