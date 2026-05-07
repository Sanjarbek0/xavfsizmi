import { useTranslation } from 'react-i18next';
import { Link, useParams } from 'react-router';
import type { BreachSummary } from '@xavfsizmi/shared-types';

interface Props {
  breach: BreachSummary;
  href?: boolean;
}

interface BadgeProps {
  tone: 'green' | 'amber' | 'red' | 'slate';
  label: string;
}

function Badge({ tone, label }: BadgeProps) {
  const colors = {
    green: 'border-emerald-300 bg-emerald-50 text-emerald-800',
    amber: 'border-amber-300 bg-amber-50 text-amber-900',
    red: 'border-red-300 bg-red-50 text-red-800',
    slate: 'border-slate-300 bg-slate-50 text-slate-700',
  } as const;
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${colors[tone]}`}
    >
      {label}
    </span>
  );
}

function formatNumber(n: number, locale: string): string {
  try {
    return new Intl.NumberFormat(locale).format(n);
  } catch {
    return String(n);
  }
}

function formatDate(iso: string, locale: string): string {
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return new Intl.DateTimeFormat(locale, { dateStyle: 'long' }).format(d);
  } catch {
    return iso;
  }
}

export function BreachCard({ breach, href = false }: Props) {
  const { t, i18n } = useTranslation();
  const { locale = 'uz' } = useParams();
  const lng = i18n.language || locale;
  const heading = breach.title || breach.name;

  const cardBody = (
    <article className="space-y-3 rounded-lg border border-slate-200 bg-white p-5 shadow-sm transition hover:border-slate-300 hover:shadow">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-lg font-semibold text-slate-900">{heading}</h3>
          {breach.domain && <p className="text-sm text-slate-500">{breach.domain}</p>}
        </div>
        <div className="flex flex-wrap gap-1.5">
          {breach.isVerified === true && (
            <Badge tone="green" label={t('breach.badges.verified')} />
          )}
          {breach.isVerified === false && (
            <Badge tone="slate" label={t('breach.badges.unverified')} />
          )}
          {breach.isFabricated && <Badge tone="amber" label={t('breach.badges.fabricated')} />}
          {breach.isRetired && <Badge tone="slate" label={t('breach.badges.retired')} />}
          {breach.isSensitive && <Badge tone="red" label={t('breach.badges.sensitive')} />}
          {breach.isSpamList && <Badge tone="amber" label={t('breach.badges.spam_list')} />}
        </div>
      </header>

      <dl className="grid grid-cols-1 gap-2 text-sm sm:grid-cols-2">
        {breach.breachDate && (
          <div>
            <dt className="text-slate-500">{t('breach.date_label')}</dt>
            <dd className="font-medium text-slate-800">{formatDate(breach.breachDate, lng)}</dd>
          </div>
        )}
        {typeof breach.pwnCount === 'number' && (
          <div>
            <dt className="text-slate-500">{t('breach.accounts_label')}</dt>
            <dd className="font-medium text-slate-800">{formatNumber(breach.pwnCount, lng)}</dd>
          </div>
        )}
      </dl>

      {breach.dataClasses && breach.dataClasses.length > 0 && (
        <div>
          <p className="text-sm text-slate-500">{t('breach.data_classes_label')}</p>
          <ul className="mt-1 flex flex-wrap gap-1.5">
            {breach.dataClasses.map((dc) => (
              <li
                key={dc}
                className="rounded bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700"
              >
                {dc}
              </li>
            ))}
          </ul>
        </div>
      )}
    </article>
  );

  if (!href) return cardBody;
  return (
    <Link
      to={`/${locale}/breach/${encodeURIComponent(breach.name)}`}
      className="block focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
    >
      {cardBody}
    </Link>
  );
}
