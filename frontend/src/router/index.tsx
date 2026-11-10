import { createBrowserRouter, Navigate } from 'react-router-dom';
import { ControlShell } from '../components/layout/ControlShell';
import { BundlesPage } from '../pages/Bundles';
import { ExemptionsPage } from '../pages/Exemptions';
import { LoginPage } from '../pages/Login';
import { PoliciesPage } from '../pages/Policies';
import { RunsPage } from '../pages/Runs';
import { ViolationsPage } from '../pages/Violations';
import { requireAuth } from './guards';

const shell = (element: React.ReactNode) => <ControlShell>{element}</ControlShell>;

export const router = createBrowserRouter([
  { path: '/login', element: <LoginPage /> },
  { path: '/', loader: requireAuth, element: <Navigate to="/bundles" replace /> },
  { path: '/bundles', loader: requireAuth, element: shell(<BundlesPage />) },
  { path: '/policies', loader: requireAuth, element: shell(<PoliciesPage />) },
  { path: '/runs', loader: requireAuth, element: shell(<RunsPage />) },
  { path: '/violations', loader: requireAuth, element: shell(<ViolationsPage />) },
  { path: '/exemptions', loader: requireAuth, element: shell(<ExemptionsPage />) },
  { path: '*', element: <Navigate to="/bundles" replace /> },
]);
