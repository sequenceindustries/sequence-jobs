import type { Metadata } from "next";
import { Account } from "@/components/Account";
export const metadata: Metadata = { title: "Your account", robots: { index: false, follow: false } };
export default function Page() { return <Account />; }
