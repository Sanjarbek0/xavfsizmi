import { useTranslation } from 'react-i18next';
import { Link, useParams } from 'react-router';

export function Footer() {
  const { t } = useTranslation();
  const { locale = 'uz' } = useParams();

  return (
    <footer className="border-t border-slate-200 bg-white">
      <div className="mx-auto flex max-w-6xl flex-col items-start justify-between gap-2 px-4 py-6 text-sm text-slate-600 md:flex-row">
        <span>© {new Date().getFullYear()} {t('brand.name')}. {t('footer.rights')}</span>
        <div className="flex gap-4">
          <Link className="hover:underline" to={`/${locale}/security`}>
            {t('footer.security')}
          </Link>
          <Link className="hover:underline" to={`/${locale}/privacy`}>
            {t('footer.privacy')}
          </Link>
        </div>
      </div>
    </footer>
  );
}
