import { LinkButton } from "../components/Button";
import { EmptyState } from "../components/EmptyState";
import { usePageTitle } from "../hooks/usePageTitle";

export function NotFoundPage() {
  usePageTitle("Not found");
  return (
    <EmptyState
      title="Not found"
      action={<LinkButton to="/shows">Go to your shows</LinkButton>}
    >
      This page does not exist, or it belongs to another account.
    </EmptyState>
  );
}
