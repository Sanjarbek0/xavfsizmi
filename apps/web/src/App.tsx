import { Navigate, Route, Routes, useParams } from 'react-router';

import { Layout } from './components/Layout';
import { LocaleGate } from './components/LocaleGate';
import { AuthProvider } from './lib/auth-context';
import { AccountPage } from './routes/AccountPage';
import { AdminPage } from './routes/AdminPage';
import { BillingPage } from './routes/BillingPage';
import { BreachDetailPage } from './routes/BreachDetailPage';
import { BreachesPage } from './routes/BreachesPage';
import { ConfirmPage } from './routes/ConfirmPage';
import { DomainsPage } from './routes/DomainsPage';
import { HomePage } from './routes/HomePage';
import { NotFoundPage } from './routes/NotFoundPage';
import { NotificationsPage } from './routes/NotificationsPage';
import { PasswordsPage } from './routes/PasswordsPage';
import { PrivacyPage } from './routes/PrivacyPage';
import { SecurityPage } from './routes/SecurityPage';
import { SignInPage } from './routes/SignInPage';
import { UnsubscribePage } from './routes/UnsubscribePage';
import { VerifyMagicLinkPage } from './routes/VerifyMagicLinkPage';
import { detectLocale } from './i18n/detect';

export function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/" element={<RootRedirect />} />
        <Route path="/:locale" element={<LocaleGate />}>
          <Route element={<Layout />}>
            <Route index element={<HomePage />} />
            <Route path="passwords" element={<PasswordsPage />} />
            <Route path="breaches" element={<BreachesPage />} />
            <Route path="breach/:name" element={<BreachDetailPage />} />
            <Route path="domains" element={<DomainsPage />} />
            <Route path="notifications" element={<NotificationsPage />} />
            <Route path="confirm" element={<ConfirmPage />} />
            <Route path="unsubscribe" element={<UnsubscribePage />} />
            <Route path="privacy" element={<PrivacyPage />} />
            <Route path="security" element={<SecurityPage />} />
            <Route path="sign-in" element={<SignInPage />} />
            <Route path="verify" element={<VerifyMagicLinkPage />} />
            <Route path="account" element={<AccountPage />} />
            <Route path="account/billing" element={<BillingPage />} />
            <Route path="admin" element={<AdminPage />} />
            <Route path="*" element={<NotFoundPage />} />
          </Route>
        </Route>
        <Route path="*" element={<RootRedirect />} />
      </Routes>
    </AuthProvider>
  );
}

function RootRedirect() {
  const { locale } = useParams();
  const target = locale ?? detectLocale();
  return <Navigate to={`/${target}`} replace />;
}
