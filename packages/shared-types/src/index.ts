export type Locale = 'uz' | 'ru' | 'en';

export interface BreachSummary {
  name: string;
  title?: string;
  domain?: string;
  breachDate?: string;
  pwnCount?: number;
  isVerified?: boolean;
  isSensitive?: boolean;
  isFabricated?: boolean;
  isRetired?: boolean;
  isSpamList?: boolean;
  description?: string;
  dataClasses?: string[];
  logoPath?: string;
}

export interface AccountLookupResponse {
  email: string;
  breaches: BreachSummary[];
  cached?: boolean;
}

export interface PasteSummary {
  source: string;
  id: string;
  title?: string;
  date?: string;
  emailCount?: number;
}

export interface PasteLookupResponse {
  email: string;
  pastes: PasteSummary[];
  cached?: boolean;
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

export interface NotificationSubscribeRequest {
  email: string;
  locale?: Locale;
  turnstileToken?: string | null;
}

export interface NotificationSubscribeResponse {
  message: string;
}

export interface DomainSummary {
  id: string;
  domain: string;
  verifiedAt?: string;
  verifyMethod?: 'dns_txt' | 'email' | 'meta_tag';
}

export type ApiKeyTierName = 'free' | 'pro' | 'high_rpm';

export interface ApiKeyTier {
  name: ApiKeyTierName;
  rpm: number;
  monthlyCap?: number;
}

export const SUPPORTED_LOCALES: readonly Locale[] = ['uz', 'ru', 'en'] as const;

export function isLocale(value: string): value is Locale {
  return (SUPPORTED_LOCALES as readonly string[]).includes(value);
}
