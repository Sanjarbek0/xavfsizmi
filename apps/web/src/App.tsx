import { Navigate, Route, Routes, useParams } from 'react-router';

import { Layout } from './components/Layout';
import { LocaleGate } from './components/LocaleGate';
import { DomainsPage } from './routes/DomainsPage';
import { HomePage } from './routes/HomePage';
import { NotFoundPage } from './routes/NotFoundPage';
import { NotificationsPage } from './routes/NotificationsPage';
import { PasswordsPage } from './routes/PasswordsPage';
import { PrivacyPage } from './routes/PrivacyPage';
import { SecurityPage } from './routes/SecurityPage';
import { detectLocale } from './i18n/detect';

export function App() {
  return (
    <Routes>
      <Route path="/" element={<RootRedirect />} />
      <Route path="/:locale" element={<LocaleGate />}>
        <Route element={<Layout />}>
          <Route index element={<HomePage />} />
          <Route path="passwords" element={<PasswordsPage />} />
          <Route path="domains" element={<DomainsPage />} />
          <Route path="notifications" element={<NotificationsPage />} />
          <Route path="privacy" element={<PrivacyPage />} />
          <Route path="security" element={<SecurityPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Route>
      <Route path="*" element={<RootRedirect />} />
    </Routes>
  );
}

function RootRedirect() {
  const { locale } = useParams();
  const target = locale ?? detectLocale();
  return <Navigate to={`/${target}`} replace />;
}
