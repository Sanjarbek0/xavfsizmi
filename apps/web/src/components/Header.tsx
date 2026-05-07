import { useTranslation } from 'react-i18next';
import { Link, NavLink, useParams } from 'react-router';

import { useAuth } from '../lib/auth-context';
import { LocaleSwitcher } from './LocaleSwitcher';

export function Header() {
  const { t } = useTranslation();
  const { locale = 'uz' } = useParams();
  const { user } = useAuth();

  const navClass = ({ isActive }: { isActive: boolean }) =>
    `rounded px-3 py-2 text-sm font-medium ${
      isActive ? 'bg-brand text-white' : 'text-slate-700 hover:bg-slate-100'
    }`;

  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
        <Link to={`/${locale}`} className="text-lg font-semibold tracking-tight">
          {t('brand.name')}
        </Link>
        <nav className="hidden items-center gap-1 md:flex">
          <NavLink to={`/${locale}`} end className={navClass}>
            {t('nav.home')}
          </NavLink>
          <NavLink to={`/${locale}/passwords`} className={navClass}>
            {t('nav.passwords')}
          </NavLink>
          <NavLink to={`/${locale}/breaches`} className={navClass}>
            {t('nav.breaches')}
          </NavLink>
          <NavLink to={`/${locale}/domains`} className={navClass}>
            {t('nav.domains')}
          </NavLink>
          <NavLink to={`/${locale}/notifications`} className={navClass}>
            {t('nav.notifications')}
          </NavLink>
        </nav>
        <div className="flex items-center gap-2">
          {user ? (
            <NavLink to={`/${locale}/account`} className={navClass}>
              {t('auth.account_link')}
            </NavLink>
          ) : (
            <NavLink to={`/${locale}/sign-in`} className={navClass}>
              {t('auth.sign_in_link')}
            </NavLink>
          )}
          <LocaleSwitcher />
        </div>
      </div>
    </header>
  );
}
