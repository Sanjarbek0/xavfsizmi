export type Locale = 'uz' | 'ru' | 'en';

export interface BreachSummary {
  name: string;
  title?: string;
  domain?: string;
  breachDate?: string;
  pwnCount?: number;
  isVerified?: boolean;
  isSensitive?: boolean;
  dataClasses?: string[];
}

export interface AccountLookupResponse {
  email: string;
  breaches: BreachSummary[];
}

export interface PwnedPasswordRangeMatch {
  suffix: string;
  count: number;
}

export interface PwnedPasswordResponse {
  prefix: string;
  matches: PwnedPasswordRangeMatch[];
}

export interface ProblemDetails {
  type?: string;
  title: string;
  detail?: string;
  status: number;
  instance?: string;
}

export interface DomainSummary {
  id: string;
  domain: string;
  verifiedAt?: string;
  verifyMethod?: 'dns_txt' | 'email' | 'meta';
}

export interface ApiKeyTier {
  name: 'free' | 'pro' | 'high_rpm';
  rpm: number;
  monthlyCap?: number;
}

export const SUPPORTED_LOCALES: readonly Locale[] = ['uz', 'ru', 'en'] as const;

export function isLocale(value: string): value is Locale {
  return (SUPPORTED_LOCALES as readonly string[]).includes(value);
}
