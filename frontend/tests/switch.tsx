import { useAuth } from "@/lib/auth";

/** A test-only button that signs in as someone else, to prove a screen reloads when the person changes. */
export function Switch() {
  const auth = useAuth();
  return <button onClick={() => void auth.login("ravi@velugu.example.com", "Ravi")}>switch person</button>;
}
