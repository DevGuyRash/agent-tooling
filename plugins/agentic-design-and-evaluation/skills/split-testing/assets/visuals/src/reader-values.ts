function fail(message:string):never { throw new Error(message); }
export function readerTimestamp(value: unknown, label: string): string {
  if(typeof value!=="string")throw new Error(`${label} must be a string.`);
  const text = value;
  const parts = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(?:Z|([+-])(\d{2}):(\d{2}))$/.exec(text);
  if (!parts) fail(`${label} must be an ISO timestamp with a timezone.`);
  const [, yearText, monthText, dayText, hourText, minuteText, secondText, , offsetHourText, offsetMinuteText] = parts;
  const year = Number(yearText), month = Number(monthText), day = Number(dayText);
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  if (month < 1 || month > 12 || day < 1 || day > days[month - 1] || Number(hourText) > 23 || Number(minuteText) > 59 || Number(secondText) > 59 || Number(offsetHourText || 0) > 23 || Number(offsetMinuteText || 0) > 59) fail(`${label} must be a valid ISO timestamp with a timezone.`);
  return text;
}
