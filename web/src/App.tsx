import { Route, Routes } from "react-router";

import { RequireAuth } from "./auth/RequireAuth";
import { AppShell } from "./layout/AppShell";
import { EpisodePage } from "./pages/episodes/EpisodePage";
import { ForgotPasswordPage } from "./pages/ForgotPasswordPage";
import { HomePage } from "./pages/HomePage";
import { LoginPage } from "./pages/LoginPage";
import { CompanionPage } from "./pages/CompanionPage";
import { NewVoicePage } from "./pages/voices/NewVoicePage";
import { VoicesPage } from "./pages/voices/VoicesPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { OnboardingPage } from "./pages/OnboardingPage";
import { ResetPasswordPage } from "./pages/ResetPasswordPage";
import { SetupPage } from "./pages/SetupPage";
import { SignUpPage } from "./pages/SignUpPage";
import { NewShowPage } from "./pages/shows/NewShowPage";
import { ShowPage } from "./pages/shows/ShowPage";
import { ShowsPage } from "./pages/shows/ShowsPage";

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/setup" element={<SetupPage />} />
      <Route path="/signup" element={<SignUpPage />} />
      <Route
        path="/welcome"
        element={
          <RequireAuth>
            <OnboardingPage />
          </RequireAuth>
        }
      />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      >
        <Route index element={<HomePage />} />
        <Route path="/shows" element={<ShowsPage />} />
        <Route path="/shows/new" element={<NewShowPage />} />
        <Route path="/shows/:showId" element={<ShowPage />} />
        <Route path="/episodes/:episodeId" element={<EpisodePage />} />
        <Route path="/companion" element={<CompanionPage />} />
        <Route path="/voices" element={<VoicesPage />} />
        <Route path="/voices/new" element={<NewVoicePage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
