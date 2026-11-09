/** Demo personas (SPEC 11): the seeded Velugu Cove cast. Signing in as one is just an email login (no passwords exist in this app). */
export const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE === "true";

export const PERSONAS = [
  { key: "lakshmi", name: "Lakshmi", role: "Lead · Sea Breeze Homestay", email: "lakshmi@velugu.example.com" },
  { key: "ravi", name: "Ravi", role: "Sponsor · Ravi's Fish Kitchen", email: "ravi@velugu.example.com" },
  { key: "meena", name: "Meena", role: "Sponsor · Cove Boat Tours", email: "meena@velugu.example.com" },
  { key: "arjun", name: "Arjun", role: "Freelancer", email: "arjun@velugu.example.com" },
] as const;
